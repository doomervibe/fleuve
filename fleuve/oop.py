"""Class-based (OOP) workflow definition style.

This module adds a second way to define a Fleuve workflow.  Instead of
implementing the ``Workflow[E, C, S, EE]`` Protocol with a static
``decide`` and class-method ``_evolve`` that dispatch via long
isinstance chains, you can model commands as **methods** on a
``Workflow`` subclass:

    from fleuve import Workflow, command, event_handler, WorkflowRejection

    class Counter(Workflow):
        state: CounterState | None = None

        @classmethod
        def name(cls) -> str:
            return "counter"

        @command
        def increment(self, by: int) -> list[EvIncremented]:
            if by <= 0:
                raise WorkflowRejection("must be positive")
            return [EvIncremented(by=by)]

        @event_handler
        def _on_inc(self, ev: EvIncremented) -> CounterState:
            current = self.state.count if self.state else 0
            return CounterState(count=current + ev.by, ...)

The framework auto-derives a per-method Pydantic command schema from
the method signature, builds a discriminated union (``method`` field),
and dispatches commands through the existing ``decide``/``evolve``
pipeline.

Wire format
-----------
Each ``@command`` method generates a Pydantic model::

    {
      "method": "increment",
      "params": {"by": 1}
    }

The class-level ``Workflow.command_union()`` returns the discriminated
union of all per-method command models — use it as the ``PydanticType``
target for ``DelaySchedule.next_command`` and any other column that
stores commands::

    class CounterDelaySchedule(DelaySchedule):
        next_command = mapped_column(PydanticType(Counter.command_union()), ...)

Caller-side surface
-------------------
``AsyncRepo`` gains three helpers for class-based workflows::

    await repo.invoke(workflow_id, "increment", by=2)
    await repo.workflow(workflow_id).increment(by=2)
    await repo.bulk_invoke([id1, id2], "increment", by=2)

All of them route through the same ``process_command`` /
``bulk_process_command`` machinery as the legacy style.
"""

from __future__ import annotations

import datetime
import inspect
from typing import Annotated, Any, Callable, Literal, Type, Union

from pydantic import BaseModel, Field, create_model

__all__ = [
    "WorkflowRejection",
    "command",
    "event_handler",
    "on_command",
    "periodic_task",
]

# ---------------------------------------------------------------------------
# Public surface


class WorkflowRejection(Exception):
    """Raised inside a ``@command`` method to reject the command.

    The framework catches this at the ``decide`` boundary and converts it to
    a regular ``fleuve.Rejection`` so callers see the same return type they
    do from the legacy Protocol-style API.
    """

    def __init__(self, msg: str = "") -> None:
        super().__init__(msg)
        self.msg = msg


_COMMAND_MARKER = "__fleuve_command__"
_EVENT_HANDLER_MARKER = "__fleuve_event_handler__"
_ON_COMMAND_MARKER = "__fleuve_on_command__"
_PERIODIC_TASK_MARKER = "__fleuve_periodic_task__"


def command(fn: Callable) -> Callable:
    """Mark a method as a workflow command handler.

    The method must:
    - take ``self`` as its first parameter,
    - declare each remaining parameter with a type annotation,
    - return ``list[Event]`` (or any iterable of events; ``None``/empty is OK),
    - optionally raise :class:`WorkflowRejection` to reject.

    Disallowed: positional-only parameters, ``*args``, ``**kwargs`` (the
    framework needs a stable, named parameter list to derive a schema).
    """
    setattr(fn, _COMMAND_MARKER, True)
    return fn


def event_handler(fn: Callable) -> Callable:
    """Mark a method as the apply/evolve handler for a specific event type.

    The handler is selected by ``isinstance(event, <annotation of 2nd arg>)``.
    Multiple handlers may be registered per workflow (one per event class);
    they fire in declaration order, and the first match wins.

    The method must take ``(self, event: <EventClass>)`` and return the new
    state.  ``self.state`` is read-only — return a new state object (e.g.
    via ``state.model_copy(update={...})`` or ``state.apply(...)``).
    """
    setattr(fn, _EVENT_HANDLER_MARKER, True)
    return fn


def on_command(cmd_type: type) -> Callable[[Callable], Callable]:
    """Mark a method as the handler for a specific raw command class.

    Used for **framework-emitted** commands that fleuve constructs itself,
    without going through ``cls.cmd("method", ...)`` — the canonical case is
    :class:`fleuve.model.CmdPeriodicTaskDue`, which the periodic-task system
    sets as the ``next_cmd`` of every ``EvPeriodicDelay`` it schedules.
    These commands have no ``method`` field, so the regular ``@command``
    method-routing dispatch can't reach them.

    Dispatch is by ``isinstance(cmd, cmd_type)``.  ``@on_command`` handlers
    are checked *before* the ``@command`` method-routing dispatcher, so a
    raw command never falls through to ``"unknown command method: None"``.

    The decorated method must take ``(self, cmd: <cmd_type>)`` and return
    ``list[Event]`` (or any iterable of events; ``None`` / empty is OK), or
    raise :class:`WorkflowRejection` to reject.

    Usage::

        from fleuve import Workflow, on_command, event_handler
        from fleuve.model import CmdPeriodicTaskDue

        class MyWorkflow(Workflow, periodic_tasks=[...]):
            state: MyState | None = None

            @on_command(CmdPeriodicTaskDue)
            def on_periodic_task_due(
                self, cmd: CmdPeriodicTaskDue
            ) -> list[Event]:
                # branch by cmd.task_id ...
                return []

    Multiple ``@on_command`` decorators may be registered per workflow
    (one per command class); they fire in declaration order, and the
    first matching ``isinstance`` wins.
    """

    def decorator(fn: Callable) -> Callable:
        setattr(fn, _ON_COMMAND_MARKER, cmd_type)
        return fn

    return decorator


def periodic_task(
    *,
    every: datetime.timedelta,
    first_run: datetime.timedelta = datetime.timedelta(minutes=1),
    jitter: datetime.timedelta = datetime.timedelta(),
) -> Callable[[Callable], Callable]:
    """Mark a method as a periodic task handler.

    The decorated method runs every ``every`` after the first kick.  The
    method's ``__name__`` is used as the task id, so the same string never
    appears twice in your code (versus the legacy ``periodic_tasks=[
    PeriodicTask(id="psyop_check", ...)]`` form which repeats the id in
    the spec, in ``decide``, and in ``reschedule_periodic_task``).

    The framework auto-installs an ``@on_command(CmdPeriodicTaskDue)``
    dispatcher that:

    - Looks up the method by ``cmd.task_id``.
    - Calls it with no arguments — the method reads ``self.state``.
    - Appends an :class:`fleuve.model.EvPeriodicDelay` for the next run
      so the user **never** has to call ``reschedule_periodic_task``.

    Use :meth:`Workflow.kickstart_periodic` (an instance method auto-
    installed when any ``@periodic_task`` exists on the class) from
    inside an ``@command`` method (typically ``activate``) to emit the
    initial delay events::

        @command
        def activate(self) -> list[Event]:
            return [EvActivated(...), *self.kickstart_periodic()]

    Args:
        every: Interval between runs.  ``timedelta(0)`` disables the
            task entirely — the dispatcher returns the user's events
            without re-arming, and ``kickstart_periodic`` skips it.
        first_run: Delay between ``kickstart_periodic`` and the first
            run.  Defaults to one minute.
        jitter: Maximum random offset added to the scheduled time;
            uniform in ``[base, base + jitter]``.  Use to prevent
            thundering-herd when many workflows kickstart at the same
            instant.

    Opt-out: if you provide an explicit
    ``@on_command(CmdPeriodicTaskDue)`` method on the same class, the
    framework does **not** install its synthetic dispatcher — your
    handler takes full responsibility (including re-arm).
    """
    from fleuve.periodic import PeriodicTask

    def decorator(fn: Callable) -> Callable:
        spec = PeriodicTask(
            id=fn.__name__,
            interval=every,
            first_run_after=first_run,
            jitter=jitter,
        )
        setattr(fn, _PERIODIC_TASK_MARKER, spec)
        return fn

    return decorator


# ---------------------------------------------------------------------------
# Class-creation hook (called from Workflow.__init_subclass__)


def _has_oop_methods(cls: type) -> bool:
    """True if any direct attribute on *cls* is a @command, @event_handler,
    @on_command, or @periodic_task-decorated method.
    """
    for v in cls.__dict__.values():
        if callable(v) and (
            getattr(v, _COMMAND_MARKER, False)
            or getattr(v, _EVENT_HANDLER_MARKER, False)
            or getattr(v, _ON_COMMAND_MARKER, None) is not None
            or getattr(v, _PERIODIC_TASK_MARKER, None) is not None
        ):
            return True
    return False


def _try_setup_oop_workflow(cls: type) -> None:
    """Set up class-based dispatch if ``cls`` declares any ``@command`` /
    ``@event_handler`` methods.  No-op for legacy Protocol-style workflows.

    Called from ``Workflow.__init_subclass__`` so existing workflows that
    don't use the decorators keep their current behaviour unchanged.
    """
    if not _has_oop_methods(cls):
        return
    _setup_oop_workflow(cls)


def _setup_oop_workflow(cls: type) -> None:
    """Build per-method command models, register event handlers, and
    install ``decide`` / ``_evolve`` dispatchers.

    Direct ``cls.__dict__`` inspection only — does not walk the MRO.
    Subclassing an OOP workflow does **not** inherit ``@command`` methods
    from the parent in v1.
    """
    # Require state declared as a Pydantic field (so model_construct works).
    if "state" not in getattr(cls, "model_fields", {}) and "state" not in getattr(
        cls, "__annotations__", {}
    ):
        raise TypeError(
            f"{cls.__name__} uses @command/@event_handler but does not declare "
            f"a `state` field.  Add e.g. `state: MyState | None = None` to the "
            f"class body."
        )

    cmd_handlers: dict[str, Callable] = {}
    cmd_models: dict[str, Type[BaseModel]] = {}
    ev_handlers: list[tuple[type, Callable]] = []
    raw_cmd_handlers: list[tuple[type, Callable]] = []
    periodic_handlers: dict[str, tuple[Any, Callable]] = {}

    for name, attr in cls.__dict__.items():
        if not callable(attr):
            continue
        if getattr(attr, _COMMAND_MARKER, False):
            model = _build_command_model(cls, name, attr)
            cmd_handlers[name] = attr
            cmd_models[name] = model
            continue
        if getattr(attr, _EVENT_HANDLER_MARKER, False):
            ev_type = _extract_event_type(cls, name, attr)
            ev_handlers.append((ev_type, attr))
            continue
        raw_cmd_type = getattr(attr, _ON_COMMAND_MARKER, None)
        if raw_cmd_type is not None:
            raw_cmd_handlers.append((raw_cmd_type, attr))
            continue
        periodic_spec = getattr(attr, _PERIODIC_TASK_MARKER, None)
        if periodic_spec is not None:
            periodic_handlers[name] = (periodic_spec, attr)

    cls._command_handlers = cmd_handlers  # type: ignore[attr-defined]
    cls._command_models = cmd_models  # type: ignore[attr-defined]
    cls._event_handlers = tuple(ev_handlers)  # type: ignore[attr-defined]
    cls._periodic_handlers = periodic_handlers  # type: ignore[attr-defined]
    cls._is_oop_workflow = True  # type: ignore[attr-defined]

    # Auto-install the CmdPeriodicTaskDue dispatcher when @periodic_task
    # methods exist and the user hasn't provided their own
    # @on_command(CmdPeriodicTaskDue) — the user's handler always wins.
    if periodic_handlers:
        from fleuve.model import CmdPeriodicTaskDue

        already_handled = any(
            cmd_type is CmdPeriodicTaskDue or issubclass(CmdPeriodicTaskDue, cmd_type)
            for cmd_type, _ in raw_cmd_handlers
        )
        if not already_handled:
            raw_cmd_handlers.append(
                (CmdPeriodicTaskDue, _periodic_task_dispatch)
            )

        # Install the kickstart_periodic instance method (only when there are
        # tasks to kickstart, and only if the user hasn't shadowed it).
        if "kickstart_periodic" not in cls.__dict__:
            cls.kickstart_periodic = _kickstart_periodic  # type: ignore[attr-defined]

    cls._raw_command_handlers = tuple(raw_cmd_handlers)  # type: ignore[attr-defined]

    # Install dispatchers if the user hasn't overridden them.  Using
    # cls.__dict__ (not hasattr) so inherited abstract methods don't block.
    if "decide" not in cls.__dict__:
        cls.decide = classmethod(_oop_decide)  # type: ignore[method-assign]
    if "_evolve" not in cls.__dict__:
        cls._evolve = classmethod(_oop_evolve)  # type: ignore[method-assign]

    # Strip from __abstractmethods__ so the class can be instantiated /
    # registered without the legacy abstract-method enforcement firing.
    if hasattr(cls, "__abstractmethods__"):
        cls.__abstractmethods__ = frozenset(
            cls.__abstractmethods__ - {"decide", "_evolve"}
        )


# ---------------------------------------------------------------------------
# Schema derivation


def _build_command_model(cls: type, method_name: str, fn: Callable) -> Type[BaseModel]:
    """Build a per-method Pydantic command model.

    Wire format is nested::

        {"method": "<name>", "params": {<method-signature-fields>}}
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.items())
    if not params or params[0][0] != "self":
        raise TypeError(
            f"@command {cls.__name__}.{method_name} must take 'self' as the "
            f"first parameter"
        )

    param_fields: dict[str, Any] = {}
    for pname, p in params[1:]:
        if p.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        ):
            raise TypeError(
                f"@command {cls.__name__}.{method_name}: parameter {pname!r} "
                f"uses positional-only / *args / **kwargs which is not "
                f"supported (the framework needs a stable named parameter list)"
            )
        ann = p.annotation if p.annotation is not inspect.Parameter.empty else Any
        default = p.default if p.default is not inspect.Parameter.empty else ...
        param_fields[pname] = (ann, default)

    # Inner params model: one per @command method.
    params_model_name = f"_{cls.__name__}__{method_name}__Params"
    params_model = create_model(
        params_model_name,
        __base__=BaseModel,
        **param_fields,
    )

    # Outer command model: {method, params}.  The Literal discriminator on
    # ``method`` lets us build a tagged union over all per-method models.
    cmd_model_name = f"_{cls.__name__}__cmd__{method_name}"
    cmd_model = create_model(
        cmd_model_name,
        __base__=BaseModel,
        method=(Literal[method_name], method_name),  # type: ignore[valid-type]
        params=(params_model, ...),
    )
    # Stash useful metadata for introspection / better error messages.
    setattr(cmd_model, "__fleuve_method_name__", method_name)
    setattr(cmd_model, "__fleuve_owner__", cls)
    setattr(cmd_model, "__fleuve_params_model__", params_model)
    return cmd_model


def _extract_event_type(cls: type, method_name: str, fn: Callable) -> type:
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    if len(params) < 2:
        raise TypeError(
            f"@event_handler {cls.__name__}.{method_name} must take " f"(self, event)"
        )
    ann = params[1].annotation
    if ann is inspect.Parameter.empty:
        raise TypeError(
            f"@event_handler {cls.__name__}.{method_name}: the event "
            f"parameter must have a type annotation (e.g. `ev: MyEvent`)"
        )
    if not isinstance(ann, type):
        raise TypeError(
            f"@event_handler {cls.__name__}.{method_name}: event annotation "
            f"must be a class, got {ann!r}"
        )
    return ann


# ---------------------------------------------------------------------------
# Dispatchers (installed on each OOP workflow class)


def _oop_decide(cls: type, state: Any, cmd: Any) -> Any:
    """Dispatch a command to its handler.

    Two routes, tried in order:

    1. **Raw isinstance route** — for framework-emitted commands registered
       via :func:`on_command`.  These have no ``method`` field; they're
       routed by ``isinstance(cmd, cmd_type)`` against the
       ``@on_command``-decorated methods on *cls*.  First match wins.

    2. **Method-routed route** — for user commands built via ``cls.cmd``.
       These have a ``method`` field that names the ``@command`` handler.

    Returns ``list[Event]`` or ``Rejection``.
    """
    from fleuve.model import Rejection  # avoid circular import at module load

    raw_handlers: tuple[tuple[type, Callable], ...] = getattr(
        cls, "_raw_command_handlers", ()
    )
    for cmd_type, handler in raw_handlers:
        if isinstance(cmd, cmd_type):
            instance = _build_instance(cls, state)
            try:
                result = handler(instance, cmd)
            except WorkflowRejection as e:
                return Rejection(msg=e.msg)
            return list(result or [])

    method = getattr(cmd, "method", None)
    handlers: dict[str, Callable] = cls._command_handlers  # type: ignore[attr-defined]
    if method is None or method not in handlers:
        return Rejection(msg=f"unknown command method: {method!r}")

    handler = handlers[method]
    instance = _build_instance(cls, state)
    params_obj = getattr(cmd, "params", None)
    kwargs: dict[str, Any]
    if params_obj is None:
        kwargs = {}
    else:
        # Iterate fields rather than model_dump() so nested Pydantic objects
        # (e.g. ``target_info: TargetInfo``) reach the handler intact.
        kwargs = {
            field_name: getattr(params_obj, field_name)
            for field_name in type(params_obj).model_fields
        }

    try:
        result = handler(instance, **kwargs)
    except WorkflowRejection as e:
        return Rejection(msg=e.msg)
    return list(result or [])


def _oop_evolve(cls: type, state: Any, event: Any) -> Any:
    """Dispatch ``@event_handler`` methods by ``isinstance(event, <type>)``.

    Falls through to ``state`` unchanged when no handler matches.  System
    events (cancel, pause, sub-add, …) are handled by ``Workflow._evolve_system``
    *before* this method is reached, so users do not need to register
    handlers for them.
    """
    handlers: tuple[tuple[type, Callable], ...] = cls._event_handlers  # type: ignore[attr-defined]
    for ev_type, handler in handlers:
        if isinstance(event, ev_type):
            instance = _build_instance(cls, state)
            return handler(instance, event)
    return state


def _periodic_task_dispatch(self: Any, cmd: Any) -> list[Any]:
    """Auto-installed handler for ``CmdPeriodicTaskDue`` on classes that use
    ``@periodic_task``.

    Two responsibilities:

    1. Look up the periodic-task method by ``cmd.task_id`` and invoke it.
    2. Append an :class:`fleuve.model.EvPeriodicDelay` for the next run so
       the user never has to call ``reschedule_periodic_task`` manually.

    If ``cmd.task_id`` does not match any registered ``@periodic_task``,
    the dispatcher returns an empty list — a stale periodic delay (e.g.
    a task that was renamed or removed) becomes a no-op rather than a
    Rejection / crash.  This keeps the workflow robust to schema drift.
    """
    from fleuve.model import CmdPeriodicTaskDue, EvPeriodicDelay

    cls = type(self)
    handlers: dict[str, tuple[Any, Callable]] = getattr(
        cls, "_periodic_handlers", {}
    )
    entry = handlers.get(cmd.task_id)
    if entry is None:
        return []
    spec, fn = entry
    user_events = list(fn(self) or [])
    if spec.is_enabled:
        user_events.append(
            EvPeriodicDelay(
                id=f"periodic_{cmd.task_id}",
                delay_until=spec.next_delay_until(),
                next_cmd=CmdPeriodicTaskDue(task_id=cmd.task_id),
                task_id=cmd.task_id,
            )
        )
    return user_events


def _kickstart_periodic(self: Any, *only: str) -> list[Any]:
    """Return :class:`fleuve.model.EvPeriodicDelay` events to start the
    workflow's periodic tasks.

    Call from inside an ``@command`` method (typically the activation
    one) to kick off all enabled periodic tasks::

        @command
        def activate(self) -> list[Event]:
            return [EvActivated(...), *self.kickstart_periodic()]

    Args:
        *only: Optional task ids (method names) to limit the kickstart
            to.  When empty, every ``@periodic_task`` on the class is
            included.  Useful when activation is split across multiple
            commands and only some tasks should fire from each.

    Tasks whose delay is already present in ``state.schedules`` (i.e.
    a previous activation already scheduled them) are silently skipped
    — re-activation is idempotent.  Tasks with ``every=timedelta(0)``
    (disabled) are also skipped.
    """
    from fleuve.model import CmdPeriodicTaskDue, EvPeriodicDelay

    cls = type(self)
    handlers: dict[str, tuple[Any, Callable]] = getattr(
        cls, "_periodic_handlers", {}
    )
    if only:
        unknown = [t for t in only if t not in handlers]
        if unknown:
            raise KeyError(
                f"{cls.__name__} has no @periodic_task method(s) "
                f"named {unknown!r}; available: {sorted(handlers)}"
            )
        selected = list(only)
    else:
        selected = list(handlers.keys())

    already: set[str] = set()
    state = getattr(self, "state", None)
    if state is not None:
        already = {s.id for s in getattr(state, "schedules", [])}

    out: list[Any] = []
    for tid in selected:
        spec, _ = handlers[tid]
        delay_id = f"periodic_{tid}"
        if not spec.is_enabled or delay_id in already:
            continue
        out.append(
            EvPeriodicDelay(
                id=delay_id,
                delay_until=spec.first_delay_until(),
                next_cmd=CmdPeriodicTaskDue(task_id=tid),
                task_id=tid,
            )
        )
    return out


def _build_instance(cls: type, state: Any) -> Any:
    """Construct a class-based workflow instance bound to *state*.

    Uses Pydantic's ``model_construct`` (no validation, no copy) for speed.
    Shallow-copies the state so an ``@command`` method that accidentally
    mutates ``self.state`` cannot corrupt the caller's reference.
    """
    if state is not None and isinstance(state, BaseModel):
        bound_state = state.model_copy()  # shallow; cheap
    else:
        bound_state = state
    return cls.model_construct(state=bound_state)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Convenience helpers exposed via the Workflow base


def _cmd(cls: type, method_name: str, **kwargs: Any) -> BaseModel:
    """Build a typed command instance for a method.

    Usage from inside a ``@command`` method that schedules a delay::

        return [
            MyDelay(
                id="check",
                delay_until=...,
                next_cmd=type(self).cmd("perform_check", x=1),
            )
        ]

    Or from outside (rare — prefer ``repo.invoke`` / ``repo.workflow(id).x()``)::

        await repo.process_command(id, Counter.cmd("increment", by=2))
    """
    models: dict[str, Type[BaseModel]] = cls._command_models  # type: ignore[attr-defined]
    if method_name not in models:
        raise KeyError(
            f"{cls.__name__} has no @command method named {method_name!r}; "
            f"available: {sorted(models)}"
        )
    cmd_model = models[method_name]
    params_model = getattr(cmd_model, "__fleuve_params_model__")
    return cmd_model(method=method_name, params=params_model(**kwargs))


def _command_union(cls: type) -> Any:
    """Return a union of every command kind this workflow can dispatch.

    Members:

    - The auto-built per-method models for every ``@command``, joined by
      ``method`` discriminator (O(1) deserialization).
    - :class:`fleuve.model.CmdPeriodicTaskDue` — added automatically when
      the class has any ``@periodic_task`` method, so the events table's
      ``EvDelayComplete[command_union]`` can store periodic
      delay-completions without users having to remember to widen the
      union manually.

    Use as the target of ``PydanticType`` for any DB column that stores a
    command (``DelaySchedule.next_command``, the ``next_cmd`` argument of
    ``EvDelayComplete[...]`` in event-body unions, custom command
    tables)::

        class CounterDelaySchedule(DelaySchedule):
            next_command = mapped_column(
                PydanticType(Counter.command_union()),
                nullable=False,
            )

    Raises ``TypeError`` if *cls* has no ``@command`` and no
    ``@periodic_task`` methods (a silent empty union would deserialize
    to nothing useful and produce confusing runtime errors).
    """
    models: dict[str, Type[BaseModel]] = getattr(cls, "_command_models", {})
    periodic = getattr(cls, "_periodic_handlers", {})
    if not models and not periodic:
        raise TypeError(
            f"{cls.__name__} has no @command or @periodic_task methods; "
            f"cannot build a command union"
        )

    method_branch: Any = None
    if models:
        model_list = list(models.values())
        if len(model_list) == 1:
            method_branch = model_list[0]
        else:
            method_branch = Annotated[
                Union[tuple(model_list)], Field(discriminator="method")
            ]

    if periodic:
        from fleuve.model import CmdPeriodicTaskDue

        if method_branch is None:
            return CmdPeriodicTaskDue
        # Outer untagged union: try the discriminated method-branch
        # first, fall back to CmdPeriodicTaskDue (which has no `method`
        # field).  Works because Pydantic's discriminator on the inner
        # branch correctly rejects payloads that lack `method`.
        return Union[method_branch, CmdPeriodicTaskDue]

    return method_branch
