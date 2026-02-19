import asyncio
import datetime
import logging
from typing import Generic, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.model import EvDelay, EvDelayComplete
from fleuve.postgres import DelaySchedule, StoredEvent

logger = logging.getLogger(__name__)

C = TypeVar("C", bound=BaseModel)  # Command type
Se = TypeVar("Se", bound=StoredEvent)  # StoredEvent subclass type
Ds = TypeVar("Ds", bound=DelaySchedule)  # DelaySchedule subclass type


class DelayScheduler(Generic[C, Se, Ds]):
    """Service that monitors delay schedules and emits EvDelayComplete events when workflows should resume."""

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        workflow_type: str,
        db_event_model: Type[Se],
        db_delay_schedule_model: Type[Ds],
        check_interval: datetime.timedelta = datetime.timedelta(seconds=1),
    ) -> None:
        self._session_maker = session_maker
        self._workflow_type = workflow_type
        self._db_event_model = db_event_model
        self._db_delay_schedule_model = db_delay_schedule_model
        self._check_interval = check_interval
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the scheduler background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Stop the scheduler background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def __aenter__(self):
        """Async context manager entry: start the delay scheduler."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit: stop the delay scheduler."""
        await self.stop()
        return False

    async def register_delay(
        self,
        workflow_id: str,
        delay_event: EvDelay[C],
        event_version: int,
    ):
        """Register a delay schedule when EvDelay event is emitted.
        Multiple delays can coexist per workflow; each is identified by delay_event.id.
        A delay replaces an existing one only if both belong to the same workflow and
        their IDs match."""
        async with self._session_maker() as s:
            # Replace only if same workflow AND same delay id
            await s.execute(
                delete(self._db_delay_schedule_model)
                .where(self._db_delay_schedule_model.workflow_id == workflow_id)
                .where(self._db_delay_schedule_model.delay_id == delay_event.id)
            )

            # Insert new delay schedule
            await s.execute(
                insert(self._db_delay_schedule_model).values(
                    {
                        "workflow_id": workflow_id,
                        "delay_id": delay_event.id,
                        "workflow_type": self._workflow_type,
                        "delay_until": delay_event.delay_until,
                        "event_version": event_version,
                        "next_command": delay_event.next_cmd,
                    }
                )
            )
            await s.commit()
        logger.info(
            f"Registered delay {delay_event.id} for workflow {workflow_id} until {delay_event.delay_until}"
        )

    async def _run_loop(self):
        """Main loop that checks for workflows that should resume."""
        while self._running:
            try:
                await self._check_and_resume()
            except Exception as e:
                logger.exception(f"Error in delay scheduler loop: {e}")

            await asyncio.sleep(self._check_interval.total_seconds())

    async def _check_and_resume(self):
        """Check for workflows that should resume and emit EvDelayComplete events."""
        now = datetime.datetime.now(datetime.timezone.utc)

        async with self._session_maker() as s:
            # Find all workflows that should resume
            result = await s.execute(
                select(self._db_delay_schedule_model)
                .where(
                    self._db_delay_schedule_model.workflow_type == self._workflow_type
                )
                .where(self._db_delay_schedule_model.delay_until <= now)
            )
            schedules = result.fetchall()

            for schedule in schedules:
                try:
                    await self._resume_workflow(s, schedule)
                except Exception as e:
                    logger.exception(
                        f"Error resuming workflow {schedule.workflow_id}: {e}"
                    )

    async def _resume_workflow(self, s: AsyncSession, schedule: Ds):
        """Resume a workflow by emitting EvDelayComplete event. The workflow's event_to_cmd should return the next_cmd."""
        workflow_id = schedule.workflow_id

        # Get the current version to determine where to insert the resume event
        version_result = await s.scalar(
            select(self._db_event_model.workflow_version)
            .where(self._db_event_model.workflow_id == workflow_id)
            .order_by(self._db_event_model.workflow_version.desc())
            .limit(1)
        )

        if version_result is None:
            logger.warning(f"Cannot resume workflow {workflow_id}: no events found")
            # Clean up the delay schedule
            await s.execute(
                delete(self._db_delay_schedule_model)
                .where(self._db_delay_schedule_model.workflow_id == workflow_id)
                .where(self._db_delay_schedule_model.delay_id == schedule.delay_id)
            )
            await s.commit()
            return

        # Emit EvDelayComplete event (concrete class, emitted by system not workflow)
        delay_complete_event = EvDelayComplete(
            delay_id=schedule.delay_id,
            at=datetime.datetime.now(datetime.timezone.utc),
            next_cmd=schedule.next_command,
        )

        await s.execute(
            insert(self._db_event_model).values(
                {
                    "workflow_id": workflow_id,
                    "workflow_version": version_result + 1,
                    "event_type": delay_complete_event.type,
                    "workflow_type": self._workflow_type,
                    "body": delay_complete_event,
                    "schema_version": 1,
                }
            )
        )

        # Remove the delay schedule
        await s.execute(
            delete(self._db_delay_schedule_model)
            .where(self._db_delay_schedule_model.workflow_id == workflow_id)
            .where(self._db_delay_schedule_model.delay_id == schedule.delay_id)
        )

        await s.commit()

        logger.info(f"Resumed workflow {workflow_id} at version {version_result + 1}")
