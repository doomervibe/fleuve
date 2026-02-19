"""Reconciliation service for monitoring PostgreSQL and NATS consistency.

This service acts as a safety net to detect and alert on events that are
stuck in the outbox (unpublished state). It does not automatically fix issues
but provides visibility and monitoring to ensure the OutboxPublisher is
working correctly.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Type

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.postgres import StoredEvent

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Monitors PostgreSQL outbox for stuck unpublished events.

    This service periodically checks for events that have been in the
    unpublished state (pushed=False) for longer than expected. This
    indicates either:
    1. High throughput where OutboxPublisher is catching up
    2. OutboxPublisher failure/crash
    3. NATS connectivity issues

    The service logs warnings but does not automatically republish events.
    The OutboxPublisher handles automatic republishing when it restarts.
    """

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        event_model: Type[StoredEvent],
        workflow_type: str,
        check_interval: timedelta = timedelta(minutes=5),
        stuck_threshold: timedelta = timedelta(minutes=5),
    ):
        """Initialize reconciliation service.

        Args:
            session_maker: SQLAlchemy session maker
            event_model: StoredEvent model class
            workflow_type: Workflow type to monitor
            check_interval: How often to check for stuck events
            stuck_threshold: How old events must be to be considered stuck
        """
        self._session_maker = session_maker
        self._event_model = event_model
        self._workflow_type = workflow_type
        self._check_interval = check_interval
        self._stuck_threshold = stuck_threshold
        self._running = False
        self._task = None

    async def start(self):
        """Start reconciliation monitoring."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._reconciliation_loop())
        logger.info(f"Started ReconciliationService for {self._workflow_type}")

    async def stop(self):
        """Stop reconciliation monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Stopped ReconciliationService for {self._workflow_type}")

    async def _reconciliation_loop(self):
        """Periodically check for stuck unpublished events."""
        while self._running:
            try:
                await self._check_stuck_events()
                await asyncio.sleep(self._check_interval.total_seconds())
            except Exception as e:
                logger.error(f"Reconciliation error: {e}", exc_info=True)
                await asyncio.sleep(60)  # Back off on error

    async def _check_stuck_events(self):
        """Check for events stuck in unpublished state.

        Logs warnings if events are found that have been unpublished
        for longer than the stuck threshold.
        """
        cutoff_time = datetime.now() - self._stuck_threshold

        async with self._session_maker() as s:
            # Count and get range of stuck events
            result = await s.execute(
                select(
                    func.count(self._event_model.global_id),
                    func.min(self._event_model.global_id),
                    func.max(self._event_model.global_id),
                )
                .where(self._event_model.pushed == False)
                .where(self._event_model.workflow_type == self._workflow_type)
                .where(self._event_model.at < cutoff_time)
            )

            count, min_id, max_id = result.one()

            if count > 0:
                logger.warning(
                    f"Found {count} stuck unpublished events "
                    f"(range: {min_id}-{max_id}) older than {self._stuck_threshold}. "
                    f"OutboxPublisher should pick these up automatically."
                )
                # Note: OutboxPublisher will automatically publish these events
                # No manual intervention needed unless this persists
            else:
                logger.debug(
                    f"No stuck events found (threshold: {self._stuck_threshold})"
                )
