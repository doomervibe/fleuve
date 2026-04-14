import datetime
import inspect
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Sequence
from typing import Any, Callable, Generic, Iterator, Literal, Type, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fleuve.postgres import RetryPolicy
from fleuve.stream import ConsumedEvent


class EventBase(BaseModel, ABC):
    # This makes the model abstract
    class Config:
        abstract = True

    # Optional metadata (e.g. workflow_tags) injected by repo; not part of event schema.
    metadata_: dict[str, Any] = Field(default_factory=dict, exclude=True)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # Skip the abstract base itself.
        if cls is EventBase:
            return

        # Skip validation for ABC classes (built-in abstract events meant to be subclassed)
        if (
            ABC in cls.__bases__
            or ("EvDelay[" in cls.__name__)
            or ("EvDirectMessage[" in cls.__name__)
        ):
            return

        # Did the subclass actually override the annotation?
        annotation = cls.__annotations__.get("type")
        if annotation is None:
            # Generic subclasses (e.g. EvDelayComplete[C]) may not inherit annotations.
            # Allow if model_fields has type with a default.
            model_fields = getattr(cls, "model_fields", {})
            type_field = model_fields.get("type")
            if type_field is not None and not type_field.is_required():
                return
            raise TypeError(
                f"{cls.__name__} must override `type` with a Literal[...] default."
            )


class Sub(BaseModel):
    """Internal subscription: workflow subscribes to events from another workflow/event type."""

    event_type: str
    workflow_id: str
    tags: list[str] = Field(default_factory=list)
    tags_all: list[str] = Field(default_factory=list)

    def matches_tags(self, event_tags: list[str], workflow_tags: list[str]) -> bool:
        """Check if subscription matches event/workflow tags.

        Args:
            event_tags: Tags from the event's metadata
            workflow_tags: Tags from the workflow's metadata

        Returns:
            True if the subscription's tag filters match, False otherwise
        """
        all_tags = set(event_tags) | set(workflow_tags)

        # If tags specified, check ANY match (OR)
        if self.tags and not any(tag in all_tags for tag in self.tags):
            return False

        # If tags_all specified, check ALL match (AND)
        if self.tags_all and not all(tag in all_tags for tag in self.tags_all):
            return False

        return True


class ExternalSub(BaseModel):
    """External subscription: workflow subscribes to an external NATS message topic."""

    topic: str


class Schedule(BaseModel):
    """A cron schedule stored in workflow state (source of truth for recurring delays)."""

    id: str
    cron_expression: str
    timezone: str | None = None
    next_cmd: BaseModel


class StateBase(BaseModel):
    subscriptions: list[Sub]
    external_subscriptions: list["ExternalSub"] = Field(default_factory=list)
    lifecycle: Literal["active", "paused", "cancelled"] = "active"
    schedules: list[Schedule] = Field(default_factory=list)


# Define type variables for generic typing
C = TypeVar("C", bound=BaseModel)  # Command type
E = TypeVar("E", bound=EventBase)  # Event type
S = TypeVar("S", bound=StateBase)
EE = TypeVar(
    "EE", bound=EventBase
)  # External Event the workflow is supposed to react to


class Rejection(BaseModel):
    msg: str = ""


class AlreadyExists(Rejection):
    pass


class EvDirectMessage(EventBase, ABC):
    target_workflow_id: str
    target_workflow_type: str


class EvDelayComplete(EventBase, Generic[C]):
    """Concrete event emitted by the system (DelayScheduler) when a delay expires.
    Not an ABC - workflows do not emit this; they only receive it."""

    type: Literal["delay_complete"] = "delay_complete"
    delay_id: str
    at: datetime.datetime
    next_cmd: C


class EvDelay(EventBase, Generic[C], ABC):
    id: str  # Unique ID for this delay (workflow-provided); enables multiple delays per workflow
    delay_until: datetime.datetime
    next_cmd: C
    cron_expression: str | None = (
        None  # croniter-compatible expression for recurring schedules
    )
    timezone: str | None = None  # IANA timezone name (e.g. "UTC", "America/New_York")


class CmdPeriodicTaskDue(BaseModel):
    """Framework command delivered when a ``PeriodicTask`` delay fires.

    Add this to your workflow's command union type so that ``decide`` can
    receive it::

        VaultCommand = Union[CmdActivate, CmdPsyopCheckDone, ..., CmdPeriodicTaskDue]

    In ``decide``, dispatch on ``task_id``::

        if isinstance(cmd, CmdPeriodicTaskDue):
            if cmd.task_id == "psyop_check":
                return [EvPsyopCheckRequested(vault_id=state.vault_id)]
            elif cmd.task_id == "entity_reconcile":
                return [EvEntityReconcileRequested(vault_id=state.vault_id)]
    """

    task_id: str


class EvPeriodicDelay(EvDelay[CmdPeriodicTaskDue]):
    """Framework-provided concrete ``EvDelay`` for periodic task scheduling.

    Add this to your workflow's event union so Fleuve can serialize it::

        VaultEvent = Union[EvPsyopCheckRequested, ..., EvPeriodicDelay, EvDelayComplete[VaultCommand]]

    You do **not** need to emit or inspect ``EvPeriodicDelay`` directly — Fleuve
    generates and schedules it via ``PeriodicTask``.  The ``CmdPeriodicTaskDue``
    command is what arrives in ``decide`` when a task is due.
    """

    type: Literal["periodic_delay"] = "periodic_delay"
    task_id: str  # Which PeriodicTask triggered this delay


class EvCancelSchedule(EventBase):
    """Emitted by a workflow to cancel a recurring schedule by id."""

    type: Literal["cancel_schedule"] = "cancel_schedule"
    delay_id: str


class EvActionCancel(EventBase):
    """Emitted by a workflow to cancel its in-flight actions."""

    type: Literal["action_cancel"] = "action_cancel"
    # If None or empty: cancel all actions for this workflow.
    # If non-empty: cancel only actions for these event versions (workflow_version = event_no).
    event_numbers: list[int] | None = None


class EvSubscriptionAdded(EventBase):
    """Emit from decide() to add a subscription. Updates state and DB."""

    type: Literal["subscription_added"] = "subscription_added"
    sub: Sub


class EvSubscriptionRemoved(EventBase):
    """Emit from decide() to remove a subscription. Updates state and DB."""

    type: Literal["subscription_removed"] = "subscription_removed"
    sub: Sub


class EvExternalSubscriptionAdded(EventBase):
    """Emit from decide() to add an external subscription. Updates state and DB."""

    type: Literal["external_subscription_added"] = "external_subscription_added"
    sub: "ExternalSub"


class EvExternalSubscriptionRemoved(EventBase):
    """Emit from decide() to remove an external subscription. Updates state and DB."""

    type: Literal["external_subscription_removed"] = "external_subscription_removed"
    topic: str


class EvScheduleAdded(EventBase):
    """Emit from decide() to add a cron schedule. Updates state and delay_schedule table."""

    type: Literal["schedule_added"] = "schedule_added"
    schedule: Schedule


class EvScheduleRemoved(EventBase):
    """Emit from decide() to remove a cron schedule. Updates state and delay_schedule table."""

    type: Literal["schedule_removed"] = "schedule_removed"
    delay_id: str


class EvSystemPause(EventBase):
    """System event emitted when a workflow is paused externally."""

    type: Literal["system_pause"] = "system_pause"
    reason: str = ""


class EvSystemResume(EventBase):
    """System event emitted when a workflow is resumed externally."""

    type: Literal["system_resume"] = "system_resume"


class EvSystemCancel(EventBase):
    """System event emitted when a workflow is cancelled externally."""

    type: Literal["system_cancel"] = "system_cancel"
    reason: str = ""


class EvContinueAsNew(EventBase):
    """System event that resets a workflow's event log while preserving state.

    After this event is written, the event history is truncated (events deleted)
    and a snapshot is taken.  The workflow then "continues as new" from the
    snapshot with a fresh version counter.  Optionally the workflow type can
    change (for in-place migrations).
    """

    type: Literal["system_continue_as_new"] = "system_continue_as_new"
    reason: str = ""
    new_workflow_type: str | None = None


class Workflow(BaseModel, Generic[E, C, S, EE], ABC):
    def __init_subclass__(cls, periodic_tasks: list | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if periodic_tasks:
            from fleuve.periodic import _inject_periodic_task_methods
            _inject_periodic_task_methods(cls, periodic_tasks)

    @classmethod
    @abstractmethod
    def name(cls) -> str:
        pass

    @classmethod
    def schema_version(cls) -> int:
        """Schema version for event storage. Override when evolving event schemas."""
        return 1

    @classmethod
    def upcast(cls, event_type: str, schema_version: int, raw_data: dict) -> dict:
        """Transform old event data to current schema. Override to handle migrations."""
        return raw_data

    @classmethod
    def decide_and_evolve(
        cls, state: S | None, cmd: C
    ) -> Rejection | tuple[S | None, list[E]]:
        d = cls.decide(state, cmd)
        if isinstance(d, Rejection):
            return d
        new_state = cls.evolve_(state, d)
        return new_state, d

    @classmethod
    def evolve_(cls, state: S | None, events: list[E]) -> S:
        """Evolve state through events. Does not emit sync events."""
        for e in events:
            state = cls.evolve(state, e)
        assert state
        return state

    @classmethod
    def evolve(cls, state: S | None, event: E) -> S:
        """Orchestrates evolution: system events first, then user _evolve."""
        result = cls._evolve_system(state, event)
        if result is not None:
            return result
        return cls._evolve(state, event)

    @staticmethod
    def _sub_matches(a: Sub, b: Sub) -> bool:
        return (
            a.workflow_id == b.workflow_id
            and a.event_type == b.event_type
            and (a.tags or []) == (b.tags or [])
            and (a.tags_all or []) == (b.tags_all or [])
        )

    @classmethod
    def _evolve_system(cls, state: S | None, event: E) -> S | None:
        """Handle system lifecycle events. Returns new state or None if not a system event."""
        # Lifecycle events
        new_lifecycle: Literal["active", "paused", "cancelled"] | None = None
        if isinstance(event, EvSystemPause):
            new_lifecycle = "paused"
        elif isinstance(event, EvSystemResume):
            new_lifecycle = "active"
        elif isinstance(event, EvSystemCancel):
            if state is None:
                return StateBase(
                    subscriptions=[],
                    external_subscriptions=[],
                    lifecycle="cancelled",
                    schedules=[],
                )  # type: ignore[return-value]
            return state.model_copy(update={"lifecycle": "cancelled", "schedules": []})
        elif isinstance(event, EvContinueAsNew):
            # State is preserved; the event log is reset in repo.continue_as_new.
            return state  # type: ignore[return-value]

        # Sync events (user emits from decide; update state)
        if isinstance(event, EvSubscriptionAdded):
            if state is None:
                return StateBase(
                    subscriptions=[event.sub],
                    external_subscriptions=[],
                    lifecycle="active",
                    schedules=[],
                )  # type: ignore[return-value]
            new_subs = state.subscriptions + [event.sub]
            return state.model_copy(update={"subscriptions": new_subs})
        if isinstance(event, EvSubscriptionRemoved):
            if state is None:
                return None
            new_subs = [
                s for s in state.subscriptions if not cls._sub_matches(s, event.sub)
            ]
            return state.model_copy(update={"subscriptions": new_subs})
        if isinstance(event, EvExternalSubscriptionAdded):
            if state is None:
                return StateBase(
                    subscriptions=[],
                    external_subscriptions=[event.sub],
                    lifecycle="active",
                    schedules=[],
                )  # type: ignore[return-value]
            new_ext = state.external_subscriptions + [event.sub]
            return state.model_copy(update={"external_subscriptions": new_ext})
        if isinstance(event, EvExternalSubscriptionRemoved):
            if state is None:
                return None
            new_ext = [
                x for x in state.external_subscriptions if x.topic != event.topic
            ]
            return state.model_copy(update={"external_subscriptions": new_ext})
        if isinstance(event, EvScheduleAdded):
            if state is None:
                return StateBase(
                    subscriptions=[],
                    external_subscriptions=[],
                    lifecycle="active",
                    schedules=[event.schedule],
                )  # type: ignore[return-value]
            new_sched = [x for x in state.schedules if x.id != event.schedule.id] + [
                event.schedule
            ]
            return state.model_copy(update={"schedules": new_sched})
        if isinstance(event, EvScheduleRemoved):
            if state is None:
                return None
            new_sched = [x for x in state.schedules if x.id != event.delay_id]
            return state.model_copy(update={"schedules": new_sched})

        # Cron schedule events (EvDelay with cron, EvCancelSchedule)
        if isinstance(event, EvDelay) and event.cron_expression:
            sched = Schedule(
                id=event.id,
                cron_expression=event.cron_expression,
                timezone=event.timezone,
                next_cmd=event.next_cmd,
            )
            if state is None:
                return StateBase(
                    subscriptions=[],
                    external_subscriptions=[],
                    lifecycle="active",
                    schedules=[sched],
                )  # type: ignore[return-value]
            new_schedules = [x for x in state.schedules if x.id != event.id] + [sched]
            return state.model_copy(update={"schedules": new_schedules})
        if isinstance(event, EvCancelSchedule):
            if state is None:
                return None
            new_schedules = [x for x in state.schedules if x.id != event.delay_id]
            return state.model_copy(update={"schedules": new_schedules})

        if new_lifecycle is not None:
            if state is None:
                return StateBase(
                    subscriptions=[], external_subscriptions=[], lifecycle=new_lifecycle
                )  # type: ignore[return-value]
            return state.model_copy(update={"lifecycle": new_lifecycle})
        return None

    @staticmethod
    @abstractmethod
    def decide(state: S | None, cmd: C) -> list[E] | Rejection:
        pass

    @staticmethod
    @abstractmethod
    def _evolve(state: S | None, event: E) -> S:
        """User-implemented state evolution for workflow events. Called when event is not a system event."""
        pass

    @classmethod
    def event_to_cmd(cls, e: EE) -> C | None:
        """Convert an external event (or ConsumedEvent wrapper) to a command.

        The default implementation handles the universal ``EvDelayComplete``
        case: it unwraps the inner event from a ``ConsumedEvent`` if necessary,
        and returns ``inner.next_cmd`` for any ``EvDelayComplete``.  This means
        workflows that *only* use delays do not need to override this method.

        Override when the workflow reacts to external subscriptions or needs
        custom routing logic beyond delay completion.
        """
        # Unwrap ConsumedEvent (runner passes ConsumedEvent; testing passes inner event)
        inner: Any = getattr(e, "event", e)
        if isinstance(inner, EvDelayComplete):
            return inner.next_cmd  # type: ignore[return-value]
        return None

    @staticmethod
    def is_final_event(e: E) -> bool:
        """Return True if ``e`` terminates the workflow.  Default returns False.

        Override only when the workflow has a terminal event that should stop
        further processing.
        """
        return False


M = TypeVar("M", bound=BaseModel)


class TypedCheckpoint(dict):
    """Typed, dict-backed checkpoint accessor.

    ``TypedCheckpoint`` is a plain ``dict`` subclass, so all existing code that
    reads or writes ``context.checkpoint`` as a dictionary continues to work.
    The additional methods provide a typed layer on top:

    **Load / save a Pydantic model**::

        class DomainCheckpoint(BaseModel):
            domain: str
            pending_urls: list[str]
            next_index: int = 0

        async def act_on(self, event, context):
            cp = context.checkpoint.load(DomainCheckpoint)
            if cp is None:
                cp = DomainCheckpoint(domain=event.domain, pending_urls=event.urls)

            async for i, url in context.checkpoint.iter(cp.pending_urls, start=cp.next_index):
                await self._scrape(url)
                yield context.checkpoint.save(cp.model_copy(update={"next_index": i + 1}))

    **Methods**:

    - ``load(ModelType)`` — deserialize checkpoint dict into a Pydantic model.
      Returns ``None`` when the checkpoint is empty (i.e. first execution).
    - ``save(model, save_now=True)`` — serialize model into the checkpoint dict
      in-place and return a ``CheckpointYield`` ready to be yielded from
      ``act_on``.  By default persists immediately (``save_now=True``).
    - ``iter(items, start=0)`` — async generator of ``(index, item)`` tuples
      starting at ``start``.  Pair with ``save()`` to checkpoint after each item.
    """

    def load(self, model_type: Type[M]) -> M | None:
        """Deserialize the checkpoint dict into ``model_type``.

        Returns ``None`` when the checkpoint is empty (first run or cleared).
        """
        if not self:
            return None
        return model_type.model_validate(dict(self))

    def save(self, model: BaseModel, *, save_now: bool = True) -> "CheckpointYield":
        """Serialize ``model`` into the checkpoint dict and return a ``CheckpointYield``.

        The returned ``CheckpointYield`` should be yielded from ``act_on`` so
        the framework can persist it::

            yield context.checkpoint.save(my_model)

        Args:
            model: Pydantic model to checkpoint.
            save_now: If True (default), the checkpoint is persisted to the DB
                immediately.  Set to False to defer persistence until the action
                completes.
        """
        data = model.model_dump()
        self.clear()
        self.update(data)
        return CheckpointYield(data=data, save_now=save_now)

    async def iter(
        self,
        items: Sequence,
        *,
        start: int = 0,
    ) -> AsyncGenerator[tuple[int, Any], None]:
        """Async generator of ``(index, item)`` pairs starting at ``start``.

        Convenience wrapper so handlers can resume mid-list without manually
        slicing.  Pair with :meth:`save` to checkpoint after each item::

            async for i, url in context.checkpoint.iter(pending_urls, start=cp.next_index):
                await self._fetch(url)
                yield context.checkpoint.save(cp.model_copy(update={"next_index": i + 1}))
        """
        for i in range(start, len(items)):
            yield i, items[i]


class ActionContext(BaseModel):
    """Context passed to action execution, allowing checkpoint/resume functionality."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    workflow_id: str
    event_number: int
    checkpoint: TypedCheckpoint = Field(default_factory=TypedCheckpoint)
    retry_count: int = 0
    retry_policy: RetryPolicy

    @field_validator("checkpoint", mode="before")
    @classmethod
    def _coerce_checkpoint(cls, v: Any) -> TypedCheckpoint:
        """Wrap plain dicts in TypedCheckpoint transparently."""
        if isinstance(v, TypedCheckpoint):
            return v
        return TypedCheckpoint(v if isinstance(v, dict) else {})


class CheckpointYield(BaseModel):
    """
    Checkpoint data yielded from act_on to update and optionally persist checkpoint.

    - save_now=False (default): merge data into context.checkpoint; persisted at end of action.
    - save_now=True: merge data and persist immediately to the DB.
    """

    data: dict = Field(default_factory=dict)
    save_now: bool = False


class ActionTimeout(BaseModel):
    """
    Instruct ActionExecutor to apply a timeout to the remainder of the action.

    When yielded from act_on, the executor wraps the rest of the action
    (consuming the rest of the async generator) in asyncio.wait_for(..., timeout=seconds).
    If the remainder does not complete within the given time, asyncio.TimeoutError
    is raised and the action will retry according to the retry policy.

    Example:
        async def act_on(self, event, context=None):
            yield SomeCommand(...)
            yield ActionTimeout(seconds=30.0)  # rest of action must finish in 30s
            await long_running_work()
            yield AnotherCommand(...)
    """

    seconds: float = Field(
        ..., gt=0, description="Timeout in seconds for the remainder of the action."
    )


Wf = TypeVar("Wf", bound=Workflow)


def handles(*event_types: type) -> Callable:
    """Decorator that registers an Adapter method as the handler for one or more event types.

    When at least one method in an ``Adapter`` subclass is decorated with
    ``@handles``, Fleuve automatically generates ``act_on`` and
    ``to_be_act_on`` — no need to write them manually.

    The decorated method receives the **inner** event (already unwrapped from
    ``ConsumedEvent``), typed to the declared event class::

        class VaultAdapter(Adapter[VaultEvent, VaultCommand]):

            @handles(EvPsyopCheckRequested)
            async def _psyop_check(
                self, ev: EvPsyopCheckRequested, context: ActionContext | None
            ) -> AsyncGenerator[VaultCommand, None]:
                result = await self._client.check(ev.vault_id)
                yield CmdPsyopCheckDone(vault_id=ev.vault_id, alerts=result)

            @handles(EvEntityReconcileRequested)
            async def _entity_reconcile(self, ev, context):
                ...
                yield CmdEntityReconcileDone(vault_id=ev.vault_id)

    Rules:
    - Handlers must be **async generators** (they ``yield`` commands /
      ``CheckpointYield`` / ``ActionTimeout`` values, just like ``act_on``).
    - A handler that yields nothing is fine — just ``return`` without
      yielding anything.
    - You can still override ``act_on`` and/or ``to_be_act_on`` manually
      alongside ``@handles`` methods; the generated versions are only injected
      when those methods are absent from the subclass's own ``__dict__``.
    """

    def decorator(fn: Callable) -> Callable:
        fn._handles_event_types = event_types  # type: ignore[attr-defined]
        return fn

    return decorator


class Adapter(Generic[E, C], ABC):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Collect every @handles-decorated method visible on this class
        # (includes methods inherited from adapter base classes).
        handled: dict[type, Any] = {}
        for attr_name in dir(cls):
            try:
                method = getattr(cls, attr_name)
            except AttributeError:
                continue
            event_types = getattr(method, "_handles_event_types", None)
            if event_types:
                for et in event_types:
                    handled[et] = method

        if not handled:
            return  # Traditional manual act_on / to_be_act_on — nothing to do.

        # Snapshot so the closures below capture stable references.
        _handled_snapshot = dict(handled)
        _event_types_tuple = tuple(handled.keys())

        provided: set[str] = set()

        if "act_on" not in cls.__dict__:
            # Generate an act_on that unwraps ConsumedEvent and dispatches by type.
            async def _generated_act_on(
                self: Any,
                event: Any,
                context: Any = None,
            ) -> AsyncGenerator:
                inner: Any = getattr(event, "event", event)
                for event_type, handler in _handled_snapshot.items():
                    if isinstance(inner, event_type):
                        async for item in handler(self, inner, context):
                            yield item
                        return

            _generated_act_on.__name__ = "act_on"
            cls.act_on = _generated_act_on  # type: ignore[method-assign]
            provided.add("act_on")

        if "to_be_act_on" not in cls.__dict__:

            def _generated_to_be_act_on(self: Any, event: Any) -> bool:
                inner: Any = getattr(event, "event", event)
                return isinstance(inner, _event_types_tuple)

            _generated_to_be_act_on.__name__ = "to_be_act_on"
            cls.to_be_act_on = _generated_to_be_act_on  # type: ignore[method-assign]
            provided.add("to_be_act_on")

        # Remove the provided methods from __abstractmethods__ so that
        # subclasses using @handles are not considered abstract.
        if provided and hasattr(cls, "__abstractmethods__"):
            cls.__abstractmethods__ = frozenset(
                cls.__abstractmethods__ - provided
            )

    @abstractmethod
    async def act_on(
        self, event: ConsumedEvent[E], context: "ActionContext | None" = None
    ) -> AsyncGenerator[Union[C, CheckpointYield, "ActionTimeout"], None]:
        """
        Execute an action for an event; yield zero or more commands and/or checkpoint updates.

        Args:
            event: The event to act on
            context: Optional action context for checkpoint/resume functionality.
                     If None, action is executed without checkpoint support.

        Yields:
            - Commands (C): processed via process_command for the same workflow.
            - CheckpointYield: merge data into checkpoint; if save_now=True persist
              immediately, else persist at end of action.
            - ActionTimeout: apply asyncio.wait_for to the remainder of the action;
              if the rest does not complete within the given seconds, TimeoutError is raised.

        Note: When using the ``@handles`` decorator on methods, this method is
        generated automatically and does not need to be implemented.
        """
        if False:
            yield  # make this an async generator; subclasses override and yield commands/checkpoints

    @abstractmethod
    def to_be_act_on(self, event: Any) -> bool:
        """Return True if this adapter should handle the given event.

        Note: When using the ``@handles`` decorator on methods, this method is
        generated automatically and does not need to be implemented.
        """
        pass

    async def sync_db(
        self,
        session: Any,
        workflow_id: str,
        old_state: Any,
        new_state: Any,
        events: list[Any],
    ) -> None:
        """
        Optional: update denormalized/auxiliary DB in the same transaction as event insert.

        Called by AsyncRepo after subscription handling and before event insert.
        Override to maintain strongly consistent DB data (e.g. summary tables).
        Must not commit; the repo commits the transaction.
        Default implementation does nothing.
        """
        pass
