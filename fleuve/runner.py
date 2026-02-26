import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Type

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio.session import AsyncSession

from fleuve.model import (
    Adapter,
    EvActionCancel,
    EvDirectMessage,
    EvDelay,
    EvDelayComplete,
    Workflow,
)
from fleuve.postgres import (
    Activity,
    DelaySchedule,
    ScalingOperation,
    StoredEvent,
    Subscription,
)
from fleuve.repo import AsyncRepo
from fleuve.actions import ActionExecutor
from fleuve.delay import DelayScheduler
from fleuve.stream import ConsumedEvent, Reader, Readers

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token-bucket rate limiter for gating event dispatch.

    Allows ``rate`` events per second on average while tolerating short bursts.
    Calling ``acquire()`` waits until a token is available.

    Usage::

        bucket = TokenBucket(rate=100.0)  # 100 events/s
        async for event in stream.iter_events():
            await bucket.acquire()
            ...
    """

    def __init__(self, rate: float) -> None:
        if rate <= 0:
            raise ValueError("rate must be > 0")
        self._rate = rate
        self._tokens: float = rate
        self._last_check: float = asyncio.get_event_loop().time()

    async def acquire(self) -> None:
        while True:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_check
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last_check = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            sleep_time = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(sleep_time)


class InflightTracker:
    """Tracks in-flight event processing for safe checkpointing.

    Maintains a sliding window of dispatched event global_ids and their
    completion status.  The committable offset is the highest *contiguous*
    completed global_id from the bottom (TCP receive-window semantics).
    """

    def __init__(self) -> None:
        self._pending: dict[int, bool] = {}
        self._committed: int = 0

    def register(self, global_id: int) -> None:
        self._pending[global_id] = False

    def mark_done(self, global_id: int) -> None:
        self._pending[global_id] = True
        self._advance()

    def _advance(self) -> None:
        for gid in sorted(self._pending):
            if self._pending[gid]:
                self._committed = gid
                del self._pending[gid]
            else:
                break

    @property
    def committable_offset(self) -> int:
        return self._committed

    @property
    def size(self) -> int:
        return len(self._pending)


@dataclass
class CachedSubscription:
    """Cached subscription data for fast matching.

    This avoids database queries for every event by keeping subscriptions in memory.
    """

    workflow_id: str  # The subscribing workflow
    subscribed_to_workflow: str  # "*" or specific workflow_id
    subscribed_to_event_type: str  # "*" or specific event type
    tags: list[str]  # ANY match (OR logic)
    tags_all: list[str]  # ALL match (AND logic)

    def matches_event(
        self,
        event_workflow_id: str,
        event_type: str,
        event_tags: set[str],
        workflow_tags: set[str],
    ) -> bool:
        """Check if this subscription matches the event.

        Args:
            event_workflow_id: The workflow ID that emitted the event
            event_type: The type of the event
            event_tags: Tags from the event's metadata
            workflow_tags: Tags from the workflow's metadata

        Returns:
            True if this subscription matches the event
        """
        all_tags = event_tags | workflow_tags

        # Check workflow_id match
        if (
            self.subscribed_to_workflow != "*"
            and self.subscribed_to_workflow != event_workflow_id
        ):
            return False

        # Check event_type match
        if (
            self.subscribed_to_event_type != "*"
            and self.subscribed_to_event_type != event_type
        ):
            return False

        # Check tags (ANY match - OR logic)
        if self.tags and not any(tag in all_tags for tag in self.tags):
            return False

        # Check tags_all (ALL match - AND logic)
        if self.tags_all and not all(tag in all_tags for tag in self.tags_all):
            return False

        return True


class SideEffects:
    def __init__(
        self,
        action_executor: ActionExecutor,
        delay_scheduler: DelayScheduler,
    ) -> None:
        self.action_executor = action_executor
        self.delay_scheduler = delay_scheduler

    @classmethod
    def make_side_effects(
        cls,
        workflow_type: Type[Workflow],
        adapter: Adapter,
        session_maker: async_sessionmaker[AsyncSession],
        db_activity_model: Type[Activity],
        db_event_model: Type[StoredEvent],
        db_delay_schedule_model: Type[DelaySchedule],
        repo: AsyncRepo,
        action_executor_kwargs: dict[str, Any] = {},
        delay_scheduler_kwargs: dict[str, Any] = {},
        runner_name: str | None = None,
    ) -> "SideEffects":
        # Merge delay_scheduler_kwargs with required parameters
        delay_kwargs = {
            "workflow_type": workflow_type.name(),
            "db_event_model": db_event_model,
            "db_delay_schedule_model": db_delay_schedule_model,
            **delay_scheduler_kwargs,
        }

        return SideEffects(
            action_executor=ActionExecutor(
                session_maker=session_maker,
                adapter=adapter,
                db_activity_model=db_activity_model,
                db_event_model=db_event_model,
                repo=repo,
                runner_name=runner_name,
                **action_executor_kwargs,
            ),
            delay_scheduler=DelayScheduler(
                session_maker=session_maker,
                **delay_kwargs,
            ),
        )

    async def __aenter__(self):
        """Async context manager entry: start action executor and delay scheduler."""
        try:
            await self.action_executor.__aenter__()
        except Exception:
            # If action_executor fails to start, we don't need to clean it up
            raise
        try:
            await self.delay_scheduler.__aenter__()
        except Exception:
            # If delay_scheduler fails to start, clean up action_executor
            await self.action_executor.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit: stop action executor and delay scheduler."""
        # Exit in reverse order
        delay_exit = False
        action_exit = False
        try:
            delay_exit = await self.delay_scheduler.__aexit__(exc_type, exc_val, exc_tb)
        except Exception:
            # Continue with action_executor cleanup even if delay_scheduler cleanup fails
            pass
        try:
            action_exit = await self.action_executor.__aexit__(
                exc_type, exc_val, exc_tb
            )
        except Exception:
            pass
        # Return True if any suppressed the exception
        return delay_exit or action_exit

    async def maybe_act_on(self, event: ConsumedEvent):
        if event.event_type == "action_cancel" or (
            not event.event_type and isinstance(event.event, EvActionCancel)
        ):
            await self.action_executor.cancel_workflow_actions(
                event.workflow_id,
                event_numbers=event.event.event_numbers,
            )
            return
        if isinstance(event.event, EvDelay):
            await self.delay_scheduler.register_delay(
                workflow_id=event.workflow_id,
                delay_event=event.event,
                event_version=event.event_no,
            )
        if self.action_executor.to_be_act_on(event):
            await self.action_executor.execute_action(event)


class WorkflowsRunner:

    def __init__(
        self,
        repo: AsyncRepo,
        readers: Readers,
        workflow_type: Type[Workflow],
        session_maker: async_sessionmaker[AsyncSession],
        db_sub_type: Type[Subscription],
        se: SideEffects,
        wf_id_rule: Callable[[str], bool] | None = None,
        name: str | None = None,
        db_scaling_operation_model: Type[ScalingOperation] | None = None,
        scaling_check_interval: int = 50,  # Check every N events
        external_message_consumer: Any | None = None,
        max_inflight: int = 1,
        max_events_per_second: float | None = None,
    ) -> None:
        self.name = name or f"{workflow_type.name()}_runner"
        self.wf_id_rule = wf_id_rule
        self.session_maker = session_maker
        self.repo = repo
        self.stream = readers.reader(
            reader_name=self.name,
            event_types=None,  # Read all event types
        )
        self.db_sub_type = db_sub_type
        self.workflow_type = workflow_type
        self.se = se
        self.db_scaling_operation_model = db_scaling_operation_model
        self.scaling_check_interval = scaling_check_interval
        self._events_processed = 0
        self._target_offset_for_scaling: int | None = None
        self.external_message_consumer = external_message_consumer
        self._max_inflight = max(1, max_inflight)
        self._token_bucket: TokenBucket | None = (
            TokenBucket(max_events_per_second)
            if max_events_per_second is not None and max_events_per_second > 0
            else None
        )

        # Subscription cache: workflow_id -> list of CachedSubscription
        # This eliminates database queries for every event
        self._subscription_cache: dict[str, list[CachedSubscription]] = {}
        self._cache_initialized = False
        self._has_tag_subscriptions = False

    async def __aenter__(self):
        """Async context manager entry: start side effects, stream reader, and optional external message consumer."""
        await self.stream.__aenter__()
        await self.se.__aenter__()

        # Load subscription cache
        await self._load_subscription_cache()

        if self.external_message_consumer is not None:
            await self.external_message_consumer.__aenter__()
            await self.external_message_consumer.start()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit: stop side effects, stream reader, and optional external message consumer."""
        if self.external_message_consumer is not None:
            await self.external_message_consumer.stop()
            await self.external_message_consumer.__aexit__(exc_type, exc_val, exc_tb)
        se_exit = await self.se.__aexit__(exc_type, exc_val, exc_tb)
        stream_exit = await self.stream.__aexit__(exc_type, exc_val, exc_tb)
        return se_exit or stream_exit

    async def _load_subscription_cache(self):
        """Load all subscriptions for this workflow type into memory.

        This eliminates the need for database queries on every event.
        The cache is kept consistent by updating it whenever subscriptions change
        through process_command() or create_new().
        """
        logger.info(f"Loading subscription cache for {self.workflow_type.name()}...")

        async with self.session_maker() as s:
            result = await s.execute(
                select(
                    self.db_sub_type.workflow_id,
                    self.db_sub_type.subscribed_to_workflow,
                    self.db_sub_type.subscribed_to_event_type,
                    self.db_sub_type.tags,
                    self.db_sub_type.tags_all,
                ).where(self.db_sub_type.workflow_type == self.workflow_type.name())
            )

            self._subscription_cache.clear()
            count = 0

            for row in result.fetchall():
                subscription = CachedSubscription(
                    workflow_id=row.workflow_id,
                    subscribed_to_workflow=row.subscribed_to_workflow,
                    subscribed_to_event_type=row.subscribed_to_event_type,
                    tags=row.tags or [],
                    tags_all=row.tags_all or [],
                )

                # Index by subscribing workflow_id for efficient updates
                if subscription.workflow_id not in self._subscription_cache:
                    self._subscription_cache[subscription.workflow_id] = []
                self._subscription_cache[subscription.workflow_id].append(subscription)
                count += 1

        self._cache_initialized = True
        self._has_tag_subscriptions = any(
            sub.tags or sub.tags_all
            for subs in self._subscription_cache.values()
            for sub in subs
        )
        if hasattr(self.stream, "fetch_metadata"):
            self.stream.fetch_metadata = self._has_tag_subscriptions
        logger.info(
            f"Loaded {count} subscriptions for {len(self._subscription_cache)} workflows "
            f"into cache (tag filtering: {self._has_tag_subscriptions})"
        )

    async def run(self):
        inflight = InflightTracker()
        pending: set[asyncio.Task] = set()
        wf_gates: dict[str, asyncio.Event] = {}

        async for event in self.stream.iter_events():
            # Check for scaling operation periodically
            if self.db_scaling_operation_model:
                self._events_processed += 1
                if self._events_processed >= self.scaling_check_interval:
                    self._events_processed = 0
                    target_offset = await self._check_scaling_operation()
                    if target_offset is not None:
                        self._target_offset_for_scaling = target_offset
                        self.stream.set_stop_at_offset(target_offset)
                        logger.info(
                            f"Scaling operation detected for {self.workflow_type.name()}, "
                            f"target_offset={target_offset}. Runner will stop at this offset."
                        )

            # Rate limiting: throttle read speed if requested
            if self._token_bucket is not None:
                await self._token_bucket.acquire()

            # Backpressure: wait until an inflight slot is available
            while len(pending) >= self._max_inflight:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                self._reap_completed(done, inflight)

            # Routing in the main loop preserves event order for predecessor chains
            cmd = self.workflow_type.event_to_cmd(event)
            workflow_ids: list[str] = []
            if cmd:
                workflow_ids = await self.workflows_to_notify(event)

            # Build per-workflow ordering chain
            predecessors: dict[str, asyncio.Event | None] = {}
            completions: dict[str, asyncio.Event] = {}
            for wf_id in workflow_ids:
                predecessors[wf_id] = wf_gates.get(wf_id)
                gate = asyncio.Event()
                wf_gates[wf_id] = gate
                completions[wf_id] = gate

            inflight.register(event.global_id)
            task = asyncio.create_task(
                self._process_event(
                    event, cmd, workflow_ids, predecessors, completions
                ),
                name=f"process_event:{event.global_id}",
            )
            pending.add(task)

            # Check if we've reached target_offset after reading event
            if (
                self._target_offset_for_scaling is not None
                and self.stream.last_read_event_g_id is not None
                and self.stream.last_read_event_g_id >= self._target_offset_for_scaling
            ):
                logger.info(
                    f"Runner {self.name} reached target_offset {self._target_offset_for_scaling} "
                    f"for scaling, stopping gracefully"
                )
                break

        # Drain remaining in-flight tasks
        if pending:
            done, _ = await asyncio.wait(pending)
            self._reap_completed(done, inflight)

    async def _process_event(
        self,
        event: ConsumedEvent,
        cmd: Any | None,
        workflow_ids: list[str],
        predecessors: dict[str, "asyncio.Event | None"],
        completions: dict[str, asyncio.Event],
    ) -> int:
        """Process a single event and return its global_id."""
        if self.to_be_act_on(event):
            await self.se.maybe_act_on(event)
        if cmd and workflow_ids:
            async with asyncio.TaskGroup() as tg:
                for wf_id in workflow_ids:
                    tg.create_task(
                        self._ordered_process(
                            wf_id, cmd, predecessors.get(wf_id), completions[wf_id]
                        ),
                        name=f"{self.repo.__class__.__name__} processing {cmd} for {wf_id} from {event.workflow_id}:{event.event_no}",
                    )
        return event.global_id

    async def _ordered_process(
        self,
        workflow_id: str,
        cmd: Any,
        predecessor: "asyncio.Event | None",
        completion: asyncio.Event,
    ) -> None:
        """Await predecessor, run process_command, then signal completion."""
        try:
            if predecessor is not None:
                await predecessor.wait()
            result = await self.repo.process_command(workflow_id, cmd)
            if isinstance(result, tuple):
                stored_state, events = result
                await self._update_subscription_cache(
                    workflow_id, stored_state.state.subscriptions
                )
        finally:
            completion.set()

    def _reap_completed(
        self, done: set[asyncio.Task], inflight: InflightTracker
    ) -> None:
        for task in done:
            global_id = task.result()  # re-raises if the task failed
            inflight.mark_done(global_id)
        self.stream.committed_offset = inflight.committable_offset

    async def _check_scaling_operation(self) -> int | None:
        """Check for active scaling operation and return target_offset if found."""
        if not self.db_scaling_operation_model:
            return None

        async with self.session_maker() as s:
            result = await s.execute(
                select(
                    self.db_scaling_operation_model.target_offset,
                    self.db_scaling_operation_model.status,
                )
                .where(
                    self.db_scaling_operation_model.workflow_type
                    == self.workflow_type.name()
                )
                .where(
                    self.db_scaling_operation_model.status.in_(
                        ["pending", "synchronizing"]
                    )
                )
                .limit(1)
            )
            row = result.fetchone()
            if row:
                return row.target_offset
        return None

    def to_be_act_on(self, event: ConsumedEvent) -> bool:
        if event.workflow_type != self.workflow_type.name():
            return False
        return self.wf_id_rule is None or self.wf_id_rule(event.workflow_id)

    async def workflows_to_notify(self, event: ConsumedEvent) -> list[str]:
        out = set[str]()

        if event.workflow_type == self.workflow_type.name():
            if event.event_type == "delay_complete" or (
                not event.event_type and isinstance(event.event, EvDelayComplete)
            ):
                out.add(event.workflow_id)
            elif isinstance(event.event, EvDirectMessage):
                out.add(event.event.target_workflow_id)

        for sub in await self.find_subscriptions(event):
            out.add(sub)

        if self.wf_id_rule:
            return sorted((i for i in out if self.wf_id_rule(i)))

        return sorted(out)

    async def find_subscriptions(self, event: ConsumedEvent) -> list[str]:
        """Find workflows that should be notified about this event (cached version).

        Uses in-memory cache for fast lookups. Falls back to database if cache
        is not initialized.

        Workflow tags are read directly from event metadata (injected at creation time)
        for maximum performance - no database queries needed.
        """
        event_type = event.event_type or getattr(event.event, "type", None)
        if event_type is None:
            return []

        if not self._cache_initialized:
            # Fallback to database if cache not ready (shouldn't happen)
            logger.warning(
                "Subscription cache not initialized, falling back to DB query"
            )
            return await self._find_subscriptions_from_db(event)

        # Get event tags from metadata
        event_tags = set(event.metadata_.get("tags", [])) if event.metadata_ else set()

        # Get workflow tags from event metadata (injected at creation time)
        # This avoids a database query on every event
        workflow_tags = (
            set(event.metadata_.get("workflow_tags", [])) if event.metadata_ else set()
        )

        # Match subscriptions from cache
        matched_workflows = set()

        # Iterate through all cached subscriptions
        for workflow_id, subscriptions in self._subscription_cache.items():
            for sub in subscriptions:
                if sub.matches_event(
                    event.workflow_id, event_type, event_tags, workflow_tags
                ):
                    matched_workflows.add(workflow_id)
                    break  # No need to check other subscriptions for this workflow

        return list(matched_workflows)

    async def _find_subscriptions_from_db(self, event: ConsumedEvent) -> list[str]:
        """Fallback: Find subscriptions from database (original implementation).

        This is used when the cache is not initialized or during testing.
        """
        event_type = event.event_type or getattr(event.event, "type", None)
        if event_type is None:
            return []

        # Get event tags from metadata
        event_tags = event.metadata_.get("tags", []) if event.metadata_ else []

        # Get workflow tags from event metadata (should be injected at creation)
        # Fall back to database query only if not present in metadata
        workflow_tags = (
            event.metadata_.get("workflow_tags", []) if event.metadata_ else []
        )
        if not workflow_tags:
            workflow_tags = await self.repo.get_workflow_tags(event.workflow_id)

        # Combine all available tags
        all_tags = set(event_tags) | set(workflow_tags)

        async with self.session_maker() as s:
            # Select subscriptions with their tag filters
            result = await s.execute(
                select(
                    self.db_sub_type.workflow_id,
                    self.db_sub_type.tags,
                    self.db_sub_type.tags_all,
                )
                .where(
                    or_(
                        and_(
                            self.db_sub_type.subscribed_to_event_type.in_(
                                ["*", event_type]
                            ),
                            self.db_sub_type.subscribed_to_workflow
                            == event.workflow_id,
                        ),
                        and_(
                            self.db_sub_type.subscribed_to_event_type
                            == event_type,
                            self.db_sub_type.subscribed_to_workflow.in_(
                                ["*", event.workflow_id]
                            ),
                        ),
                    )
                )
                .where(
                    self.db_sub_type.workflow_type == self.workflow_type.name(),
                )
                .distinct()
            )

            # Filter subscriptions by tag matching logic
            matched_workflows = []
            for workflow_id, sub_tags, sub_tags_all in result:
                # Check if subscription's tag filters match
                if sub_tags:
                    # If tags specified, check ANY match (OR)
                    if not any(tag in all_tags for tag in sub_tags):
                        continue

                if sub_tags_all:
                    # If tags_all specified, check ALL match (AND)
                    if not all(tag in all_tags for tag in sub_tags_all):
                        continue

                matched_workflows.append(workflow_id)

            return matched_workflows

    async def _update_subscription_cache(self, workflow_id: str, subscriptions: list):
        """Update cache when subscriptions change for a workflow.

        This is called after process_command() or create_new() to keep the cache
        in sync with the database.

        Args:
            workflow_id: The workflow whose subscriptions changed
            subscriptions: List of Sub objects from the workflow state
        """
        if not self._cache_initialized:
            return

        # Clear old subscriptions for this workflow
        self._subscription_cache.pop(workflow_id, None)

        # Add new subscriptions (internal event subs only; external topic subs are in a separate table)
        if subscriptions:
            cached_subs = []
            for sub in subscriptions:
                cached_subs.append(
                    CachedSubscription(
                        workflow_id=workflow_id,
                        subscribed_to_workflow=sub.workflow_id,
                        subscribed_to_event_type=sub.event_type,
                        tags=sub.tags,
                        tags_all=sub.tags_all,
                    )
                )
            self._subscription_cache[workflow_id] = cached_subs
            if not self._has_tag_subscriptions and any(
                s.tags or s.tags_all for s in cached_subs
            ):
                self._has_tag_subscriptions = True
                if hasattr(self.stream, "fetch_metadata"):
                    self.stream.fetch_metadata = True
            logger.debug(
                f"Updated subscription cache for workflow {workflow_id}: "
                f"{len(subscriptions)} subscriptions"
            )
        else:
            logger.debug(f"Removed subscriptions from cache for workflow {workflow_id}")
