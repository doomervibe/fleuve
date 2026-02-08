from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, Generic, Type, TypeVar
from uuid import uuid4

from nats.aio.client import Client as NATS
from nats.js.api import KeyValueConfig
from nats.js.errors import BucketNotFoundError, KeyNotFoundError
from pydantic import BaseModel
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing_extensions import Self

from fleuve.model import AlreadyExists, Rejection, StateBase, Workflow
from fleuve.postgres import StoredEvent, Subscription

# Define type variables for generic typing
C = TypeVar("C", bound=BaseModel)  # Command type
E = TypeVar("E", bound=BaseModel)  # Event type
Wf = TypeVar("Wf", bound=Workflow)  # Workflow type
S = TypeVar("S", bound=StateBase)  # State type
Se = TypeVar("Se", bound=StoredEvent)  # StoredEvent subclass type

# Callable run inside the same transaction as event insertion to update
# denormalized/auxiliary DB data. Args: (session, workflow_id, old_state, new_state, events).
# Must not commit; runs after subscription handling and before event insert.
SyncDbHandler = Callable[
    [AsyncSession, str, Any, Any, list[Any]], Awaitable[None]
]


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
        self._bucket = None
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
        await self._bucket.put(str(new.id), new.model_dump_json().encode())

    async def get_state(self, workflow_id: str) -> StoredState[S] | None:
        assert self._bucket
        try:
            entry = await self._bucket.get(str(workflow_id))
        except KeyNotFoundError:
            return None
        assert entry.value is not None
        return StoredState[self._s].model_validate_json(entry.value)

    async def remove_state(self, workflow_id: str):
        assert self._bucket
        try:
            await self._bucket.delete(str(workflow_id))
        except KeyNotFoundError:
            return


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
    ) -> None:
        self._workflow_type = model.name()
        self._uuid = uuid4
        self._es = es
        self._session_maker: async_sessionmaker[AsyncSession] = session_maker
        self.model = model
        self.db_event_model = db_event_model
        self.db_sub_model = db_sub_model
        self.db_workflow_metadata_model = db_workflow_metadata_model
        self.db_external_sub_model = db_external_sub_model
        self.sync_db = sync_db

    async def process_command(
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
                events = self.model.decide(old.state, cmd)
                if not events:
                    return old, []
                if isinstance(events, Rejection):
                    return events

                # Evolve the state with the new events
                new_state: S = self.model.evolve_(old.state, events)

                await self._handle_subscriptions(old.state, new_state, s, id)
                await self._handle_external_subscriptions(old.state, new_state, s, id)

                if self.sync_db:
                    await self.sync_db(s, id, old.state, new_state, events)

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
                                }
                                for i, e in enumerate(events, start=1)
                            ]
                        )
                    )
                    await s.commit()
                    # Success - break out of retry loop
                    break
                except IntegrityError:
                    # Handle race condition: workflow state changed between read and write
                    # Rollback and retry with updated state
                    await s.rollback()
                    continue

        new = StoredState(id=id, state=new_state, version=old.version + len(events))
        if self.model.is_final_event(events[-1]):
            await self._es.remove_state(id)
        else:
            await self._es.put_state(new)
        return new, events

    async def _handle_subscriptions(
        self, old_state: S | None, new_state: S, s: AsyncSession, workflow_id: str
    ):
        if (old_state is None and new_state.subscriptions) or (
            old_state and old_state.subscriptions != new_state.subscriptions
        ):
            c = await s.execute(
                select(self.db_sub_model).where(
                    self.db_sub_model.workflow_id == workflow_id
                )
            )
            existing = set[
                tuple[str, str, tuple[str, ...], tuple[str, ...]]
            ](
                (
                    i.subscribed_to_workflow,
                    i.subscribed_to_event_type,
                    tuple(i.tags or []),
                    tuple(i.tags_all or []),
                )
                for i in c.fetchall()
            )
            new = set[tuple[str, str, tuple[str, ...], tuple[str, ...]]](
                (i.workflow_id, i.event_type, tuple(i.tags), tuple(i.tags_all))
                for i in new_state.subscriptions
            )
            for i in existing:
                if i not in new:
                    await s.execute(
                        delete(self.db_sub_model)
                        .where(self.db_sub_model.workflow_id == workflow_id)
                        .where(self.db_sub_model.subscribed_to_event_type == i[1])
                        .where(self.db_sub_model.subscribed_to_workflow == i[0])
                        .where(self.db_sub_model.tags == list(i[2]))
                        .where(self.db_sub_model.tags_all == list(i[3]))
                    )
            for i in new:
                if i not in existing:
                    await s.execute(
                        insert(self.db_sub_model).values(
                            dict(
                                workflow_id=workflow_id,
                                workflow_type=self._workflow_type,
                                subscribed_to_event_type=i[1],
                                subscribed_to_workflow=i[0],
                                tags=list(i[2]),
                                tags_all=list(i[3]),
                            )
                        )
                    )

    async def _handle_external_subscriptions(
        self, old_state: S | None, new_state: S, s: AsyncSession, workflow_id: str
    ):
        if not self.db_external_sub_model:
            return
        external_subs = getattr(new_state, "external_subscriptions", []) or []
        if (old_state is None and external_subs) or (
            old_state
            and getattr(old_state, "external_subscriptions", []) or [] != external_subs
        ):
            c = await s.execute(
                select(self.db_external_sub_model).where(
                    self.db_external_sub_model.workflow_id == workflow_id
                )
            )
            existing = set(row[0].topic for row in c.fetchall())
            new = set(ext.topic for ext in external_subs)
            for topic in existing:
                if topic not in new:
                    await s.execute(
                        delete(self.db_external_sub_model)
                        .where(self.db_external_sub_model.workflow_id == workflow_id)
                        .where(self.db_external_sub_model.topic == topic)
                    )
            for topic in new:
                if topic not in existing:
                    await s.execute(
                        insert(self.db_external_sub_model).values(
                            dict(
                                workflow_id=workflow_id,
                                workflow_type=self._workflow_type,
                                topic=topic,
                            )
                        )
                    )

    async def create_new(self, cmd: C, id: str, tags: list[str] | None = None) -> StoredState | Rejection:
        events = self.model.decide(None, cmd)
        if isinstance(events, Rejection):
            return events

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

                await self._handle_subscriptions(None, state, s, id)
                await self._handle_external_subscriptions(None, state, s, id)

                if self.sync_db:
                    await self.sync_db(s, id, None, state, events)

                # Inject workflow tags into events for fast access
                for event in events:
                    if not hasattr(event, 'metadata_'):
                        event.metadata_ = {}
                    event.metadata_['workflow_tags'] = tags

                await s.execute(
                    insert(self.db_event_model).values(
                        [
                            {
                                "workflow_id": id,
                                "workflow_version": i,
                                "event_type": e.type,
                                "workflow_type": self._workflow_type,
                                "body": e,
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
                select(self.db_workflow_metadata_model.tags)
                .where(self.db_workflow_metadata_model.workflow_id == workflow_id)
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
                if not hasattr(event, 'metadata_'):
                    event.metadata_ = {}
                # Store workflow tags separately from event tags
                event.metadata_['workflow_tags'] = workflow_tags

    async def get_current_state(self, s: AsyncSession, id: str) -> StoredState[S]:
        state: StoredState[S] | None = await self._es.get_state(id)
        if state is not None:
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
        q = (
            select(self.db_event_model.body, self.db_event_model.workflow_version)
            .where(self.db_event_model.workflow_id == id)
            .order_by(self.db_event_model.workflow_version)
        )
        if at_version is not None:
            q = q.where(self.db_event_model.workflow_version <= at_version)

        c = await s.execute(q)
        events = c.fetchall()
        if not events:
            return None
        version = events[-1].workflow_version
        if self.model.is_final_event(events[-1].body):
            return None
    
        state = self.model.evolve_(None, [e.body for e in events])
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
        from sqlalchemy import update

        async with self._session_maker() as s:
            query = update(self.db_event_model).values(pushed=False)

            if workflow_id:
                query = query.where(self.db_event_model.workflow_id == workflow_id)
            if min_event_id:
                query = query.where(self.db_event_model.global_id >= min_event_id)
            if max_event_id:
                query = query.where(self.db_event_model.global_id <= max_event_id)

            result = await s.execute(query)
            await s.commit()

            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"Marked {result.rowcount} events for republishing")
            return result.rowcount
