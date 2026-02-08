import asyncio
import datetime
import logging
from enum import Enum
from typing import Any, Callable, Generic, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.model import ActionContext, Adapter, RetryPolicy
from fleuve.postgres import Activity, StoredEvent
from fleuve.repo import AsyncRepo
from fleuve.stream import ConsumedEvent

logger = logging.getLogger(__name__)

C = TypeVar("C", bound=BaseModel)  # Command type
E = TypeVar("E", bound=BaseModel)  # Event type
Ae = TypeVar("Ae", bound=Activity)  # Activity subclass type


class ActionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class ActionExecutor(Generic[C, Ae]):
    """Manages action execution with retry logic, checkpointing, and recovery."""

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        adapter: Adapter,
        db_activity_model: Type[Ae],
        db_event_model: Type[StoredEvent],
        repo: AsyncRepo,
        max_retries: int = 3,
        recovery_interval: datetime.timedelta = datetime.timedelta(seconds=30),
        action_timeout: datetime.timedelta | None = None,
    ) -> None:
        self._session_maker = session_maker
        self._adapter = adapter
        self._db_activity_model = db_activity_model
        self._db_event_model = db_event_model
        self._repo = repo
        self._max_retries = max_retries
        self._recovery_interval = recovery_interval
        self._action_timeout = action_timeout
        self._running_actions: dict[tuple[str, int], asyncio.Task] = {}
        self._recovery_task: asyncio.Task | None = None
        self._running = False

    def to_be_act_on(self, event: Any) -> bool:
        return self._adapter.to_be_act_on(event)

    async def start(self):
        """Start the action executor and recovery mechanism."""
        if self._running:
            return
        self._running = True
        self._recovery_task = asyncio.create_task(self._recovery_loop())

    async def stop(self):
        """Stop the action executor and recovery mechanism."""
        self._running = False
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
        # Wait for running actions to complete (with timeout)
        if self._running_actions:
            await asyncio.wait_for(
                asyncio.gather(*self._running_actions.values(), return_exceptions=True),
                timeout=30.0,
            )

    async def __aenter__(self):
        """Async context manager entry: start the action executor."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit: stop the action executor."""
        await self.stop()
        return False

    async def execute_action(self, event: ConsumedEvent) -> None:
        """Execute an action for an event, with idempotency and retry logic."""
        action_key = (event.agg_id, event.event_no)

        # Check if action is already running
        if action_key in self._running_actions:
            logger.debug(
                f"Action for {event.agg_id}:{event.event_no} is already running"
            )
            return

        # Check if action is already completed
        async with self._session_maker() as s:
            activity = await self._get_activity(s, event.agg_id, event.event_no)
            if activity and activity.status == ActionStatus.COMPLETED:
                logger.debug(
                    f"Action for {event.agg_id}:{event.event_no} already completed"
                )
                return

        # Start action execution
        task = asyncio.create_task(
            self._run_action_with_retry(event),
            name=f"action-{event.agg_id}-{event.event_no}",
        )
        self._running_actions[action_key] = task

        try:
            await task
        finally:
            self._running_actions.pop(action_key, None)

    async def _run_action_with_retry(self, event: ConsumedEvent) -> None:
        """Run action with retry logic and checkpoint support."""
        workflow_id = event.agg_id
        event_number = event.event_no

        activity: Ae
        async with self._session_maker() as s:
            activity = await self._get_or_create_activity(s, event)

        retry_count = 0
        last_exception = None

        while retry_count <= activity.retry_policy.max_retries:
            try:
                # Update activity status
                async with self._session_maker() as s:
                    await self._update_activity_status(
                        s,
                        workflow_id,
                        event_number,
                        (
                            ActionStatus.RUNNING
                            if retry_count == 0
                            else ActionStatus.RETRYING
                        ),
                        retry_count=retry_count,
                    )

                context = ActionContext(
                    workflow_id=workflow_id,
                    event_number=event_number,
                    checkpoint=activity.checkpoint.copy(),  # Copy to allow mutation
                    retry_count=retry_count,
                    retry_policy=activity.retry_policy.model_copy(),
                )
                
                # Set up checkpoint saver callback for immediate persistence
                async def checkpoint_saver(checkpoint_data: dict) -> None:
                    """Callback to immediately persist checkpoint data to database."""
                    async with self._session_maker() as s:
                        await self._save_checkpoint(
                            s, workflow_id, event_number, checkpoint_data
                        )
                
                context._checkpoint_saver = checkpoint_saver

                # Execute the action (with timeout if configured)
                # Pass the actual event, not ConsumedEvent
                try:
                    if self._action_timeout:
                        cmd = await asyncio.wait_for(
                            self._adapter.act_on(event, context),
                            timeout=self._action_timeout.total_seconds(),
                        )
                    else:
                        cmd = await self._adapter.act_on(event, context)
                except Exception:
                    # Save checkpoint even on failure for resume capability
                    if context.checkpoint != activity.checkpoint:
                        async with self._session_maker() as s:
                            await self._save_checkpoint(
                                s, workflow_id, event_number, context.checkpoint
                            )
                    if context.retry_policy != activity.retry_policy:
                        async with self._session_maker() as s:
                            await self._update_activity_retry_policy(
                                s, workflow_id, event_number, context.retry_policy
                            )
                    raise
                else:
                    # Save checkpoint if it was updated during execution
                    if context.checkpoint != activity.checkpoint:
                        async with self._session_maker() as s:
                            await self._save_checkpoint(
                                s, workflow_id, event_number, context.checkpoint
                            )
                    if context.retry_policy != activity.retry_policy:
                        async with self._session_maker() as s:
                            await self._update_activity_retry_policy(
                                s, workflow_id, event_number, context.retry_policy
                            )

                activity.checkpoint = context.checkpoint
                activity.retry_policy = context.retry_policy

                # Process the resulting command if provided BEFORE marking as completed
                # This ensures that if the process crashes, the action will be recovered
                # and the command will be processed again (process_command is idempotent)
                if cmd:
                    try:
                        await self._repo.process_command(workflow_id, cmd)
                    except Exception as e:
                        logger.exception(
                            f"Error processing command after action completion "
                            f"for {workflow_id}:{event_number}: {e}"
                        )
                        raise

                # Action completed successfully - mark as completed after command processing
                async with self._session_maker() as s:
                    await self._mark_action_completed(
                        s, workflow_id, event_number, cmd, result=None
                    )

                logger.info(
                    f"Action completed for {workflow_id}:{event_number} "
                    f"(retry_count={retry_count})"
                )
                return

            except asyncio.TimeoutError:
                last_exception = asyncio.TimeoutError("Action execution timed out")
                logger.warning(
                    f"Action timeout for {workflow_id}:{event_number} "
                    f"(attempt {retry_count + 1}/{activity.retry_policy.max_retries + 1})"
                )
            except Exception as e:
                last_exception = e
                error_msg = str(e)
                error_type = type(e).__name__
                logger.exception(
                    f"Action failed for {workflow_id}:{event_number} "
                    f"(attempt {retry_count + 1}/{activity.retry_policy.max_retries + 1}): {error_msg}"
                )

                # Update activity with error information
                async with self._session_maker() as s:
                    await self._update_activity_error(
                        s, workflow_id, event_number, error_type, error_msg, retry_count
                    )

            retry_count += 1

            if retry_count <= activity.retry_policy.max_retries:
                if activity.retry_policy.backoff_strategy == "exponential":
                    # Calculate exponential backoff delay
                    delay = max(
                        activity.retry_policy.backoff_min.total_seconds(),
                        min(
                            activity.retry_policy.backoff_factor**retry_count,
                            activity.retry_policy.backoff_max.total_seconds(),
                        ),
                    )
                    logger.info(
                        f"Retrying action for {workflow_id}:{event_number} "
                        f"after {delay}s (attempt {retry_count + 1}/{activity.retry_policy.max_retries + 1})"
                    )
                elif activity.retry_policy.backoff_strategy == "linear":
                    # Calculate linear backoff delay
                    delay = max(
                        activity.retry_policy.backoff_min.total_seconds(),
                        activity.retry_policy.backoff_factor * retry_count,
                    )
                    logger.info(
                        f"Retrying action for {workflow_id}:{event_number} "
                        f"after {delay}s (attempt {retry_count + 1}/{activity.retry_policy.max_retries + 1})"
                    )
                await asyncio.sleep(delay)

        # All retries exhausted
        async with self._session_maker() as s:
            await self._mark_action_failed(s, workflow_id, event_number, last_exception)
        logger.error(
            f"Action failed permanently for {workflow_id}:{event_number} "
            f"after {activity.retry_policy.max_retries + 1} attempts"
        )

    async def _recovery_loop(self):
        """Periodically check for interrupted actions and resume them."""
        while self._running:
            try:
                await self._recover_interrupted_actions()
            except Exception as e:
                logger.exception(f"Error in action recovery loop: {e}")

            await asyncio.sleep(self._recovery_interval.total_seconds())

    async def _recover_interrupted_actions(self):
        """Find and resume interrupted actions."""
        # Find actions that are in "running" or "retrying" state but haven't been updated recently
        threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            minutes=5
        )

        async with self._session_maker() as s:
            result = await s.execute(
                select(self._db_activity_model)
                .where(
                    self._db_activity_model.status.in_(
                        [ActionStatus.RUNNING, ActionStatus.RETRYING]
                    )
                )
                .where(
                    (self._db_activity_model.last_attempt_at < threshold)
                    | (self._db_activity_model.last_attempt_at.is_(None))
                )
            )
            interrupted_activities = result.fetchall()

        for activity in interrupted_activities:
            # Reconstruct the event from the database
            async with self._session_maker() as s:
                event_result = await s.execute(
                    select(self._db_event_model)
                    .where(self._db_event_model.workflow_id == activity.workflow_id)
                    .where(
                        self._db_event_model.workflow_version == activity.event_number
                    )
                    .limit(1)
                )
                event_row = event_result.fetchone()

                if event_row:
                    event = ConsumedEvent(
                        agg_id=activity.workflow_id,
                        event=event_row.body,
                        event_no=activity.event_number,
                        event_g_id=event_row.global_id,
                        at=event_row.at,
                    )
                    logger.info(
                        f"Recovering interrupted action for {activity.workflow_id}:{activity.event_number}"
                    )
                    # Resume the action
                    await self.execute_action(event)

    async def _get_activity(
        self, s: AsyncSession, workflow_id: str, event_number: int
    ) -> Ae | None:
        """Get an activity record."""
        result = await s.execute(
            select(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_activity(
        self, s: AsyncSession, event: ConsumedEvent
    ) -> Ae:
        """Get or create an activity record."""
        activity = await self._get_activity(s, event.agg_id, event.event_no)
        if activity:
            return activity

        # Create new activity
        activity = self._db_activity_model(
            workflow_id=event.agg_id,
            event_number=event.event_no,
            status=ActionStatus.PENDING,
            max_retries=self._max_retries,
            started_at=datetime.datetime.now(datetime.timezone.utc),
        )
        s.add(activity)
        await s.commit()
        await s.refresh(activity)
        return activity

    async def _update_activity_status(
        self,
        s: AsyncSession,
        workflow_id: str,
        event_number: int,
        status: ActionStatus,
        retry_count: int = 0,
    ):
        """Update activity status."""
        await s.execute(
            update(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
            .values(
                status=status.value,
                retry_count=retry_count,
                last_attempt_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        await s.commit()

    async def _update_activity_error(
        self,
        s: AsyncSession,
        workflow_id: str,
        event_number: int,
        error_type: str,
        error_message: str,
        retry_count: int,
    ):
        """Update activity with error information."""
        await s.execute(
            update(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
            .values(
                error_type=error_type,
                error_message=error_message,
                retry_count=retry_count,
                last_attempt_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        await s.commit()

    async def _mark_action_completed(
        self,
        s: AsyncSession,
        workflow_id: str,
        event_number: int,
        cmd: C | None,
        result: bytes | None = None,
    ):
        """Mark an action as completed."""
        values = {
            "status": ActionStatus.COMPLETED.value,
            "finished_at": datetime.datetime.now(datetime.timezone.utc),
        }
        if cmd:
            values["resulting_command"] = cmd
        if result:
            values["result"] = result

        await s.execute(
            update(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
            .values(**values)
        )
        await s.commit()

    async def _save_checkpoint(
        self, s: AsyncSession, workflow_id: str, event_number: int, checkpoint: dict
    ):
        """Save checkpoint data for an action."""
        await s.execute(
            update(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
            .values(checkpoint=checkpoint)
        )
        await s.commit()

    async def _update_activity_retry_policy(
        self, s: AsyncSession, workflow_id: str, event_number: int, retry_policy: RetryPolicy
    ):
        """Update the retry policy for an activity."""
        await s.execute(
            update(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
            .values(retry_policy=retry_policy)
        )
        await s.commit()

    async def _mark_action_failed(
        self, s: AsyncSession, workflow_id: str, event_number: int, exception: Exception
    ):
        """Mark an action as permanently failed."""
        await s.execute(
            update(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
            .values(
                status=ActionStatus.FAILED.value,
                finished_at=datetime.datetime.now(datetime.timezone.utc),
                error_type=type(exception).__name__,
                error_message=str(exception),
            )
        )
        await s.commit()
