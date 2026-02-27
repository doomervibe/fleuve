"""NATS JetStream integration for event streaming.

This module implements the Outbox pattern for reliable event delivery:
1. Events are committed to PostgreSQL (single atomic write)
2. OutboxPublisher asynchronously publishes to NATS JetStream
3. Readers consume from JetStream with PostgreSQL fallback

This eliminates dual-write inconsistency while maintaining strong consistency.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Type

from nats.aio.client import Client as NATS
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    DeliverPolicy,
    StorageType,
    StreamConfig,
)
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.postgres import StoredEvent

logger = logging.getLogger(__name__)


class JetStreamPublisher:
    """Publishes events from PostgreSQL to NATS JetStream using Outbox pattern.

    This component continuously polls PostgreSQL for unpublished events
    (pushed=False) and publishes them to NATS JetStream. This ensures:
    - No dual-write inconsistency
    - At-least-once delivery
    - Automatic recovery from failures
    - Strict ordering (requires distributed lock)

    IMPORTANT: Only ONE instance should run per workflow_type to maintain
    event ordering. Uses PostgreSQL advisory locks to ensure exclusivity.
    """

    def __init__(
        self,
        nats_client: NATS,
        session_maker: async_sessionmaker[AsyncSession],
        event_model: Type[StoredEvent],
        stream_name: str,
        workflow_type: str,
        batch_size: int = 100,
        poll_interval: float = 0.1,
        enable_lock: bool = True,
    ):
        """Initialize JetStream publisher.

        Args:
            nats_client: Connected NATS client
            session_maker: SQLAlchemy session maker
            event_model: StoredEvent model class
            stream_name: Name of JetStream stream
            workflow_type: Workflow type name
            batch_size: Number of events to publish per batch
            poll_interval: Seconds between polls when events are found
            enable_lock: Enable distributed lock (default: True, disable only for testing)
        """
        self._nc = nats_client
        self._session_maker = session_maker
        self._event_model = event_model
        self._stream_name = stream_name
        self._workflow_type = workflow_type
        self._batch_size = batch_size
        self._poll_interval = poll_interval
        self._enable_lock = enable_lock
        self._js = None
        self._running = False
        self._publish_task = None
        self._lock_acquired = False
        # Generate unique lock ID based on workflow_type hash
        self._lock_id = hash(f"fleuve_outbox_{workflow_type}") % (2**31)

    async def __aenter__(self):
        """Initialize JetStream and create stream."""
        self._js = self._nc.jetstream()

        # Create or update stream
        try:
            await self._js.add_stream(
                StreamConfig(
                    name=self._stream_name,
                    subjects=[f"events.{self._workflow_type}.*"],
                    max_age=86400,  # 24 hours retention
                    storage=StorageType.FILE,
                    num_replicas=1,  # Increase for HA
                    duplicate_window=300,  # 5 min deduplication window
                )
            )
            logger.info(f"Created JetStream stream: {self._stream_name}")
        except Exception as e:
            logger.info(f"JetStream stream already exists: {self._stream_name}")

        # Acquire distributed lock to ensure single publisher
        if self._enable_lock:
            await self._acquire_lock()

        return self

    async def _acquire_lock(self):
        """Acquire PostgreSQL advisory lock to ensure single publisher.

        Uses pg_try_advisory_lock() which:
        - Returns immediately (non-blocking)
        - Automatically released on connection close
        - Scoped to the session, not transaction

        Raises:
            RuntimeError: If lock cannot be acquired (another publisher is running)
        """
        async with self._session_maker() as s:
            result = await s.execute(select(func.pg_try_advisory_lock(self._lock_id)))
            acquired = result.scalar()

            if not acquired:
                raise RuntimeError(
                    f"Could not acquire lock for OutboxPublisher (workflow_type={self._workflow_type}). "
                    f"Another instance is already running. Lock ID: {self._lock_id}"
                )

            self._lock_acquired = True
            logger.info(
                f"Acquired OutboxPublisher lock for {self._workflow_type} (lock_id={self._lock_id})"
            )

    async def _release_lock(self):
        """Release PostgreSQL advisory lock."""
        if self._lock_acquired:
            try:
                async with self._session_maker() as s:
                    await s.execute(select(func.pg_advisory_unlock(self._lock_id)))
                    logger.info(
                        f"Released OutboxPublisher lock for {self._workflow_type}"
                    )
                    self._lock_acquired = False
            except Exception as e:
                logger.warning(f"Error releasing lock: {e}")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stop publisher and cleanup."""
        await self.stop()
        if self._enable_lock:
            await self._release_lock()
        return False

    async def start(self):
        """Start the outbox publisher background task."""
        if self._running:
            return

        self._running = True
        self._publish_task = asyncio.create_task(self._publish_loop())
        logger.info(f"Started OutboxPublisher for {self._workflow_type}")

    async def stop(self):
        """Stop the outbox publisher."""
        self._running = False
        if self._publish_task:
            self._publish_task.cancel()
            try:
                await self._publish_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Stopped OutboxPublisher for {self._workflow_type}")

    async def _publish_loop(self):
        """Continuously publish unpublished events to JetStream."""
        while self._running:
            try:
                published_count = await self._publish_batch()

                if published_count == 0:
                    # No events to publish, sleep longer
                    await asyncio.sleep(self._poll_interval * 10)
                else:
                    # More events might be available, check quickly
                    await asyncio.sleep(self._poll_interval)

            except Exception as e:
                logger.error(f"Error in publish loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)  # Back off on error

    async def _publish_batch(self) -> int:
        """Publish a batch of unpublished events.

        Returns:
            Number of events published
        """
        async with self._session_maker() as s:
            # Fetch unpublished events
            result = await s.execute(
                select(self._event_model)
                .where(self._event_model.pushed == False)
                .where(self._event_model.workflow_type == self._workflow_type)
                .order_by(self._event_model.global_id)
                .limit(self._batch_size)
            )
            events = result.scalars().all()

            if not events:
                return 0

            published = 0
            for event in events:
                try:
                    # Publish to JetStream with deduplication ID
                    msg_id = f"{event.workflow_id}:{event.workflow_version}"
                    subject = f"events.{event.workflow_type}.{event.event_type}"

                    assert self._js is not None
                    await self._js.publish(
                        subject,
                        event.body.model_dump_json().encode(),
                        headers={
                            "Nats-Msg-Id": msg_id,  # Deduplication
                            "workflow_id": event.workflow_id,
                            "workflow_version": str(event.workflow_version),
                            "event_type": event.event_type,
                            "global_id": str(event.global_id),
                        },
                    )

                    # Mark as published
                    await s.execute(
                        update(self._event_model)
                        .where(self._event_model.global_id == event.global_id)
                        .values(pushed=True)
                    )

                    published += 1

                except Exception as e:
                    logger.error(
                        f"Failed to publish event {event.global_id}: {e}", exc_info=True
                    )
                    # Continue with next event

            if published > 0:
                await s.commit()
                logger.debug(f"Published {published} events to JetStream")

            return published


class JetStreamConsumer:
    """Consumes events from NATS JetStream.

    Provides durable consumption with explicit acknowledgment and
    automatic retries for failed messages.
    """

    def __init__(
        self,
        nats_client: NATS,
        stream_name: str,
        consumer_name: str,
        workflow_type: str,
        event_model_type: Type[BaseModel],
    ):
        """Initialize JetStream consumer.

        Args:
            nats_client: Connected NATS client
            stream_name: Name of JetStream stream to consume from
            consumer_name: Durable consumer name (for offset tracking)
            workflow_type: Workflow type name
            event_model_type: Pydantic model type for event body
        """
        self._nc = nats_client
        self._stream_name = stream_name
        self._consumer_name = consumer_name
        self._workflow_type = workflow_type
        self._event_model_type = event_model_type
        self._js = None
        self._subscription = None

    async def __aenter__(self):
        """Initialize JetStream consumer and create subscription."""
        self._js = self._nc.jetstream()

        # Create durable consumer if it doesn't exist
        try:
            await self._js.add_consumer(
                stream=self._stream_name,
                config=ConsumerConfig(
                    durable_name=self._consumer_name,
                    deliver_policy=DeliverPolicy.ALL,
                    ack_policy=AckPolicy.EXPLICIT,
                    max_deliver=3,  # Retry failed messages up to 3 times
                    ack_wait=30,  # 30s timeout for acknowledgment
                ),
            )
            logger.info(
                f"Created JetStream consumer: {self._consumer_name} on {self._stream_name}"
            )
        except Exception as e:
            logger.info(f"JetStream consumer already exists: {self._consumer_name}")

        # Create pull subscription
        self._subscription = await self._js.pull_subscribe(
            subject=f"events.{self._workflow_type}.*", durable=self._consumer_name
        )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup: unsubscribe from JetStream."""
        if self._subscription:
            await self._subscription.unsubscribe()
        return False

    async def fetch_events(self, batch_size: int = 100, timeout: float = 1.0):
        """Fetch a batch of events from JetStream.

        Yields:
            Tuple of (ConsumedEvent, ack_callback)

        Args:
            batch_size: Number of messages to fetch
            timeout: Timeout in seconds for fetch operation
        """
        try:
            assert self._subscription is not None
            msgs = await self._subscription.fetch(batch_size, timeout=timeout)

            for msg in msgs:
                # Parse event from message
                event = self._parse_message(msg)

                # Return event with ack callback
                async def ack():
                    await msg.ack()

                yield event, ack

        except asyncio.TimeoutError:
            # No messages available - this is normal
            return

    def _get_body_validator(self):
        """Build a validator closure for the event model type."""
        if not hasattr(self, "_cached_body_validator"):
            if hasattr(self._event_model_type, "__table__"):
                body_col = self._event_model_type.__table__.c["body"]  # type: ignore[union-attr]
                self._cached_body_validator = body_col.type._adapter.validate_python
            else:
                self._cached_body_validator = self._event_model_type.model_validate
        return self._cached_body_validator

    def _parse_message(self, msg):
        """Parse NATS message into ConsumedEvent with lazy body validation.

        Args:
            msg: NATS message object

        Returns:
            ConsumedEvent instance with deferred body validation
        """
        from fleuve.stream import ConsumedEvent

        headers = msg.headers or {}
        data = json.loads(msg.data.decode())

        metadata_ = data.get("metadata_", {})
        validator = self._get_body_validator()

        return ConsumedEvent(
            workflow_id=headers.get("workflow_id") or "",
            event_no=int(headers.get("workflow_version") or 0),
            _raw_body=data,
            _body_validator=validator,
            global_id=int(headers.get("global_id") or 0),
            at=(
                datetime.fromisoformat(data.get("at"))
                if "at" in data
                else datetime.now()
            ),
            workflow_type=headers.get("workflow_type") or self._workflow_type,
            event_type=headers.get("event_type") or "",
            metadata_=metadata_,
        )
