"""PeriodicTask — declarative periodic workflow scheduling.

Eliminates the per-task boilerplate of concrete EvDelay subclasses, delay-id
constants, and repeated decide/reschedule branches that accumulate when a
workflow has multiple recurring tasks.

## Usage

Declare periodic tasks as a class-level argument::

    from fleuve import Workflow, PeriodicTask
    from datetime import timedelta

    class VaultWorkflow(Workflow[VaultEvent, VaultCommand, VaultState, VaultExternal],
                        periodic_tasks=[
        PeriodicTask(id="psyop_check",      interval=timedelta(hours=6),
                     first_run_after=timedelta(minutes=1)),
        PeriodicTask(id="entity_reconcile", interval=timedelta(hours=12)),
        PeriodicTask(id="context_brief",    interval=timedelta(hours=24),
                     jitter=timedelta(minutes=10)),
    ]):
        ...

Add ``EvPeriodicDelay`` and ``CmdPeriodicTaskDue`` to your event / command unions::

    VaultEvent   = Union[EvPsyopCheckRequested, ..., EvPeriodicDelay,
                         EvDelayComplete[VaultCommand]]
    VaultCommand = Union[CmdActivate, CmdPsyopCheckDone, ..., CmdPeriodicTaskDue]

In ``decide``, use the generated classmethods::

    @staticmethod
    def decide(state, cmd):
        if isinstance(cmd, CmdActivate):
            return [EvVaultActivated(), *VaultWorkflow.schedule_periodic_tasks(state)]

        if isinstance(cmd, CmdPeriodicTaskDue):
            match cmd.task_id:
                case "psyop_check":
                    return [EvPsyopCheckRequested(vault_id=state.vault_id)]
                case "entity_reconcile":
                    return [EvEntityReconcileRequested(vault_id=state.vault_id)]

        if isinstance(cmd, CmdPsyopCheckDone):
            return [
                EvPsyopChecked(),
                *VaultWorkflow.reschedule_periodic_task("psyop_check"),
            ]

## What is generated

``Workflow.__init_subclass__`` (when ``periodic_tasks`` is provided) injects
three classmethods:

- ``schedule_periodic_tasks(state=None)`` — returns a list of
  ``EvPeriodicDelay`` events for all enabled tasks.  Pass ``state`` so that
  tasks that are already scheduled (present in ``state.schedules`` or
  signalled by a non-None ``last_x_at``-style field) are skipped.  Omit
  ``state`` (or pass ``None``) to schedule all tasks unconditionally (e.g.
  on first activation).

- ``reschedule_periodic_task(task_id)`` — returns a list containing one
  ``EvPeriodicDelay`` for the next run of the named task, or an empty list if
  the task is disabled (interval == 0).

- ``get_periodic_task(task_id)`` — returns the ``PeriodicTask`` spec for
  inspection.

## Jitter

When ``jitter`` is set, ``delay_until`` is spread uniformly over
``[base, base + jitter]``.  This prevents thundering-herd issues when many
workflows are activated simultaneously.

## Disabling a task

Set ``interval=timedelta(0)`` to disable a task entirely.  The
``schedule_periodic_tasks`` and ``reschedule_periodic_task`` methods silently
return ``[]`` for disabled tasks.
"""

from __future__ import annotations

import datetime
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PeriodicTask:
    """Specification for one periodic recurring task.

    Args:
        id: Unique identifier within the workflow.  Used as ``task_id`` in
            ``CmdPeriodicTaskDue`` so you can dispatch in ``decide``.
        interval: How often the task runs.  ``timedelta(0)`` disables it.
        first_run_after: How long after workflow activation before the first
            run.  Defaults to 1 minute.  Use this to stagger tasks across
            workflows activated at the same time.
        jitter: Maximum random offset added to the scheduled time to spread
            load.  Defaults to no jitter.
    """

    id: str
    interval: datetime.timedelta
    first_run_after: datetime.timedelta = field(
        default_factory=lambda: datetime.timedelta(minutes=1)
    )
    jitter: datetime.timedelta = field(default_factory=datetime.timedelta)

    @property
    def is_enabled(self) -> bool:
        return self.interval.total_seconds() > 0

    def first_delay_until(
        self, now: datetime.datetime | None = None
    ) -> datetime.datetime:
        """Compute ``delay_until`` for the very first run."""
        base = (
            now or datetime.datetime.now(datetime.timezone.utc)
        ) + self.first_run_after
        return self._apply_jitter(base)

    def next_delay_until(
        self, now: datetime.datetime | None = None
    ) -> datetime.datetime:
        """Compute ``delay_until`` for a subsequent run (after completion)."""
        base = (now or datetime.datetime.now(datetime.timezone.utc)) + self.interval
        return self._apply_jitter(base)

    def _apply_jitter(self, base: datetime.datetime) -> datetime.datetime:
        if self.jitter.total_seconds() > 0:
            offset = random.uniform(0, self.jitter.total_seconds())
            base = base + datetime.timedelta(seconds=offset)
        return base


def _inject_periodic_task_methods(cls: Any, tasks: list[PeriodicTask]) -> None:
    """Inject schedule_periodic_tasks, reschedule_periodic_task, get_periodic_task
    as classmethods on ``cls``."""

    from fleuve.model import CmdPeriodicTaskDue, EvPeriodicDelay

    task_map: dict[str, PeriodicTask] = {t.id: t for t in tasks}

    @classmethod  # type: ignore[misc]
    def schedule_periodic_tasks(klass: Any, state: Any = None) -> list[EvPeriodicDelay]:
        """Return ``EvPeriodicDelay`` events that should be emitted to schedule
        all enabled periodic tasks.

        Call this from ``decide`` in the workflow-activation branch to kick off
        all recurring tasks::

            if isinstance(cmd, CmdActivate):
                return [EvActivated(), *VaultWorkflow.schedule_periodic_tasks(state)]

        Args:
            state: Current workflow state.  When provided, tasks whose delay is
                already registered in ``state.schedules`` are skipped to avoid
                double-scheduling on re-activation.  Pass ``None`` to schedule
                all tasks unconditionally.

        Returns:
            A list of ``EvPeriodicDelay`` events, one per enabled task.
        """
        already_scheduled: set[str] = set()
        if state is not None:
            already_scheduled = {s.id for s in getattr(state, "schedules", [])}
            # Also check the delay_id format used by EvPeriodicDelay
            already_scheduled |= {
                f"periodic_{t_id}" for t_id in already_scheduled if t_id in task_map
            }

        result: list[EvPeriodicDelay] = []
        for task in task_map.values():
            if not task.is_enabled:
                continue
            delay_id = f"periodic_{task.id}"
            if delay_id in already_scheduled or task.id in already_scheduled:
                continue
            result.append(
                EvPeriodicDelay(
                    id=delay_id,
                    delay_until=task.first_delay_until(),
                    next_cmd=CmdPeriodicTaskDue(task_id=task.id),
                    task_id=task.id,
                )
            )
        return result

    @classmethod  # type: ignore[misc]
    def reschedule_periodic_task(klass: Any, task_id: str) -> list[EvPeriodicDelay]:
        """Return an ``EvPeriodicDelay`` event that re-arms the named task.

        Call this from ``decide`` in the completion-command branch::

            if isinstance(cmd, CmdPsyopCheckDone):
                return [
                    EvPsyopChecked(),
                    *VaultWorkflow.reschedule_periodic_task("psyop_check"),
                ]

        Returns an empty list if the task is disabled (``interval == 0``).
        """
        task = task_map.get(task_id)
        if task is None:
            raise ValueError(
                f"Unknown periodic task '{task_id}' on {cls.__name__}. "
                f"Known tasks: {list(task_map)}"
            )
        if not task.is_enabled:
            return []
        return [
            EvPeriodicDelay(
                id=f"periodic_{task.id}",
                delay_until=task.next_delay_until(),
                next_cmd=CmdPeriodicTaskDue(task_id=task.id),
                task_id=task.id,
            )
        ]

    @classmethod  # type: ignore[misc]
    def get_periodic_task(klass: Any, task_id: str) -> PeriodicTask:
        """Return the ``PeriodicTask`` spec for ``task_id``."""
        try:
            return task_map[task_id]
        except KeyError:
            raise ValueError(
                f"Unknown periodic task '{task_id}' on {cls.__name__}. "
                f"Known tasks: {list(task_map)}"
            )

    cls._periodic_tasks = list(tasks)
    cls.schedule_periodic_tasks = schedule_periodic_tasks
    cls.reschedule_periodic_task = reschedule_periodic_task
    cls.get_periodic_task = get_periodic_task
