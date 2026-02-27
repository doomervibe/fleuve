import json
import pickle
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any, Generic, Type, TypeVar, cast
from uuid import uuid4

from nats.aio.client import Client as NATS
from nats.js.api import KeyValueConfig
from nats.js.errors import BucketNotFoundError, KeyNotFoundError
from pydantic import BaseModel, TypeAdapter
import logging

from sqlalchemy import CursorResult, delete, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing_extensions import Self

from fleuve.delay import next_cron_fire
from fleuve.model import (
    AlreadyExists,
    EvContinueAsNew,
    EvExternalSubscriptionAdded,
    EvExternalSubscriptionRemoved,
    EvScheduleAdded,
    EvScheduleRemoved,
    EvSubscriptionAdded,
    EvSubscriptionRemoved,
    EvSystemCancel,
    EvSystemPause,
    EvSystemResume,
    Rejection,
    Schedule,
    StateBase,
    Workflow,
)
from fleuve.postgres import DelaySchedule, Snapshot, StoredEvent, Subscription
from fleuve.tracing import _NoopTracer

logger = logging.getLogger(__name__)

# Define type variables for generic typing
C = TypeVar("C", bound=BaseModel)  # Command type
E = TypeVar("E", bound=BaseModel)  # Event type
Wf = TypeVar("Wf", bound=Workflow)  # Workflow type
S = TypeVar("S", bound=StateBase)  # State type
Se = TypeVar("Se", bound=StoredEvent)  # StoredEvent subclass type

# Callable run inside the same transaction as event insertion to update
# denormalized/auxiliary DB data. Args: (session, workflow_id, old_state, new_state, events).
# Must not commit; runs after subscription handling and before event insert.
SyncDbHandler = Callable[[AsyncSession, str, Any, Any, list[Any]], Awaitable[None]]


class StoredState(BaseModel, Generic[S]):
    id: str
    version: int
    state: S

    class Config:
        arbitrary_types_allowed = True


class EuphemeralStorage(Generic[S, E], ABC):
    @abstractmethod
    async def put_state(self, new: StoredState[S]):
        pass

    @abstractmethod
    async def get_state(self, workflow_id: str) -> StoredState[S] | None:
        pass

    @abstractmethod
    async def remove_state(self, workflow_id: str):
        pass


class EuphStorageNATS(EuphemeralStorage[S, E]):
    def __init__(
        self,
        c: NATS,
        bucket: str,
        s: Type[S],
    ) -> None:
        self._c = c
        self._bucket_name = bucket
        self._bucket: Any = None
        self._js: Any = None
        self._s = s

    async def __aenter__(self) -> Self:
        js = self._c.jetstream()
        try:
            self._bucket = await js.key_value(self._bucket_name)
        except BucketNotFoundError:
            self._bucket = await js.create_key_value(
                KeyValueConfig(bucket=self._bucket_name)
            )
        self._js = js
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self._bucket = None
        if hasattr(self, "_js"):
            self._js = None
        return False

    async def put_state(self, new: StoredState[S]):
        assert self._bucket
        await self._bucket.put(str(new.id), pickle.dumps(new))

    async def get_state(self, workflow_id: str) -> StoredState[S] | None:
        assert self._bucket
        try:
            entry = await self._bucket.get(str(workflow_id))
        except KeyNotFoundError:
            return None
        assert entry.value is not None
        return cast(StoredState[S], pickle.loads(entry.value))

    async def remove_state(self, workflow_id: str):
        assert self._bucket
        try:
            await self._bucket.delete(str(workflow_id))
        except KeyNotFoundError:
            return


class InProcessEuphemeralStorage(EuphemeralStorage[S, E]):
    """In-process LRU cache for workflow state.

    Holds hydrated StoredState objects in a bounded OrderedDict.
    On cache hit, returns the Python object directly with zero
    serialization/deserialization overhead. Works well with partitioned
    runners where each runner handles a fixed subset of workflow IDs.
    """

    def __init__(self, max_size: int = 10_000) -> None:
        self._cache: OrderedDict[str, StoredState[S]] = OrderedDict()
        self._max_size = max_size

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self._cache.clear()
        return False

    async def get_state(self, workflow_id: str) -> StoredState[S] | None:
        state = self._cache.get(workflow_id)
        if state is not None:
            self._cache.move_to_end(workflow_id)
        return state

    async def put_state(self, new: StoredState[S]):
        self._cache[new.id] = new
        self._cache.move_to_end(new.id)
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    async def remove_state(self, workflow_id: str):
        self._cache.pop(workflow_id, None)


class TieredEuphemeralStorage(EuphemeralStorage[S, E]):
    """Two-tier ephemeral storage: L1 in-process cache + L2 NATS KV.

    ``get_state`` tries L1 first (zero cost), then L2 (pickle + network).
    ``put_state`` writes to both tiers so L1 is always warm after a write.
    """

    def __init__(
        self,
        l1: InProcessEuphemeralStorage,
        l2: EuphStorageNATS,
    ) -> None:
        self._l1 = l1
        self._l2: EuphStorageNATS[Any, Any] = l2

    async def __aenter__(self) -> Self:
        await self._l1.__aenter__()
        await self._l2.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        r1 = await self._l1.__aexit__(exc_type, exc, tb)
        r2 = await self._l2.__aexit__(exc_type, exc, tb)
        return r1 or r2

    async def get_state(self, workflow_id: str) -> StoredState[S] | None:
        state = await self._l1.get_state(workflow_id)
        if state is not None:
            return state
        state = await self._l2.get_state(workflow_id)
        if state is not None:
            await self._l1.put_state(state)
        return state

    async def put_state(self, new: StoredState[S]):
        await self._l1.put_state(new)
        await self._l2.put_state(new)

    async def remove_state(self, workflow_id: str):
        await self._l1.remove_state(workflow_id)
        await self._l2.remove_state(workflow_id)


class WorkflowNotFound(Exception):
    def __init__(self, id, workflow_type, *args: object) -> None:
        self.agg_id = id
        self.workflow_type = workflow_type
        super().__init__(
            f"Workflow {id} of type {workflow_type} could not be found in the repo"
        )


class AsyncRepo(Generic[C, E, Wf, Se]):
    """Repository for workflow commands and event persistence.

    Optional sync_db: async (session, workflow_id, old_state, new_state, events)
    -> None. Runs in the same transaction as event insertion (after subscription
    handling, before event insert). Use for strongly consistent denormalized or
    auxiliary DB updates. Must not commit inside the handler.
    """

    db_event_model: Type[Se]
    model: Type[Wf]

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        es: EuphemeralStorage,
        model: Type[Wf],
        db_event_model: Type[Se],
        db_sub_model: Type[Subscription],
        db_workflow_metadata_model: Type[Any] | None = None,
        db_external_sub_model: Type[Any] | None = None,
        sync_db: SyncDbHandler | None = None,
        adapter: Any | None = None,
        db_snapshot_model: Type[Snapshot] | None = None,
        snapshot_interval: int = 0,
        db_delay_schedule_model: Type[DelaySchedule] | None = None,
        db_search_attributes_model: Type[Any] | None = None,
        namespace: str | None = None,
        tracer: Any = None,
        trust_cache: bool = False,
    ) -> None:
        self._workflow_type = model.name()
        self._db_delay_schedule_model = db_delay_schedule_model
        self._db_search_attributes_model = db_search_attributes_model
        self._namespace = namespace  # None = default namespace (no filtering)
        self._tracer = tracer or _NoopTracer()
        self._uuid = uuid4
        self._es = es
        self._trust_cache = trust_cache
        self._session_maker: async_sessionmaker[AsyncSession] = session_maker
        self.model = model
        self.db_event_model = db_event_model
        self.db_sub_model = db_sub_model
        self.db_workflow_metadata_model = db_workflow_metadata_model
        self.db_external_sub_model = db_external_sub_model
        self._db_snapshot_model = db_snapshot_model
        self._snapshot_interval = snapshot_interval
        self._sync_db_handler: SyncDbHandler | None
        if sync_db is not None:
            self._sync_db_handler = sync_db
        elif adapter is not None:

            async def _adapter_sync_db(
                s: AsyncSession, id_: str, old: Any, new: Any, ev: list
            ) -> None:
                await adapter.sync_db(s, id_, old, new, ev)

            self._sync_db_handler = _adapter_sync_db
        else:
            self._sync_db_handler = None

    async def process_command(
        self,
        id: str,
        cmd: C,
    ) -> tuple[StoredState[S], list[E]] | Rejection:
        with self._tracer.span(
            "process_command",
            {"fleuve.workflow_id": id, "fleuve.command_type": type(cmd).__name__},
        ):
            return await self._process_command_impl(id, cmd)

    async def _process_command_impl(
        self,
        id: str,
        cmd: C,
    ) -> tuple[StoredState[S], list[E]] | Rejection:
        while True:
            async with self._session_maker() as s:
                # Acquire a row-level lock on the first event of this workflow's
                # stream to serialize concurrent command processing.
                await s.execute(
                    select(self.db_event_model.global_id)
                    .where(
                        self.db_event_model.workflow_id == id,
                        self.db_event_model.workflow_version == 1,
                    )
                    .with_for_update()
                )

                old: StoredState[S] = await self.get_current_state(s, id)
                lifecycle = getattr(old.state, "lifecycle", "active")
                if lifecycle == "paused":
                    return Rejection(msg="Workflow is paused")
                if lifecycle == "cancelled":
                    return Rejection(msg="Workflow is cancelled")
                events = self.model.decide(old.state, cmd)
                if not events:
                    return old, []
                if isinstance(events, Rejection):
                    return events

                # Evolve the state with the new events
                new_state = self.model.evolve_(old.state, events)

                new_version = old.version + len(events)
                await self._handle_sync_events_from_decide(s, id, old.version, events)

                if self._sync_db_handler:
                    await self._sync_db_handler(s, id, old.state, new_state, events)

                # Inject workflow tags into events for fast access during subscription matching
                await self._inject_workflow_tags_into_events(id, events)

                try:
                    await s.execute(
                        insert(self.db_event_model).values(
                            [
                                {
                                    "workflow_id": id,
                                    "workflow_version": old.version + i,
                                    "event_type": e.type,
                                    "workflow_type": self._workflow_type,
                                    "body": e,
                                    "schema_version": self.model.schema_version(),
                                    **(
                                        {"namespace": self._namespace}
                                        if self._namespace is not None
                                        else {}
                                    ),
                                }
                                for i, e in enumerate(events, start=1)
                            ]
                        )
                    )

                    await self._maybe_snapshot(s, id, new_state, new_version)

                    await s.commit()
                    break
                except IntegrityError:
                    await s.rollback()
                    continue

        new = StoredState(id=id, state=new_state, version=old.version + len(events))
        if self.model.is_final_event(events[-1]):
            await self._es.remove_state(id)
        else:
            await self._es.put_state(new)
        return new, events

    async def _handle_sync_events_from_decide(
        self,
        s: AsyncSession,
        workflow_id: str,
        base_version: int,
        events: list[E],
    ) -> None:
        """Process sync events emitted by user's decide(). No state comparison."""
        from fleuve.model import EvCancelSchedule, EvDelay, EvSystemCancel

        for i, ev in enumerate(events):
            event_version = base_version + i + 1
            if isinstance(ev, EvSubscriptionAdded):
                await self._handle_subscription_added(s, workflow_id, ev)
            elif isinstance(ev, EvSubscriptionRemoved):
                await self._handle_subscription_removed(s, workflow_id, ev)
            elif isinstance(ev, EvExternalSubscriptionAdded):
                await self._handle_external_subscription_added(s, workflow_id, ev)
            elif isinstance(ev, EvExternalSubscriptionRemoved):
                await self._handle_external_subscription_removed(s, workflow_id, ev)
            elif isinstance(ev, EvScheduleAdded):
                await self._handle_schedule_added(s, workflow_id, ev, event_version)
            elif isinstance(ev, EvScheduleRemoved):
                await self._handle_schedule_removed(s, workflow_id, ev)
            elif isinstance(ev, EvDelay) and ev.cron_expression:
                sched = Schedule(
                    id=ev.id,
                    cron_expression=ev.cron_expression,
                    timezone=ev.timezone,
                    next_cmd=ev.next_cmd,
                )
                await self._handle_schedule_added(
                    s, workflow_id, EvScheduleAdded(schedule=sched), event_version
                )
            elif isinstance(ev, EvCancelSchedule):
                await self._handle_schedule_removed(
                    s, workflow_id, EvScheduleRemoved(delay_id=ev.delay_id)
                )
            elif isinstance(ev, EvSystemCancel):
                await self._handle_schedules_cleared(s, workflow_id)

    async def _handle_subscription_added(
        self, s: AsyncSession, workflow_id: str, event: EvSubscriptionAdded
    ) -> None:
        """Insert a single subscription."""
        sub = event.sub
        await s.execute(
            insert(self.db_sub_model).values(
                dict(
                    workflow_id=workflow_id,
                    workflow_type=self._workflow_type,
                    subscribed_to_event_type=sub.event_type,
                    subscribed_to_workflow=sub.workflow_id,
                    tags=sub.tags,
                    tags_all=sub.tags_all,
                )
            )
        )

    async def _handle_subscription_removed(
        self, s: AsyncSession, workflow_id: str, event: EvSubscriptionRemoved
    ) -> None:
        """Delete a single subscription."""
        sub = event.sub
        await s.execute(
            delete(self.db_sub_model)
            .where(self.db_sub_model.workflow_id == workflow_id)
            .where(self.db_sub_model.subscribed_to_event_type == sub.event_type)
            .where(self.db_sub_model.subscribed_to_workflow == sub.workflow_id)
            .where(self.db_sub_model.tags == (sub.tags or []))
            .where(self.db_sub_model.tags_all == (sub.tags_all or []))
        )

    async def _handle_external_subscription_added(
        self, s: AsyncSession, workflow_id: str, event: EvExternalSubscriptionAdded
    ) -> None:
        """Insert a single external subscription."""
        if not self.db_external_sub_model:
            return
        ext = event.sub
        await s.execute(
            insert(self.db_external_sub_model).values(
                dict(
                    workflow_id=workflow_id,
                    workflow_type=self._workflow_type,
                    topic=ext.topic,
                )
            )
        )

    async def _handle_external_subscription_removed(
        self, s: AsyncSession, workflow_id: str, event: EvExternalSubscriptionRemoved
    ) -> None:
        """Delete a single external subscription."""
        if not self.db_external_sub_model:
            return
        await s.execute(
            delete(self.db_external_sub_model)
            .where(self.db_external_sub_model.workflow_id == workflow_id)
            .where(self.db_external_sub_model.topic == event.topic)
        )

    async def _handle_schedule_added(
        self,
        s: AsyncSession,
        workflow_id: str,
        event: EvScheduleAdded,
        event_version: int,
    ) -> None:
        """Insert a single cron schedule."""
        if self._db_delay_schedule_model is None:
            return
        sch = event.schedule
        delay_until = next_cron_fire(sch.cron_expression, sch.timezone)
        if delay_until is None:
            logger.warning(
                "Skipping invalid cron schedule %s for workflow %s",
                sch.id,
                workflow_id,
            )
            return
        await s.execute(
            insert(self._db_delay_schedule_model).values(
                {
                    "workflow_id": workflow_id,
                    "delay_id": sch.id,
                    "workflow_type": self._workflow_type,
                    "delay_until": delay_until,
                    "event_version": event_version,
                    "next_command": sch.next_cmd,
                    "cron_expression": sch.cron_expression,
                    "timezone": sch.timezone,
                }
            )
        )

    async def _handle_schedule_removed(
        self, s: AsyncSession, workflow_id: str, event: EvScheduleRemoved
    ) -> None:
        """Delete a single cron schedule."""
        if self._db_delay_schedule_model is None:
            return
        await s.execute(
            delete(self._db_delay_schedule_model)
            .where(self._db_delay_schedule_model.workflow_id == workflow_id)
            .where(self._db_delay_schedule_model.delay_id == event.delay_id)
            .where(self._db_delay_schedule_model.cron_expression.isnot(None))
        )

    async def _handle_schedules_cleared(
        self, s: AsyncSession, workflow_id: str
    ) -> None:
        """Delete all cron schedules for workflow (EvSystemCancel)."""
        if self._db_delay_schedule_model is None:
            return
        await s.execute(
            delete(self._db_delay_schedule_model)
            .where(self._db_delay_schedule_model.workflow_id == workflow_id)
            .where(self._db_delay_schedule_model.cron_expression.isnot(None))
        )

    async def _maybe_snapshot(
        self, s: AsyncSession, workflow_id: str, state: StateBase, version: int
    ) -> None:
        """Upsert a snapshot if snapshotting is enabled and version hits the interval."""
        if (
            not self._db_snapshot_model
            or self._snapshot_interval <= 0
            or version % self._snapshot_interval != 0
        ):
            return

        stmt = (
            pg_insert(self._db_snapshot_model)
            .values(
                workflow_id=workflow_id,
                workflow_type=self._workflow_type,
                version=version,
                state=state,
            )
            .on_conflict_do_update(
                index_elements=["workflow_id"],
                set_={"version": version, "state": state},
            )
        )
        await s.execute(stmt)
        logger.debug("Snapshot created for %s at version %d", workflow_id, version)

    async def create_new(
        self, cmd: C, id: str, tags: list[str] | None = None
    ) -> StoredState | Rejection:
        events = self.model.decide(None, cmd)
        if isinstance(events, Rejection):
            return events
        if not events:
            return Rejection(msg="Cannot create workflow with no events")

        state = self.model.evolve_(None, events)
        async with self._session_maker() as s:
            try:
                # Store workflow metadata with tags if metadata model is configured
                if self.db_workflow_metadata_model and tags:
                    await s.execute(
                        insert(self.db_workflow_metadata_model).values(
                            dict(
                                workflow_id=id,
                                workflow_type=self._workflow_type,
                                tags=tags,
                            )
                        )
                    )

                await self._handle_sync_events_from_decide(s, id, 0, events)

                if self._sync_db_handler:
                    await self._sync_db_handler(s, id, None, state, events)

                # Inject workflow tags into events for fast access
                for event in events:
                    md: dict[str, Any] = getattr(event, "metadata_", None) or {}
                    md["workflow_tags"] = tags
                    try:
                        event.metadata_ = md  # type: ignore[union-attr]
                    except (AttributeError, ValueError):
                        object.__setattr__(event, "metadata_", md)

                await s.execute(
                    insert(self.db_event_model).values(
                        [
                            {
                                "workflow_id": id,
                                "workflow_version": i,
                                "event_type": e.type,
                                "workflow_type": self._workflow_type,
                                "body": e,
                                "schema_version": self.model.schema_version(),
                                **(
                                    {"namespace": self._namespace}
                                    if self._namespace is not None
                                    else {}
                                ),
                            }
                            for i, e in enumerate(events, start=1)
                        ]
                    )
                )
                await s.commit()
            except IntegrityError:
                # Handle race condition: another process created the workflow
                # between our check and the insert
                await s.rollback()
                return AlreadyExists(msg=f"Workflow with id {id} already exists")

        ss = StoredState(id=id, state=state, version=len(events))
        if self.model.is_final_event(events[-1]):
            return ss

        await self._es.put_state(ss)
        return ss

    async def pause_workflow(
        self, id: str, reason: str = ""
    ) -> StoredState[S] | Rejection:
        """Pause a workflow. Blocks further command processing until resumed."""
        async with self._session_maker() as s:
            old: StoredState[S] = await self.get_current_state(s, id)
            if getattr(old.state, "lifecycle", "active") == "paused":
                return Rejection(msg="Workflow is already paused")
            if getattr(old.state, "lifecycle", "active") == "cancelled":
                return Rejection(msg="Workflow is cancelled")

            ev = EvSystemPause(reason=reason)
            new_state = old.state.model_copy(update={"lifecycle": "paused"})

            await s.execute(
                insert(self.db_event_model).values(
                    {
                        "workflow_id": id,
                        "workflow_version": old.version + 1,
                        "event_type": ev.type,
                        "workflow_type": self._workflow_type,
                        "body": ev,
                        "schema_version": self.model.schema_version(),
                    }
                )
            )
            new_version = old.version + 1
            await self._maybe_snapshot(s, id, new_state, new_version)
            await s.commit()

        new = StoredState(id=id, state=new_state, version=new_version)
        await self._es.put_state(new)
        return new

    async def resume_workflow(self, id: str) -> StoredState[S] | Rejection:
        """Resume a paused workflow."""
        async with self._session_maker() as s:
            old: StoredState[S] = await self.get_current_state(s, id)
            if getattr(old.state, "lifecycle", "active") != "paused":
                return Rejection(msg="Workflow is not paused")

            ev = EvSystemResume()
            new_state = old.state.model_copy(update={"lifecycle": "active"})

            await s.execute(
                insert(self.db_event_model).values(
                    {
                        "workflow_id": id,
                        "workflow_version": old.version + 1,
                        "event_type": ev.type,
                        "workflow_type": self._workflow_type,
                        "body": ev,
                        "schema_version": self.model.schema_version(),
                    }
                )
            )
            new_version = old.version + 1
            await self._maybe_snapshot(s, id, new_state, new_version)
            await s.commit()

        new = StoredState(id=id, state=new_state, version=new_version)
        await self._es.put_state(new)
        return new

    async def cancel_workflow(
        self,
        id: str,
        reason: str = "",
        *,
        action_executor: Any = None,
    ) -> StoredState[S] | Rejection:
        """Cancel a workflow. Blocks further command processing."""
        async with self._session_maker() as s:
            old: StoredState[S] = await self.get_current_state(s, id)
            if getattr(old.state, "lifecycle", "active") == "cancelled":
                return Rejection(msg="Workflow is already cancelled")

            if action_executor is not None:
                await action_executor.cancel_workflow_actions(id)

            if self._db_delay_schedule_model is not None:
                await s.execute(
                    delete(self._db_delay_schedule_model).where(
                        self._db_delay_schedule_model.workflow_id == id
                    )
                )

            ev = EvSystemCancel(reason=reason)
            new_state = old.state.model_copy(update={"lifecycle": "cancelled"})

            await s.execute(
                insert(self.db_event_model).values(
                    {
                        "workflow_id": id,
                        "workflow_version": old.version + 1,
                        "event_type": ev.type,
                        "workflow_type": self._workflow_type,
                        "body": ev,
                        "schema_version": self.model.schema_version(),
                    }
                )
            )
            new_version = old.version + 1
            await self._maybe_snapshot(s, id, new_state, new_version)
            await s.commit()

        new = StoredState(id=id, state=new_state, version=new_version)
        await self._es.remove_state(id)
        return new

    async def continue_as_new(
        self,
        id: str,
        new_cmd: C | None = None,
        reason: str = "",
        new_workflow_type: str | None = None,
    ) -> "StoredState | Rejection":
        """Reset a workflow's event log while preserving state (Continue-As-New).

        Steps:
        1. Load current state.
        2. Force a snapshot at the current version.
        3. Delete all existing events for the workflow.
        4. Insert a single ``EvContinueAsNew`` marker event (version=1).
        5. Optionally process ``new_cmd`` against the current state.

        Args:
            id: Workflow ID.
            new_cmd: Optional initial command to run against the preserved state.
            reason: Human-readable reason for the continuation.
            new_workflow_type: Override workflow type label (for migrations).

        Returns:
            Updated StoredState, or Rejection if the workflow is not found.
        """
        if not self._db_snapshot_model:
            return Rejection(msg="continue_as_new requires snapshotting to be enabled")

        async with self._session_maker() as s:
            current: StoredState[Any] = await self.get_current_state(s, id)
            wf_type = new_workflow_type or self._workflow_type

            # Force snapshot at current version
            stmt = (
                pg_insert(self._db_snapshot_model)
                .values(
                    workflow_id=id,
                    workflow_type=wf_type,
                    version=current.version,
                    state=current.state,
                )
                .on_conflict_do_update(
                    index_elements=["workflow_id"],
                    set_={"version": current.version, "state": current.state},
                )
            )
            await s.execute(stmt)

            # Delete entire event history
            await s.execute(
                delete(self.db_event_model).where(self.db_event_model.workflow_id == id)
            )

            # Insert marker event (version=1)
            marker = EvContinueAsNew(reason=reason, new_workflow_type=new_workflow_type)
            await s.execute(
                insert(self.db_event_model).values(
                    {
                        "workflow_id": id,
                        "workflow_version": 1,
                        "event_type": marker.type,
                        "workflow_type": wf_type,
                        "body": marker,
                        "schema_version": self.model.schema_version(),
                    }
                )
            )
            await s.commit()

        new = StoredState(id=id, state=current.state, version=1)
        await self._es.put_state(new)

        # Optionally kick off a fresh command against the preserved state
        if new_cmd is not None:
            result: tuple[StoredState[Any], list[Any]] | Rejection = (
                await self.process_command(id, new_cmd)
            )
            if isinstance(result, Rejection):
                return result
            stored, _ = result
            return stored

        return new

    async def set_search_attributes(self, workflow_id: str, attributes: dict) -> None:
        """Upsert custom search attributes for a workflow.

        Requires ``db_search_attributes_model`` to be set on the repo.

        Args:
            workflow_id: The workflow whose attributes to update.
            attributes: Dict of attribute key/value pairs.  Merged (not replaced)
                        with any existing attributes.
        """
        if not self._db_search_attributes_model:
            raise RuntimeError(
                "set_search_attributes requires db_search_attributes_model to be configured"
            )
        async with self._session_maker() as s:
            stmt = (
                pg_insert(self._db_search_attributes_model)
                .values(
                    workflow_id=workflow_id,
                    workflow_type=self._workflow_type,
                    attributes=attributes,
                )
                .on_conflict_do_update(
                    index_elements=["workflow_id"],
                    set_={
                        "attributes": text(
                            f"{self._db_search_attributes_model.__tablename__}.attributes || excluded.attributes"
                        )
                    },
                )
            )
            await s.execute(stmt)
            await s.commit()

    async def search_workflows(
        self, attributes: dict, limit: int = 100, offset: int = 0
    ) -> list[str]:
        """Find workflow IDs whose search attributes contain all given key/value pairs.

        Uses the GIN index for fast JSONB containment queries.

        Args:
            attributes: Dict of attribute key/value pairs to match (containment query).
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
            List of matching workflow IDs.
        """
        if not self._db_search_attributes_model:
            raise RuntimeError(
                "search_workflows requires db_search_attributes_model to be configured"
            )
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import JSONB as _JSONB

        async with self._session_maker() as s:
            result = await s.execute(
                select(self._db_search_attributes_model.workflow_id)
                .where(
                    self._db_search_attributes_model.workflow_type
                    == self._workflow_type
                )
                .where(
                    self._db_search_attributes_model.attributes.contains(
                        cast(attributes, _JSONB)
                    )
                )
                .limit(limit)
                .offset(offset)
            )
            return [row[0] for row in result.fetchall()]

    async def replay_workflow(
        self, id: str, from_version: int
    ) -> StoredState[S] | None:
        """Replay events from from_version to HEAD. Updates snapshot and ephemeral cache."""
        async with self._session_maker() as s:
            base: StoredState[S] | None = await self.load_state(
                s, id, at_version=from_version - 1 if from_version > 1 else 0
            )
            base_state = base.state if base else None
            base_ver = base.version if base else 0

            use_upcast = hasattr(self.db_event_model, "body_raw")
            if use_upcast:
                q: Any = (
                    select(
                        self.db_event_model.body_raw,  # type: ignore[attr-defined]
                        self.db_event_model.workflow_version,
                        self.db_event_model.event_type,
                        self.db_event_model.schema_version,
                    )
                    .where(
                        self.db_event_model.workflow_id == id,
                        self.db_event_model.workflow_version >= from_version,
                    )
                    .order_by(self.db_event_model.workflow_version)
                )
            else:
                q = (
                    select(
                        self.db_event_model.body, self.db_event_model.workflow_version
                    )
                    .where(
                        self.db_event_model.workflow_id == id,
                        self.db_event_model.workflow_version >= from_version,
                    )
                    .order_by(self.db_event_model.workflow_version)
                )
            c = await s.execute(q)
            rows = c.fetchall()
            if not rows:
                return base

            if use_upcast:
                body_col = self.db_event_model.__table__.c["body"]
                pydantic_type = body_col.type._pydantic_type  # type: ignore[attr-defined]
                adapter = TypeAdapter(pydantic_type)
                event_bodies = []
                for row in rows:
                    raw = row.body_raw if row.body_raw is not None else {}
                    if isinstance(raw, str):
                        raw = json.loads(raw) if raw else {}
                    schema_ver = getattr(row, "schema_version", 1)
                    event_type = getattr(row, "event_type", "")
                    upcasted = self.model.upcast(event_type, schema_ver, raw)
                    event_bodies.append(adapter.validate_python(upcasted))
            else:
                event_bodies = [row.body for row in rows]

            state = self.model.evolve_(base_state, event_bodies)
            version = rows[-1].workflow_version
            await self._maybe_snapshot(s, id, state, version)
            await s.commit()

        new = StoredState(id=id, state=state, version=version)
        await self._es.put_state(new)
        return new

    async def get_workflow_tags(self, workflow_id: str) -> list[str]:
        """Get tags for a workflow from the metadata table.

        Args:
            workflow_id: The workflow ID to get tags for

        Returns:
            List of tags, or empty list if no metadata exists
        """
        if not self.db_workflow_metadata_model:
            return []

        async with self._session_maker() as s:
            result = await s.scalar(
                select(self.db_workflow_metadata_model.tags).where(
                    self.db_workflow_metadata_model.workflow_id == workflow_id
                )
            )
            return result if result else []

    async def _inject_workflow_tags_into_events(
        self, workflow_id: str, events: list[E]
    ) -> None:
        """Inject workflow tags into event metadata for fast access.

        This embeds workflow-level tags into each event's metadata so they're
        available without additional database queries during event processing.

        Args:
            workflow_id: The workflow ID
            events: List of events to inject tags into
        """
        if not self.db_workflow_metadata_model:
            return

        workflow_tags = await self.get_workflow_tags(workflow_id)
        if workflow_tags:
            for event in events:
                md: dict[str, Any] = getattr(event, "metadata_", None) or {}
                md["workflow_tags"] = workflow_tags
                try:
                    event.metadata_ = md  # type: ignore[union-attr,attr-defined]
                except (AttributeError, ValueError):
                    object.__setattr__(event, "metadata_", md)

    async def get_current_state(self, s: AsyncSession, id: str) -> StoredState[S]:
        state: StoredState[S] | None = await self._es.get_state(id)
        if state is not None:
            if self._trust_cache:
                return state
            last_event_no = await s.scalar(
                select(self.db_event_model.workflow_version)
                .where(self.db_event_model.workflow_id == id)
                .order_by(self.db_event_model.workflow_version.desc())
                .limit(1)
            )
            if state.version == last_event_no:
                return state

        state = await self.load_state(s, id)
        if state is None:
            raise WorkflowNotFound(id=id, workflow_type=self.model)
        await self._es.put_state(state)
        return state

    async def load_state(
        self, s: AsyncSession, id: str, at_version: int | None = None
    ) -> StoredState[S] | None:
        with self._tracer.span(
            "load_state",
            {"fleuve.workflow_id": id, "fleuve.at_version": at_version or 0},
        ):
            return await self._load_state_impl(s, id, at_version)

    async def _load_state_impl(
        self, s: AsyncSession, id: str, at_version: int | None = None
    ) -> StoredState[S] | None:
        base_state: S | None = None
        base_version = 0

        if self._db_snapshot_model:
            snap = await s.execute(
                select(self._db_snapshot_model).where(
                    self._db_snapshot_model.workflow_id == id
                )
            )
            snap_row = snap.scalar_one_or_none()
            if snap_row is not None and (
                at_version is None or snap_row.version <= at_version
            ):
                base_state = cast(S, snap_row.state)
                base_version = snap_row.version

        use_upcast = hasattr(self.db_event_model, "body_raw")
        q: Any
        if use_upcast:
            q = (
                select(
                    self.db_event_model.body_raw,  # type: ignore[attr-defined]
                    self.db_event_model.workflow_version,
                    self.db_event_model.event_type,
                    self.db_event_model.schema_version,
                )
                .where(
                    self.db_event_model.workflow_id == id,
                    self.db_event_model.workflow_version > base_version,
                )
                .order_by(self.db_event_model.workflow_version)
            )
        else:
            q = (
                select(self.db_event_model.body, self.db_event_model.workflow_version)
                .where(
                    self.db_event_model.workflow_id == id,
                    self.db_event_model.workflow_version > base_version,
                )
                .order_by(self.db_event_model.workflow_version)
            )
        if at_version is not None:
            q = q.where(self.db_event_model.workflow_version <= at_version)

        c = await s.execute(q)
        rows = c.fetchall()

        if not rows and base_state is None:
            return None

        version = rows[-1].workflow_version if rows else base_version

        if use_upcast:
            body_col = self.db_event_model.__table__.c["body"]
            pydantic_type = body_col.type._pydantic_type  # type: ignore[attr-defined]
            adapter = TypeAdapter(pydantic_type)
            event_bodies: list[Any] = []
            for row in rows:
                raw = row.body_raw if row.body_raw is not None else {}
                if isinstance(raw, str):
                    raw = json.loads(raw) if raw else {}
                elif not isinstance(raw, dict):
                    raw = {}
                schema_ver = getattr(row, "schema_version", 1)
                event_type = getattr(row, "event_type", "")
                upcasted = self.model.upcast(event_type, schema_ver, raw)
                event_bodies.append(adapter.validate_python(upcasted))
        else:
            event_bodies = [row.body for row in rows]

        if event_bodies:
            last_body = event_bodies[-1]
            if not isinstance(last_body, EvSystemCancel) and self.model.is_final_event(
                last_body
            ):
                return None  # Workflow completed (but not cancelled - cancelled needs state for lifecycle checks)

            state = self.model.evolve_(base_state, event_bodies)
        else:
            state = base_state
        assert (
            state is not None
        )  # guaranteed: early return when both rows and base_state empty
        return StoredState(state=state, id=id, version=version)

    async def hydrate_state_(self, id: str) -> StoredState[S] | None:
        async with self._session_maker() as s:
            return await self.load_state(s, id)

    async def republish_events(
        self,
        workflow_id: str | None = None,
        min_event_id: int | None = None,
        max_event_id: int | None = None,
    ) -> int:
        """Mark events for republishing to NATS JetStream (admin/recovery tool).

        This method sets pushed=False on events matching the criteria, which causes
        the OutboxPublisher to republish them to NATS JetStream. This is useful for:
        - Recovering from NATS failures
        - Replaying events to new consumers
        - Fixing inconsistencies between PostgreSQL and NATS

        Args:
            workflow_id: Optional workflow ID to filter events
            min_event_id: Optional minimum global_id to republish from
            max_event_id: Optional maximum global_id to republish to

        Returns:
            Number of events marked for republishing

        Example:
            # Republish all events for a specific workflow
            count = await repo.republish_events(workflow_id="order-123")

            # Republish events in a specific range
            count = await repo.republish_events(min_event_id=1000, max_event_id=2000)

            # Republish all events after a certain point
            count = await repo.republish_events(min_event_id=5000)
        """
        async with self._session_maker() as s:
            query = update(self.db_event_model).values(pushed=False)

            if workflow_id:
                query = query.where(self.db_event_model.workflow_id == workflow_id)
            if min_event_id:
                query = query.where(self.db_event_model.global_id >= min_event_id)
            if max_event_id:
                query = query.where(self.db_event_model.global_id <= max_event_id)

            result = cast(CursorResult[Any], await s.execute(query))
            await s.commit()

            logger.info("Marked %d events for republishing", result.rowcount)
            return result.rowcount
