import datetime
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, Generic, Literal, TypeVar, Union

from pydantic import BaseModel, Field

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


class StateBase(BaseModel):
    subscriptions: list[Sub]
    external_subscriptions: list["ExternalSub"] = Field(default_factory=list)
    lifecycle: Literal["active", "paused", "cancelled"] = "active"


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


class EvActionCancel(EventBase):
    """Emitted by a workflow to cancel its in-flight actions."""

    type: Literal["action_cancel"] = "action_cancel"
    # If None or empty: cancel all actions for this workflow.
    # If non-empty: cancel only actions for these event versions (workflow_version = event_no).
    event_numbers: list[int] | None = None


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
        for e in events:
            state = cls._evolve_system(state, e) or cls.evolve(state, e)

        assert state
        return state

    @classmethod
    def _evolve_system(cls, state: S | None, event: E) -> S | None:
        """Handle system lifecycle events. Returns new state or None if not a system event."""
        if isinstance(event, EvSystemPause):
            new_lifecycle: Literal["active", "paused", "cancelled"] = "paused"
        elif isinstance(event, EvSystemResume):
            new_lifecycle = "active"
        elif isinstance(event, EvSystemCancel):
            new_lifecycle = "cancelled"
        elif isinstance(event, EvContinueAsNew):
            # State is preserved; the event log is reset in repo.continue_as_new.
            return state  # type: ignore[return-value]
        else:
            return None
        if state is None:
            return StateBase(
                subscriptions=[], external_subscriptions=[], lifecycle=new_lifecycle
            )  # type: ignore[return-value]
        return state.model_copy(update={"lifecycle": new_lifecycle})

    @staticmethod
    @abstractmethod
    def decide(state: S | None, cmd: C) -> list[E] | Rejection:
        pass

    @staticmethod
    @abstractmethod
    def evolve(state: S | None, event: E) -> S:
        pass

    @classmethod
    @abstractmethod
    def event_to_cmd(cls, e: EE) -> C | None:
        pass

    @staticmethod
    @abstractmethod
    def is_final_event(e: E) -> bool:
        pass


class ActionContext(BaseModel):
    """Context passed to action execution, allowing checkpoint/resume functionality."""

    workflow_id: str
    event_number: int
    checkpoint: dict = Field(default_factory=dict)
    retry_count: int = 0
    retry_policy: RetryPolicy


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


class Adapter(Generic[E, C], ABC):
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
        """
        if False:
            yield  # make this an async generator; subclasses override and yield commands/checkpoints

    @abstractmethod
    def to_be_act_on(self, event: Any) -> bool:
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
