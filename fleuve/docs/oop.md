# Class-based (OOP) workflow definition

Fleuve supports two styles for defining workflows.  Both route through
the same internal pipeline (`decide → events → evolve → snapshot →
write`) and store events on the same `wf_events` stream — they are
fully interchangeable from the framework's point of view.

| Style | When to use |
|-------|-------------|
| **Protocol-style** (`Workflow[E, C, S, EE]` with a static `decide` and class-method `_evolve` that dispatch via `isinstance` chains) | Existing workflows, or when you want explicit control over the command/event union and dispatch logic. |
| **Class-based** (`@command` / `@event_handler` decorators on methods of a `Workflow` subclass) | New workflows where the per-method Pydantic command boilerplate of the protocol style would dominate the file. |

Both styles can co-exist in the same project, and a switch from one to
the other is a per-workflow decision.  Existing protocol-style
workflows are **not** affected by anything in this document.

## A complete example

```python
from datetime import datetime, timedelta, timezone
from typing import Literal
from pydantic import Field

from fleuve import (
    EvDelay,
    StateBase,
    Sub,
    Workflow,
    WorkflowRejection,
    command,
    event_handler,
)
from fleuve.model import EventBase


# --- State ---

class CounterState(StateBase):
    count: int = 0
    ticks: int = 0
    subscriptions: list[Sub] = Field(default_factory=list)
    external_subscriptions: list = Field(default_factory=list)


# --- Events ---

class EvIncremented(EventBase):
    type: Literal["counter.incremented"] = "counter.incremented"
    by: int


class EvTicked(EventBase):
    type: Literal["counter.ticked"] = "counter.ticked"
    at: datetime


class CounterTickDelay(EvDelay["CounterCmd"]):  # type: ignore[type-arg]
    type: Literal["counter.tick_delay"] = "counter.tick_delay"


# --- Workflow ---

class Counter(Workflow):
    """A class-based workflow.

    - ``state`` is required as a Pydantic field.  The framework injects
      the current state when dispatching commands and events.
    - ``@command`` methods are pure: they read ``self.state`` and return
      a list of events.  Raise :class:`WorkflowRejection` to reject.
    - ``@event_handler`` methods are pure: they take an event and return
      the new state.  Never mutate ``self.state``.
    """

    state: CounterState | None = None

    @classmethod
    def name(cls) -> str:
        return "counter"

    # --- Commands ---

    @command
    def increment(self, by: int) -> list[EvIncremented]:
        if by <= 0:
            raise WorkflowRejection("by must be positive")
        return [EvIncremented(by=by)]

    @command
    def schedule_tick(self, in_seconds: int) -> list[CounterTickDelay]:
        delay_until = datetime.now(timezone.utc) + timedelta(seconds=in_seconds)
        return [
            CounterTickDelay(
                id=f"tick-{in_seconds}",
                delay_until=delay_until,
                # Build the round-trip command via the typed helper.
                next_cmd=type(self).cmd("tick"),
            )
        ]

    @command
    def tick(self) -> list[EvTicked]:
        return [EvTicked(at=datetime.now(timezone.utc))]

    # --- Event handlers ---

    @event_handler
    def _on_incremented(self, ev: EvIncremented) -> CounterState:
        cur = self.state or CounterState()
        return cur.apply(count=cur.count + ev.by)

    @event_handler
    def _on_ticked(self, ev: EvTicked) -> CounterState:
        cur = self.state or CounterState()
        return cur.apply(ticks=cur.ticks + 1)


# Build the discriminated union once.  Use it as the target of
# ``PydanticType`` for any DB column that stores commands, e.g. the
# ``next_command`` column on the workflow's ``DelaySchedule`` table.
CounterCmd = Counter.command_union()
```

## Caller surface

`AsyncRepo` gains three helpers for class-based workflows:

```python
# Single-workflow, by name:
result = await repo.invoke("wf-1", "increment", by=2)

# Single-workflow, via a per-id proxy:
result = await repo.workflow("wf-1").increment(by=2)

# Bulk fan-out:
results = await repo.bulk_invoke(["wf-1", "wf-2", "wf-3"], "increment", by=2)
```

All three route through the existing `process_command` /
`bulk_process_command` machinery, so they share the same locking,
optimistic concurrency, snapshot, and adapter behaviour as the legacy
caller surface.

For `create_new`, build the typed cmd via the ``cmd`` helper:

```python
result = await repo.create_new(Counter.cmd("increment", by=10), "wf-1")
```

## Wire format

Each `@command` method generates a per-method Pydantic model.  The
on-the-wire (and on-disk) shape is **nested**:

```json
{
  "method": "increment",
  "params": {"by": 2}
}
```

`Workflow.command_union()` returns a discriminated union over all
per-method models, with the discriminator on the top-level `method`
field — so deserialization is O(1) regardless of how many `@command`
methods the workflow defines.

The nested layout leaves room to add wire-level metadata in the future
(e.g. `idempotency_key`, `caller_id`) without colliding with method
parameter names.

## Database wiring

Class-based workflows need exactly the same DB models as protocol-style
workflows.  The only difference: any column that stores a command
(typically the `next_command` column on a `DelaySchedule` subclass)
should target the auto-built command union:

```python
from fleuve.postgres import DelaySchedule, PydanticType
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import Mapped, mapped_column

class CounterDelaySchedule(DelaySchedule):
    __tablename__ = "counter_delays"

    @declared_attr
    def next_command(cls) -> Mapped:  # type: ignore[type-arg]
        return mapped_column(PydanticType(Counter.command_union()), nullable=False)
```

For event tables, the `body` column's `PydanticType` union must include
the workflow's events plus `EvDelayComplete[Counter.command_union()]`
when the workflow uses delays:

```python
from typing import Union
from fleuve import EvDelayComplete, EvSystemCancel, EvSystemPause, EvSystemResume
from fleuve.postgres import StoredEvent

CounterEventBody = Union[
    EvIncremented,
    EvTicked,
    CounterTickDelay,
    EvDelayComplete[CounterCmd],
    EvSystemPause,
    EvSystemResume,
    EvSystemCancel,
]

class CounterEventModel(StoredEvent):
    __tablename__ = "counter_events"

    @declared_attr
    def body(cls) -> Mapped:  # type: ignore[type-arg]
        return mapped_column(PydanticType(CounterEventBody), nullable=False)
```

## Purity contract

`@command` methods **must**:
- be pure functions of `self.state` and the named parameters,
- return a list of events (or raise `WorkflowRejection`),
- not perform any IO,
- not mutate `self.state`.

`@event_handler` methods **must**:
- be pure functions of `self.state` and the event,
- return the new state (typically via `state.apply(...)` or
  `state.model_copy(update=...)`),
- not mutate `self.state`.

The framework shallow-copies `self.state` on each dispatch as a safety
net: if a handler accidentally mutates a top-level field of `self.state`,
the caller's reference is shielded.  The shallow copy still shares
nested objects (e.g. lists), so the contract above is what you should
rely on — not the runtime guardrail.

## Decorator rules

`@command` methods:
- the first parameter must be `self`,
- every other parameter must be type-annotated (the annotation becomes
  the field type on the auto-built Pydantic model),
- positional-only, `*args`, and `**kwargs` are rejected at class-creation
  time — the framework needs a stable named parameter list.

`@event_handler` methods:
- exactly two parameters: `(self, event: SomeEventClass)`,
- dispatch is by `isinstance(event, <annotation>)`, in declaration order
  — the first match wins.

A class that uses **any** `@command` or `@event_handler` decorator must
declare a `state` field on the class.  The framework raises a clear
`TypeError` at class-creation time if it is missing.

## Framework-emitted commands: `@on_command`

Some commands are constructed by the framework itself rather than by
user code calling `cls.cmd("name", ...)` — the canonical example is
`CmdPeriodicTaskDue`, which the periodic-task system sets as the
`next_cmd` of every `EvPeriodicDelay` it schedules.  These commands
have no `method` field, so the regular `@command` method-routing
dispatch can't reach them.

Use `@on_command(CmdType)` to register an `isinstance`-routed handler:

```python
from fleuve import (
    Workflow,
    PeriodicTask,
    command,
    event_handler,
    on_command,
)
from fleuve.model import CmdPeriodicTaskDue

class Janitor(Workflow, periodic_tasks=[
    PeriodicTask(id="cleanup", interval=timedelta(hours=1)),
]):
    state: JanitorState | None = None

    @on_command(CmdPeriodicTaskDue)
    def on_periodic_task_due(
        self, cmd: CmdPeriodicTaskDue
    ) -> list[EvCleanupRequested]:
        if cmd.task_id == "cleanup":
            return [
                EvCleanupRequested(),
                *type(self).reschedule_periodic_task("cleanup"),
            ]
        return []

    @event_handler
    def _on_cleanup_requested(
        self, ev: EvCleanupRequested
    ) -> JanitorState:
        return (self.state or JanitorState()).apply(
            last_cleanup_request=ev.at
        )
```

`@on_command` handlers are checked **before** the `@command`
method-routing dispatcher, so a raw command never falls through to
`"unknown command method: None"`.  Multiple `@on_command` decorators
may coexist on the same class (one per command type); they fire in
declaration order, and the first matching `isinstance` wins.

The `command_union()` does **not** include `@on_command` handlers in
the general case — they consume pre-existing classes rather than
auto-deriving new ones.  The one exception is `CmdPeriodicTaskDue`,
which `command_union()` includes automatically when the class has any
`@periodic_task` method (see next section).

For DB columns that store other framework commands alongside user
commands, build a wider union manually:

```python
from typing import Union
from some_module import SomeFrameworkCmd

JanitorCommand = Union[Janitor.command_union(), SomeFrameworkCmd]

class JanitorDelaySchedule(DelaySchedule):
    next_command = mapped_column(
        PydanticType(JanitorCommand), nullable=False
    )
```

## Recurring work: `@periodic_task`

The decorator-style equivalent of the legacy `Workflow(periodic_tasks=
[PeriodicTask(id="x", interval=...)])` form.  The method's `__name__`
becomes the task id, the framework auto-installs a dispatcher for
`CmdPeriodicTaskDue`, and **re-arming is automatic** — you never have
to remember `*Workflow.reschedule_periodic_task("x")`.

```python
from datetime import timedelta
from fleuve import Workflow, command, event_handler, periodic_task

class Vault(Workflow):
    state: VaultState | None = None

    @classmethod
    def name(cls): return "vault"

    @command
    def activate(self) -> list[Event]:
        # kickstart_periodic() is auto-installed when @periodic_task
        # methods exist; it returns initial EvPeriodicDelay events.
        return [EvActivated(...), *self.kickstart_periodic()]

    @periodic_task(every=timedelta(hours=6), first_run=timedelta(minutes=1))
    def psyop_check(self) -> list[Event]:
        return [EvPsyopRequested(vault_id=self.state.vault_id)]

    @periodic_task(every=timedelta(hours=12), jitter=timedelta(minutes=10))
    def entity_reconcile(self) -> list[Event]:
        return [EvEntityReconcileRequested(vault_id=self.state.vault_id)]

    @event_handler
    def _on_psyop_checked(self, ev: EvPsyopChecked) -> VaultState:
        # Notice: no `*reschedule_periodic_task("psyop_check")` — the
        # framework re-armed psyop_check when CmdPeriodicTaskDue was
        # dispatched, before this handler even ran.
        return self.state.apply(last_psyop_at=ev.at)
```

### What the framework does for you

When a `@periodic_task` method is detected:

1. A synthetic `@on_command(CmdPeriodicTaskDue)` handler is auto-installed.
   When `CmdPeriodicTaskDue(task_id=X)` arrives, it:
   - looks up the method whose `__name__` is `X`,
   - calls it with no args (the method reads `self.state`),
   - **appends an `EvPeriodicDelay`** for the next run — unless the
     task is disabled (`every=timedelta(0)`).
2. `command_union()` widens to include `CmdPeriodicTaskDue` so the
   `EvDelayComplete[command_union()]` member of your event-body union
   round-trips periodic deliveries automatically.
3. `kickstart_periodic(*only)` is added as an instance method.
   Skips tasks already scheduled in `state.schedules` (re-activation
   is idempotent) and skips disabled tasks.

### Disabling, opt-out, and manual control

- **Disable a task**: `@periodic_task(every=timedelta(0))` — the
  dispatcher returns the user's events without re-arming, and
  `kickstart_periodic` skips it.  Useful as a runtime kill-switch
  controlled by a config flag (`every=cfg.psyop_interval or timedelta(0)`).
- **Stale `task_id`**: if `CmdPeriodicTaskDue(task_id=X)` arrives for
  a method that no longer exists (renamed, removed), the dispatcher
  returns `[]` — the stale delay dies quietly instead of crashing
  with "unknown task".
- **Full opt-out**: define your own `@on_command(CmdPeriodicTaskDue)`
  on the class.  The framework detects this and does **not** install
  its synthetic handler — your method takes full responsibility for
  dispatch and re-arm.
- **Selective kickstart**: `self.kickstart_periodic("psyop_check")`
  only emits the named tasks.  Useful when activation is split across
  multiple commands and only some tasks should fire from each.

### Side-by-side: old vs new

```python
# Before: spec separated from handler, id repeated 3+ times,
# manual re-arm required in every completion branch.
class Vault(Workflow[...], periodic_tasks=[
    PeriodicTask(id="psyop_check", interval=timedelta(hours=6)),
]):
    @staticmethod
    def decide(state, cmd):
        if isinstance(cmd, CmdPeriodicTaskDue):
            match cmd.task_id:
                case "psyop_check":
                    return [EvPsyopRequested(...)]
        if isinstance(cmd, CmdPsyopCheckDone):
            return [
                EvPsyopChecked(),
                *Vault.reschedule_periodic_task("psyop_check"),  # MUST not forget
            ]

# After: one method, one source of truth.
class Vault(Workflow):
    @periodic_task(every=timedelta(hours=6))
    def psyop_check(self) -> list[Event]:
        return [EvPsyopRequested(vault_id=self.state.vault_id)]
    # CmdPsyopCheckDone is just a regular @command — re-arm is automatic.
```

## Backward compatibility

- Existing `Workflow[E, C, S, EE]` protocol-style workflows are
  unaffected.  The `__init_subclass__` hook that detects class-based
  workflows is a no-op for any class that has no `@command`,
  `@event_handler`, or `@on_command` methods.
- Both styles coexist on the same `wf_events` table: events are
  discriminated by their `type` field, which is unchanged.
- All `AsyncRepo` lifecycle methods (`process_command`,
  `bulk_process_command`, `create_new`, `cancel_workflow`,
  `pause_workflow`, `resume_workflow`, `replay_workflow`,
  `continue_as_new`) work unchanged for both styles.

## Out of scope

- Sub-workflows / parent–child lifecycles.
- Imperative (Temporal-style) `await activity` workflows — class-based
  is decorator-dispatch + immutable state, not continue-as-new
  scripting.
- Mutable instance state.  All state changes go through events +
  `@event_handler` returning new state.
