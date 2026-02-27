"""Background service for truncating old events covered by snapshots.

Events are only deleted when ALL of the following conditions are met:
- A snapshot exists for the workflow at version V (events before V are redundant)
- The event's global_id is below the minimum reader offset (all readers have processed it)
- The event has been published by the outbox (pushed=True)
- The event is older than the configured minimum retention period
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from typing import cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.postgres import Offset, Snapshot, StoredEvent

_UTC = timezone.utc

logger = logging.getLogger(__name__)


class TruncationService:
    """Periodically deletes old events that are safely covered by snapshots.

    Args:
        session_maker: SQLAlchemy async session maker
        event_model: Concrete StoredEvent subclass
        snapshot_model: Concrete Snapshot subclass
        offset_model: Concrete Offset subclass
        workflow_type: Workflow type name to truncate events for
        min_retention: Minimum age before an event can be truncated
        batch_size: Maximum events to delete per workflow per cycle
        check_interval: How often the truncation loop runs
    """

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        event_model: type[StoredEvent],
        snapshot_model: type[Snapshot],
        offset_model: type[Offset],
        workflow_type: str,
        min_retention: timedelta = timedelta(days=7),
        batch_size: int = 1000,
        check_interval: timedelta = timedelta(hours=1),
    ) -> None:
        self._session_maker = session_maker
        self._event_model = event_model
        self._snapshot_model = snapshot_model
        self._offset_model = offset_model
        self._workflow_type = workflow_type
        self._min_retention = min_retention
        self._batch_size = batch_size
        self._check_interval = check_interval
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._truncation_loop())
        logger.info(
            "TruncationService started for %s (retention=%s, interval=%s)",
            self._workflow_type,
            self._min_retention,
            self._check_interval,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("TruncationService stopped for %s", self._workflow_type)

    async def _truncation_loop(self) -> None:
        while self._running:
            try:
                deleted = await self._truncate_events()
                if deleted > 0:
                    logger.info(
                        "Truncated %d old events for %s",
                        deleted,
                        self._workflow_type,
                    )
            except Exception:
                logger.exception("Error in truncation loop for %s", self._workflow_type)
            await asyncio.sleep(self._check_interval.total_seconds())

    async def _truncate_events(self) -> int:
        """Run one truncation cycle. Returns total number of events deleted."""
        async with self._session_maker() as s:
            min_offset = await self._get_min_reader_offset(s)
            if min_offset is None:
                return 0

            snapshots = await self._get_snapshots(s)
            if not snapshots:
                return 0

        cutoff_time = datetime.now(tz=_UTC) - self._min_retention
        total_deleted = 0

        for workflow_id, snap_version in snapshots:
            async with self._session_maker() as s:
                cursor_result = cast(
                    CursorResult[Any],
                    await s.execute(
                        delete(self._event_model)
                        .where(self._event_model.workflow_id == workflow_id)
                        .where(self._event_model.workflow_version < snap_version)
                        .where(self._event_model.global_id < min_offset)
                        .where(self._event_model.pushed == True)  # noqa: E712
                        .where(self._event_model.at < cutoff_time)
                    ),
                )
                count: int = cursor_result.rowcount or 0
                if count > 0:
                    await s.commit()
                    total_deleted += count
                    logger.debug(
                        "Deleted %d events for workflow %s (snapshot at v%d)",
                        count,
                        workflow_id,
                        snap_version,
                    )

        return total_deleted

    async def _get_min_reader_offset(self, s: AsyncSession) -> int | None:
        """Get the lowest offset across all readers (safe deletion floor)."""
        result = await s.scalar(select(func.min(self._offset_model.last_read_event_no)))
        return result

    async def _get_snapshots(self, s: AsyncSession) -> list[tuple[str, int]]:
        """Get (workflow_id, version) for all snapshots of this workflow type."""
        result = await s.execute(
            select(
                self._snapshot_model.workflow_id,
                self._snapshot_model.version,
            ).where(self._snapshot_model.workflow_type == self._workflow_type)
        )
        return [(row.workflow_id, row.version) for row in result.fetchall()]
