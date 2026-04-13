import asyncio
import datetime
import logging
from collections.abc import Awaitable
from enum import Enum
from typing import Any, Callable, Generic, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.model import (
    ActionContext,
    ActionTimeout,
    Adapter,
    CheckpointYield,
    RetryPolicy,
)
from fleuve.postgres import Activity, StoredEvent
from fleuve.repo import AsyncRepo
from fleuve.stream import ConsumedEvent
from fleuve.tracing import _NoopTracer

logger = logging.getLogger(__name__)


class EmptyActionError(RuntimeError):
    """Raised when act_on yields zero items; the adapter is considered misconfigured."""


C = TypeVar("C", bound=BaseModel)  # Command type
E = TypeVar("E", bound=BaseModel)  # Event type
Ae = TypeVar("Ae", bound=Activity)  # Activity subclass type


class ActionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


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
        recovery_stale_after: datetime.timedelta = datetime.timedelta(minutes=1),
        action_timeout: datetime.timedelta | None = None,
        on_action_failed: (
            Callable[[str, int, Exception], Awaitable[None]] | None
        ) = None,
        metrics: Any = None,
        tracer: Any = None,
        runner_name: str | None = None,
        max_concurrent_actions: int | None = None,
        max_concurrent_actions_per_workflow: int | None = None,
    ) -> None:
        self._session_maker = session_maker
        self._adapter = adapter
        self._metrics = metrics
        self._runner_name = runner_name
        self._db_activity_model = db_activity_model
        self._db_event_model = db_event_model
        self._repo = repo
        self._max_retries = max_retries
        self._recovery_interval = recovery_interval
        self._recovery_stale_after = recovery_stale_after
        self._action_timeout = action_timeout
        self._on_action_failed = on_action_failed
        self._tracer = tracer or _NoopTracer()
        self._running_actions: dict[tuple[str, int], asyncio.Task] = {}
        self._recovery_task: asyncio.Task | None = None
        self._running = False
        self._global_semaphore: asyncio.Semaphore | None = (
            asyncio.Semaphore(max_concurrent_actions)
            if max_concurrent_actions
            else None
        )
        self._max_concurrent_per_workflow = max_concurrent_actions_per_workflow
        self._workflow_semaphores: dict[str, asyncio.Semaphore] = {}

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

        # Check if action is already completed and ensure activity exists before firing
        async with self._session_maker() as s:
            activity = await self._get_activity(s, event.agg_id, event.event_no)
            if activity and activity.status == ActionStatus.COMPLETED:
                logger.debug(
                    f"Action for {event.agg_id}:{event.event_no} already completed"
                )
                return
            # Create activity synchronously before firing background task
            await self._get_or_create_activity(s, event)

        # Start action execution in the background (fire-and-forget)
        task = asyncio.create_task(
            self._run_action_with_retry(event),
            name=f"action-{event.agg_id}-{event.event_no}",
        )
        self._running_actions[action_key] = task

        # Set up callback to remove task from running actions when it completes
        def _on_task_done(t: asyncio.Task) -> None:
            self._running_actions.pop(action_key, None)
            # Log any exceptions that weren't handled
            try:
                t.result()
            except asyncio.CancelledError:
                pass  # Expected during shutdown
            except Exception as e:
                logger.exception(
                    f"Unhandled exception in action task for {event.agg_id}:{event.event_no}: {e}"
                )

        task.add_done_callback(_on_task_done)

    async def cancel_workflow_actions(
        self, workflow_id: str, event_numbers: list[int] | None = None
    ) -> None:
        """
        Cancel actions for a workflow.
        If event_numbers is None or empty: cancel all.
        If event_numbers is non-empty: cancel only those specific event versions.
        """
        if event_numbers:
            keys_to_cancel = [(workflow_id, ev_no) for ev_no in event_numbers]
        else:
            keys_to_cancel = [
                (wf_id, ev_no)
                for (wf_id, ev_no) in self._running_actions
                if wf_id == workflow_id
            ]

        for key in keys_to_cancel:
            task = self._running_actions.get(key)
            if task:
                task.cancel()

        # Mark activities as CANCELLED in DB
        async with self._session_maker() as s:
            q = (
                update(self._db_activity_model)
                .where(self._db_activity_model.workflow_id == workflow_id)
                .where(
                    self._db_activity_model.status.in_(
                        [
                            ActionStatus.RUNNING.value,
                            ActionStatus.RETRYING.value,
                            ActionStatus.PENDING.value,
                        ]
                    )
                )
            )
            if event_numbers:
                q = q.where(self._db_activity_model.event_number.in_(event_numbers))
            await s.execute(q.values(status=ActionStatus.CANCELLED.value))
            await s.commit()

    async def retry_failed_action(self, workflow_id: str, event_number: int) -> bool:
        """Reset a FAILED activity to PENDING and re-execute it.

        Returns True if the action was found and re-queued, False otherwise.
        """
        async with self._session_maker() as s:
            activity = await self._get_activity(s, workflow_id, event_number)
            if activity is None or activity.status != ActionStatus.FAILED.value:
                return False

            await s.execute(
                update(self._db_activity_model)
                .where(self._db_activity_model.workflow_id == workflow_id)
                .where(self._db_activity_model.event_number == event_number)
                .values(
                    status=ActionStatus.PENDING.value,
                    finished_at=None,
                    retry_count=0,
                    error_type=None,
                    error_message=None,
                )
            )
            await s.commit()

        async with self._session_maker() as s:
            result = await s.execute(
                select(self._db_event_model)
                .where(self._db_event_model.workflow_id == workflow_id)
                .where(self._db_event_model.workflow_version == event_number)
                .limit(1)
            )
            event_row = result.scalar_one_or_none()

        if event_row is None:
            logger.warning(
                f"Cannot retry {workflow_id}:{event_number}: event not found"
            )
            return False

        event: ConsumedEvent[Any] = ConsumedEvent(
            workflow_id=workflow_id,
            event_no=event_number,
            event=event_row.body,
            global_id=event_row.global_id,
            at=event_row.at,
            workflow_type=getattr(
                event_row, "workflow_type", self._repo._workflow_type
            ),
            event_type=getattr(event_row, "event_type", ""),
            metadata_=getattr(event_row, "metadata_", None) or {},
        )
        await self.execute_action(event)
        return True

    def _get_workflow_semaphore(self, workflow_id: str) -> asyncio.Semaphore | None:
        if not self._max_concurrent_per_workflow:
            return None
        sem = self._workflow_semaphores.get(workflow_id)
        if sem is None:
            sem = asyncio.Semaphore(self._max_concurrent_per_workflow)
            self._workflow_semaphores[workflow_id] = sem
        return sem

    async def _run_action_with_retry(self, event: ConsumedEvent) -> None:
        """Run action with retry logic and checkpoint support.

        Acquires global and per-workflow concurrency slots before executing.
        Tasks are created immediately (for dedup tracking) but actual work
        waits until a slot is available.
        """
        workflow_id = event.agg_id
        event_number = event.event_no

        if self._global_semaphore:
            await self._global_semaphore.acquire()
        try:
            wf_sem = self._get_workflow_semaphore(workflow_id)
            if wf_sem:
                await wf_sem.acquire()
            try:
                with self._tracer.span(
                    "execute_action",
                    {
                        "fleuve.workflow_id": workflow_id,
                        "fleuve.event_number": event_number,
                    },
                ):
                    await self._run_action_with_retry_impl(event)
            finally:
                if wf_sem:
                    wf_sem.release()
        finally:
            if self._global_semaphore:
                self._global_semaphore.release()

    async def _run_action_with_retry_impl(self, event: ConsumedEvent) -> None:
        """Internal implementation of action execution with retry."""
        workflow_id = event.agg_id
        event_number = event.event_no

        activity: Ae | None
        async with self._session_maker() as s:
            activity = await self._get_activity(s, workflow_id, event_number)

        if activity is None:
            raise RuntimeError(
                f"Activity for {workflow_id}:{event_number} not found; "
                "expected to exist after synchronous create"
            )

        retry_count = 0
        last_exception: Exception | None = None

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
                        runner_id=getattr(event, "reader_name", None),
                    )

                context = ActionContext(
                    workflow_id=workflow_id,
                    event_number=event_number,
                    checkpoint=activity.checkpoint.copy(),  # Copy to allow mutation
                    retry_count=retry_count,
                    retry_policy=activity.retry_policy.model_copy(),
                )

                # Execute the action (with optional global timeout; act_on can also yield ActionTimeout)
                # act_on is an async generator yielding commands, CheckpointYield, and optionally ActionTimeout
                try:

                    async def consume_commands() -> int:
                        gen = self._adapter.act_on(event, context)
                        try:
                            return await self._consume_action_generator(
                                gen,
                                workflow_id,
                                event_number,
                                context,
                            )
                        finally:
                            await gen.aclose()

                    if self._action_timeout:
                        yielded = await asyncio.wait_for(
                            consume_commands(),
                            timeout=self._action_timeout.total_seconds(),
                        )
                    else:
                        yielded = await consume_commands()
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
                    activity.checkpoint = context.checkpoint
                    activity.retry_policy = context.retry_policy
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

                if yielded == 0:
                    raise EmptyActionError(
                        f"Adapter act_on yielded zero items for "
                        f"{workflow_id}:{event_number} "
                        f"({type(event.event).__name__}); refusing to mark completed."
                    )

                # Action completed successfully - mark as completed after command processing
                async with self._session_maker() as s:
                    marked = await self._mark_action_completed(
                        s, workflow_id, event_number, result=None
                    )

                if marked:
                    logger.info(
                        f"Action completed for {workflow_id}:{event_number} "
                        f"(retry_count={retry_count})"
                    )
                else:
                    logger.info(
                        f"Action completion not applied for {workflow_id}:{event_number} "
                        f"(activity no longer active; likely cancelled)"
                    )
                return

            except asyncio.CancelledError:
                raise  # Propagate; do not retry

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
                else:
                    delay = activity.retry_policy.backoff_min.total_seconds()
                await asyncio.sleep(delay)

        # All retries exhausted
        if last_exception is None:
            last_exception = RuntimeError("Action failed after all retries")
        async with self._session_maker() as s:
            marked = await self._mark_action_failed(
                s, workflow_id, event_number, last_exception
            )
        if marked:
            logger.error(
                f"Action failed permanently for {workflow_id}:{event_number} "
                f"after {activity.retry_policy.max_retries + 1} attempts"
            )
        else:
            logger.info(
                f"Permanent failure not recorded for {workflow_id}:{event_number} "
                f"(activity no longer active; likely cancelled)"
            )
        if marked and self._on_action_failed and last_exception is not None:
            try:
                await self._on_action_failed(workflow_id, event_number, last_exception)
            except Exception as e:
                logger.exception(
                    f"on_action_failed callback failed for {workflow_id}:{event_number}: {e}"
                )

    async def _process_action_item(
        self,
        item: Any,
        workflow_id: str,
        event_number: int,
        context: ActionContext,
    ) -> None:
        """Process one item yielded from act_on (CheckpointYield or command)."""
        if isinstance(item, CheckpointYield):
            context.checkpoint.update(item.data)
            if item.save_now:
                async with self._session_maker() as s:
                    await self._save_checkpoint(
                        s, workflow_id, event_number, context.checkpoint
                    )
        else:
            await self._repo.process_command(workflow_id, item)

    async def _consume_action_generator(
        self,
        gen: Any,
        workflow_id: str,
        event_number: int,
        context: ActionContext,
    ) -> int:
        """Consume act_on async generator; apply ActionTimeout via asyncio.wait_for.

        Returns the number of non-ActionTimeout items yielded (commands + checkpoints).
        """
        count = 0
        while True:
            try:
                item = await gen.__anext__()
            except StopAsyncIteration:
                return count
            if isinstance(item, ActionTimeout):
                count += await asyncio.wait_for(
                    self._consume_action_generator(
                        gen, workflow_id, event_number, context
                    ),
                    timeout=item.seconds,
                )
            else:
                await self._process_action_item(
                    item, workflow_id, event_number, context
                )
                count += 1

    async def _recovery_loop(self):
        """Periodically check for interrupted actions and resume them."""
        while self._running:
            try:
                await self._recover_interrupted_actions()
            except Exception as e:
                logger.exception(f"Error in action recovery loop: {e}")

            await asyncio.sleep(self._recovery_interval.total_seconds())

    async def _recover_interrupted_actions(self):
        """Find and resume interrupted actions.

        - ``pending``: row exists but execution never started (e.g. crash after insert).
        - ``running`` / ``retrying``: stale ``last_attempt_at`` (process died mid-run).

        Active ``running`` / ``retrying`` rows with a recent ``last_attempt_at`` are left
        alone to avoid racing another live runner.

        Uses SELECT … FOR UPDATE SKIP LOCKED so concurrent workers claim disjoint sets
        of rows (Fix 3).

        Activities belonging to a different workflow type are silently skipped —
        the row lock is released on commit so the correct runner can claim it on
        its next recovery cycle.  This prevents a runner from permanently failing
        activities that belong to another runner type (Fix 5).

        Validates to_be_act_on before re-firing; marks FAILED when no handler is
        registered (Fix 4).
        """
        threshold = datetime.datetime.now(
            datetime.timezone.utc
        ) - self._recovery_stale_after

        stale_running_or_retrying = and_(
            self._db_activity_model.status.in_(
                [ActionStatus.RUNNING.value, ActionStatus.RETRYING.value]
            ),
            or_(
                self._db_activity_model.last_attempt_at < threshold,
                self._db_activity_model.last_attempt_at.is_(None),
            ),
        )

        events_to_fire: list[ConsumedEvent] = []

        async with self._session_maker() as s:
            result = await s.execute(
                select(self._db_activity_model)
                .where(
                    or_(
                        self._db_activity_model.status == ActionStatus.PENDING.value,
                        stale_running_or_retrying,
                    )
                )
                .with_for_update(skip_locked=True)
            )
            interrupted_activities = result.scalars().all()

            for activity in interrupted_activities:
                # Reconstruct the event from the database within the same transaction
                event_result = await s.execute(
                    select(self._db_event_model)
                    .where(self._db_event_model.workflow_id == activity.workflow_id)
                    .where(
                        self._db_event_model.workflow_version == activity.event_number
                    )
                    .limit(1)
                )
                event_row = event_result.scalar_one_or_none()

                if event_row is None:
                    continue

                event = ConsumedEvent(
                    workflow_id=activity.workflow_id,
                    event_no=activity.event_number,
                    event=event_row.body,
                    global_id=event_row.global_id,
                    at=event_row.at,
                    workflow_type=getattr(
                        event_row, "workflow_type", self._repo._workflow_type
                    ),
                    event_type=getattr(event_row, "event_type", ""),
                    metadata_=getattr(event_row, "metadata_", None) or {},
                    reader_name=self._runner_name,
                )

                # Fix 4: skip activities whose workflow_type does not belong to this
                # runner.  When multiple runner types share one activity table each
                # runner must only process its own type; activities belonging to other
                # runners are released (lock released on commit) so the correct runner
                # can pick them up on its next recovery cycle.
                event_workflow_type = getattr(event_row, "workflow_type", None)
                if (
                    event_workflow_type is not None
                    and event_workflow_type != self._repo._workflow_type
                ):
                    logger.debug(
                        f"Recovery: skipping activity for workflow_type "
                        f"'{event_workflow_type}' (this runner handles "
                        f"'{self._repo._workflow_type}'); "
                        f"({activity.workflow_id}:{activity.event_number})"
                    )
                    continue

                # Fix 4b: refuse to re-fire events whose handler is no longer registered
                if not self._adapter.to_be_act_on(event):
                    error_msg = (
                        f"no handler registered for event type "
                        f"'{type(event.event).__name__}' at recovery time; "
                        f"marking activity as failed"
                    )
                    logger.warning(
                        f"Recovery: {error_msg} "
                        f"({activity.workflow_id}:{activity.event_number})"
                    )
                    await s.execute(
                        update(self._db_activity_model)
                        .where(
                            self._db_activity_model.workflow_id
                            == activity.workflow_id
                        )
                        .where(
                            self._db_activity_model.event_number
                            == activity.event_number
                        )
                        .values(
                            status=ActionStatus.FAILED.value,
                            finished_at=datetime.datetime.now(datetime.timezone.utc),
                            error_type="RecoveryHandlerMissing",
                            error_message=error_msg,
                        )
                    )
                    continue

                events_to_fire.append(event)

            # Commit releases the FOR UPDATE row locks
            await s.commit()

        for event in events_to_fire:
            logger.info(
                f"Recovering interrupted action for {event.workflow_id}:{event.event_no}"
            )
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
            runner_id=getattr(event, "reader_name", None),
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
        runner_id: str | None = None,
    ):
        """Update activity status."""
        values = {
            "status": status.value,
            "retry_count": retry_count,
            "last_attempt_at": datetime.datetime.now(datetime.timezone.utc),
        }
        if runner_id is not None:
            values["runner_id"] = runner_id
        await s.execute(
            update(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
            .values(**values)
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
        result: bytes | None = None,
    ) -> bool:
        """Mark an action as completed.

        Only updates rows still in an active execution state so a concurrent cancel
        cannot be overwritten by completion.
        """
        values = {
            "status": ActionStatus.COMPLETED.value,
            "finished_at": datetime.datetime.now(datetime.timezone.utc),
        }
        if result:
            values["result"] = result

        res = await s.execute(
            update(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
            .where(
                self._db_activity_model.status.in_(
                    [ActionStatus.RUNNING.value, ActionStatus.RETRYING.value]
                )
            )
            .values(**values)
        )
        await s.commit()
        return (res.rowcount or 0) > 0

    async def _save_checkpoint(
        self, s: AsyncSession, workflow_id: str, event_number: int, checkpoint: dict
    ):
        """Save checkpoint data for an action and refresh last_attempt_at.

        Bumping last_attempt_at here keeps actively-checkpointing attempts
        invisible to the staleness selector in _recover_interrupted_actions,
        which uses last_attempt_at < threshold to detect dead workers.
        """
        await s.execute(
            update(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
            .values(
                checkpoint=checkpoint,
                last_attempt_at=datetime.datetime.now(datetime.timezone.utc),
            )
        )
        await s.commit()

    async def _update_activity_retry_policy(
        self,
        s: AsyncSession,
        workflow_id: str,
        event_number: int,
        retry_policy: RetryPolicy,
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
    ) -> bool:
        """Mark an action as permanently failed.

        Only updates rows still in an active execution state so cancel is not
        overwritten by failure.
        """
        error_type = type(exception).__name__
        res = await s.execute(
            update(self._db_activity_model)
            .where(self._db_activity_model.workflow_id == workflow_id)
            .where(self._db_activity_model.event_number == event_number)
            .where(
                self._db_activity_model.status.in_(
                    [ActionStatus.RUNNING.value, ActionStatus.RETRYING.value]
                )
            )
            .values(
                status=ActionStatus.FAILED.value,
                finished_at=datetime.datetime.now(datetime.timezone.utc),
                error_type=error_type,
                error_message=str(exception),
            )
        )
        await s.commit()
        updated = (res.rowcount or 0) > 0
        if updated and self._metrics is not None and hasattr(
            self._metrics, "record_failed_action"
        ):
            self._metrics.record_failed_action(error_type)
        return updated
