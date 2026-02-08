"""
SQLAlchemy database models for testing.
These models are used by test fixtures and are not test classes themselves.
"""
from sqlalchemy import BigInteger, String
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import Mapped, mapped_column

from fleuve.postgres import (
    Activity,
    Base,
    DelaySchedule,
    ExternalSubscription,
    Offset,
    PydanticType,
    StoredEvent,
    Subscription,
)


class DbEventModel(StoredEvent):
    """Database model for storing test workflow events"""

    __tablename__ = "test_events"

    @declared_attr
    def body(cls) -> Mapped:
        # Import here to avoid circular dependency
        from fleuve.tests.conftest import TestEvent

        return mapped_column(
            PydanticType(TestEvent),
            nullable=False,
        )


class TestActivityModel(Activity):
    """Database model for storing test workflow activities"""

    __tablename__ = "test_activities"

    @declared_attr
    def resulting_command(cls) -> Mapped:
        # Import here to avoid circular dependency
        from fleuve.tests.conftest import TestCommand

        return mapped_column(
            PydanticType(TestCommand),
            nullable=True,
        )


class TestDelayScheduleModel(DelaySchedule):
    """Database model for storing test workflow delay schedules"""

    __tablename__ = "test_delay_schedules"

    @declared_attr
    def next_command(cls) -> Mapped:
        # Import here to avoid circular dependency
        from fleuve.tests.conftest import TestCommand

        return mapped_column(
            PydanticType(TestCommand),
            nullable=False,
        )


class TestSubscriptionModel(Subscription):
    """Database model for storing test workflow subscriptions"""

    __tablename__ = "test_subscriptions"


class TestExternalSubscriptionModel(ExternalSubscription):
    """Database model for storing test workflow external (topic) subscriptions"""

    __tablename__ = "test_external_subscriptions"


class TestOffsetModel(Offset):
    """Database model for storing reader offsets"""

    __tablename__ = "test_offsets"


class WorkflowSyncLogModel(Base):
    """Test table for sync_db: one row per sync_db call (same transaction as event insert)."""

    __tablename__ = "workflow_sync_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(String(256), nullable=False)
    events_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
