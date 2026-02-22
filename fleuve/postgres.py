import hashlib
import os
from datetime import datetime, timedelta
from typing import Any, Literal, Optional, TypeVar

import zstandard
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from cryptography.hazmat.primitives.ciphers.algorithms import AES256
from cryptography.hazmat.primitives.padding import PKCS7
from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Dialect,
    Integer,
    String,
    TypeDecorator,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy.schema import Index

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_storage_key() -> AES256:
    sha256 = hashlib.sha256()
    sha256.update(os.environ["STORAGE_KEY"].encode())
    return AES256(sha256.digest())


def aes256encrypt_2(key: AES256, pt: bytes) -> tuple[bytes, bytes]:
    padder = PKCS7(key.block_size).padder()
    nonce = os.urandom(16)
    enc = Cipher(key, modes.CBC(nonce)).encryptor()
    padded = padder.update(pt) + padder.finalize()
    return enc.update(padded) + enc.finalize(), nonce


def aes256decrypt_2(key: AES256, nonce: bytes, ct: bytes) -> bytes:
    dec = Cipher(key, modes.CBC(nonce)).decryptor()
    unpadder = PKCS7(key.block_size).unpadder()
    return unpadder.update(dec.update(ct) + dec.finalize()) + unpadder.finalize()


class Encryption:
    def __init__(self, storage_key: AES256) -> None:
        self._key = storage_key

    def encrypt(self, data: bytes) -> bytes:
        padder = PKCS7(self._key.block_size).padder()
        nonce = os.urandom(16)
        enc = Cipher(self._key, modes.CBC(nonce)).encryptor()
        padded = padder.update(data) + padder.finalize()
        return nonce + enc.update(padded) + enc.finalize()

    def decrypt(self, data: bytes) -> bytes:
        nonce = data[:16]
        ct = data[16:]
        dec = Cipher(self._key, modes.CBC(nonce)).decryptor()
        unpadder = PKCS7(self._key.block_size).unpadder()
        return unpadder.update(dec.update(ct) + dec.finalize()) + unpadder.finalize()


class EncryptedPydanticType(TypeDecorator[ModelT]):
    """SQLAlchemy type for storing Pydantic models in encrypted form (AES256)."""

    cache_ok = True
    impl = BYTEA

    ZSTD_COMPRESSSION = True

    def __init__(
        self,
        pydantic_type: type[ModelT],
        encryption: Encryption | None = None,
    ) -> None:
        super().__init__()
        self._pydantic_type = pydantic_type
        self._adapter = TypeAdapter(pydantic_type)
        self._encryption = encryption or Encryption(load_storage_key())

    def process_bind_param(self, value: ModelT | None, _dialect: Dialect) -> Any:
        if value is None:
            return None
        json_data_bytes = self._adapter.dump_json(value)
        if self.ZSTD_COMPRESSSION:
            json_data_bytes = b"zstd:" + zstandard.compress(json_data_bytes)
        return self._encryption.encrypt(json_data_bytes)

    def process_result_value(self, value: Any, _dialect: Dialect) -> ModelT | None:
        if value is None:
            return None
        json_data_bytes = self._encryption.decrypt(value)
        if json_data_bytes.startswith(b"zstd:"):
            json_data_bytes = zstandard.decompress(json_data_bytes[5:])
        return self._adapter.validate_json(json_data_bytes)


class PydanticType(TypeDecorator[ModelT]):
    """SQLAlchemy type for storing Pydantic models"""

    cache_ok = True
    impl = JSONB

    def __init__(
        self,
        pydantic_type: type[ModelT],
    ) -> None:
        super().__init__()
        self._pydantic_type = pydantic_type
        self._adapter = TypeAdapter(pydantic_type)

    def process_bind_param(self, value: ModelT | None, _dialect: Dialect) -> Any:
        if value is None:
            return None
        # Return JSON string for JSONB column
        return self._adapter.dump_json(value).decode("utf-8")

    def process_result_value(self, value: Any, _dialect: Dialect) -> ModelT | None:
        if value is None:
            return None
        return self._adapter.validate_json(value)


Base = declarative_base()


class StoredEvent(Base):
    __abstract__ = True

    global_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    workflow_id: Mapped[str] = mapped_column(String(256))
    workflow_version: Mapped[int] = mapped_column(BigInteger, nullable=False)

    event_type: Mapped[str] = mapped_column(String, nullable=False)
    workflow_type: Mapped[str] = mapped_column(String, nullable=False)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    # Abstract property - must be implemented by subclasses
    # Using declared_attr allows proper inheritance and override
    @declared_attr
    def body(cls) -> Mapped[BaseModel]:
        """Abstract body column that must be implemented by subclasses"""
        raise NotImplementedError(
            f"Subclass {cls.__name__} must implement the 'body' column "
            f"with specific database type"
        )

    at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    # Use metadata_ as attribute name to avoid SQLAlchemy reserved word conflict
    # The database column name remains "metadata"
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    pushed: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("workflow_id", "workflow_version"),
        Index("idx__workflow_type_global_id", "workflow_type", "global_id"),
    )


class StoredState(Base):
    __abstract__ = True

    workflow_id: Mapped[str] = mapped_column(String(256), primary_key=True)

    @declared_attr
    def state(cls) -> Mapped[BaseModel]:
        """Abstract state column that must be implemented by subclasses"""
        raise NotImplementedError(
            f"Subclass {cls.__name__} must implement the 'state' column "
            f"with specific database type"
        )


class Snapshot(Base):
    """Durable state snapshot for a workflow at a specific event version.

    One row per workflow (upserted). Used to avoid replaying all events from
    the beginning when reconstructing state. Users must create a concrete
    subclass that implements the abstract ``state`` column with
    ``PydanticType`` or ``EncryptedPydanticType``.
    """

    __abstract__ = True

    workflow_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)

    @declared_attr
    def state(cls) -> Mapped[BaseModel]:
        """Abstract state column that must be implemented by subclasses"""
        raise NotImplementedError(
            f"Subclass {cls.__name__} must implement the 'state' column "
            f"with specific database type"
        )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Offset(Base):
    __abstract__ = True
    reader: Mapped[str] = mapped_column(
        String, nullable=False, primary_key=True, index=True
    )
    last_read_event_no: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )


class Subscription(Base):
    """Internal (Fleuve-native) event subscriptions. Workflows subscribe to events from other workflows."""

    __abstract__ = True

    workflow_id: Mapped[str] = mapped_column(String(256), index=True, primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String, nullable=False, index=True)

    subscribed_to_workflow: Mapped[str] = mapped_column(String, primary_key=True)
    subscribed_to_event_type: Mapped[str] = mapped_column(String, primary_key=True)

    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    tags_all: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )

    __table_args__ = (
        Index("idx_subscription_tags", "tags", postgresql_using="gin"),
        Index("idx_subscription_tags_all", "tags_all", postgresql_using="gin"),
    )


class ExternalSubscription(Base):
    """External (NATS topic) subscriptions. Workflows subscribe to external message topics by keyword."""

    __abstract__ = True

    workflow_id: Mapped[str] = mapped_column(String(256), index=True, primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(256), primary_key=True)

    __table_args__ = (
        Index(
            "idx_external_subscription_workflow_type_topic", "workflow_type", "topic"
        ),
    )


class RetryPolicy(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    backoff_strategy: Literal["exponential", "linear"] = "exponential"
    backoff_factor: float = 2
    backoff_max: timedelta = timedelta(seconds=60)
    backoff_min: timedelta = timedelta(seconds=1)
    backoff_jitter: float = 0.5


class Activity(Base):
    __abstract__ = True

    workflow_id: Mapped[str] = mapped_column(String(256), index=True, primary_key=True)
    event_number: Mapped[int] = mapped_column(
        BigInteger, nullable=True, primary_key=True
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # pending, running, completed, failed, retrying

    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    last_attempt_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Checkpoint data for resuming interrupted actions
    checkpoint: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    retry_policy: Mapped[RetryPolicy] = mapped_column(
        PydanticType(RetryPolicy), nullable=False, default=RetryPolicy()
    )

    # Error information for failed actions
    error_message: Mapped[str] = mapped_column(String, nullable=True)
    error_type: Mapped[str] = mapped_column(String, nullable=True)

    result: Mapped[bytes] = mapped_column(BYTEA, nullable=True)

    # Runner/reader that is executing or last executed this activity
    runner_id: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, index=True
    )


class DelaySchedule(Base):
    __abstract__ = True

    workflow_id: Mapped[str] = mapped_column(String(256), primary_key=True, index=True)
    delay_id: Mapped[str] = mapped_column(String(256), primary_key=True, index=True)
    workflow_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    delay_until: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, index=True
    )
    event_version: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Abstract property - must be implemented by subclasses
    @declared_attr
    def next_command(cls) -> Mapped[BaseModel]:
        """Abstract next_command column that must be implemented by subclasses. Required (non-nullable)."""
        raise NotImplementedError(
            f"Subclass {cls.__name__} must implement the 'next_command' column "
            f"with specific database type"
        )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ScalingOperation(Base):
    """Table for coordinating scaling operations across workers.

    Workers poll this table to detect when scaling is in progress and
    stop at the target_offset when they reach it.
    """

    __abstract__ = True

    workflow_type: Mapped[str] = mapped_column(
        String, nullable=False, primary_key=True, index=True
    )
    target_offset: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )  # pending, synchronizing, completed, failed
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class WorkflowMetadata(Base):
    """Table for storing workflow-level metadata including creation-time tags.

    Tags stored here are associated with the workflow instance at creation
    and can be used for tag-based event subscriptions.
    """

    __abstract__ = True

    workflow_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_workflow_metadata_tags", "tags", postgresql_using="gin"),
    )
