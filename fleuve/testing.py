"""Integration test helpers for Fleuve workflows.

``WorkflowTestHarness`` provides an in-memory workflow executor that does
**not** require a real database or NATS connection.  It is suitable for
fast unit/integration tests of full decide→evolve→side-effect cycles.

Example::

    harness = WorkflowTestHarness(MyWorkflow, MyAdapter())

    state, events = await harness.send_command("wf-1", MyCommand(x=1))
    assert state.some_field == expected

    # Advance simulated time so pending delays fire
    await harness.advance_time(timedelta(seconds=5))

    # Assert subscription state
    harness.assert_subscriptions("wf-1", [Sub(workflow_id="*", event_type="order.*")])

    # What-if simulation (does not mutate harness state)
    result = harness.simulate("wf-1", AnotherCommand())
"""

from __future__ import annotations

import asyncio
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Generic, Type, TypeVar

from pydantic import BaseModel

from fleuve.model import (
    AlreadyExists,
    EvDelay,
    EvDelayComplete,
    Rejection,
    StateBase,
    Sub,
    Workflow,
)
from fleuve.repo import StoredState

C = TypeVar("C", bound=BaseModel)
E = TypeVar("E", bound=BaseModel)
S = TypeVar("S", bound=StateBase)
Wf = TypeVar("Wf", bound=Workflow)


@dataclass
class _PendingDelay:
    workflow_id: str
    delay_id: str
    fire_at: datetime.datetime
    next_cmd: Any
    cron_expression: str | None = None
    timezone: str | None = None


class WorkflowTestHarness(Generic[Wf]):
    """In-memory workflow harness for testing.

    Supports:
    - ``send_command`` — run a command and return the new state + events
    - ``create_new`` — create a new workflow instance
    - ``advance_time`` — fire all pending delays whose fire time ≤ now + delta
    - ``assert_subscriptions`` — assert expected subscriptions for a workflow
    - ``simulate`` — what-if command without mutating harness state
    - ``get_state`` — retrieve current state for a workflow ID

    Limitations (by design):
    - No persistence; everything is in memory and lost when the harness is
      garbage-collected.
    - Side effects (``act_on``) are **not** executed; only decide/evolve are
      run.  Use real integration tests with a database for full side-effect
      coverage.
    - No real NATS or DB connectivity.
    """

    def __init__(self, workflow_type: Type[Wf]) -> None:
        self._workflow_type = workflow_type
        self._states: dict[str, StoredState] = {}
        self._pending_delays: list[_PendingDelay] = []
        self._simulated_now: datetime.datetime = datetime.datetime.now(
            datetime.timezone.utc
        )

    # ------------------------------------------------------------------
    # Core commands
    # ------------------------------------------------------------------

    async def create_new(
        self, workflow_id: str, cmd: Any, tags: list[str] | None = None
    ) -> tuple[StoredState, list] | Rejection:
        """Create a new workflow instance.

        Returns ``(StoredState, events)`` on success, ``Rejection`` on failure.
        """
        if workflow_id in self._states:
            return AlreadyExists(msg=f"Workflow '{workflow_id}' already exists")

        events = self._workflow_type.decide(None, cmd)
        if isinstance(events, Rejection):
            return events
        if not events:
            return Rejection(msg="Cannot create workflow with no events")

        state = self._workflow_type.evolve_(None, events)
        ss = StoredState(id=workflow_id, state=state, version=len(events))
        self._states[workflow_id] = ss
        self._register_delays(workflow_id, events, len(events))
        return ss, events

    async def send_command(
        self, workflow_id: str, cmd: Any
    ) -> tuple[StoredState, list] | Rejection:
        """Process a command against an existing workflow.

        Returns ``(StoredState, events)`` on success, ``Rejection`` on failure.
        Raises ``KeyError`` if the workflow does not exist.
        """
        if workflow_id not in self._states:
            raise KeyError(f"Workflow '{workflow_id}' not found in harness")

        stored = self._states[workflow_id]
        lifecycle = getattr(stored.state, "lifecycle", "active")
        if lifecycle == "paused":
            return Rejection(msg="Workflow is paused")
        if lifecycle == "cancelled":
            return Rejection(msg="Workflow is cancelled")

        events = self._workflow_type.decide(stored.state, cmd)
        if isinstance(events, Rejection):
            return events
        if not events:
            return stored, []

        new_state = self._workflow_type.evolve_(stored.state, events)
        new_version = stored.version + len(events)
        ss = StoredState(id=workflow_id, state=new_state, version=new_version)
        self._states[workflow_id] = ss
        self._register_delays(workflow_id, events, new_version)
        return ss, events

    def simulate(
        self, workflow_id: str, cmd: Any
    ) -> tuple[StoredState, list] | Rejection:
        """What-if simulation: apply a command without mutating harness state.

        Returns ``(StoredState, events)`` or ``Rejection``.
        Does **not** persist the result.
        """
        if workflow_id not in self._states:
            raise KeyError(f"Workflow '{workflow_id}' not found in harness")

        stored = self._states[workflow_id]
        lifecycle = getattr(stored.state, "lifecycle", "active")
        if lifecycle == "paused":
            return Rejection(msg="Workflow is paused")
        if lifecycle == "cancelled":
            return Rejection(msg="Workflow is cancelled")

        events = self._workflow_type.decide(stored.state, cmd)
        if isinstance(events, Rejection):
            return events
        if not events:
            return stored, []

        new_state = self._workflow_type.evolve_(stored.state, events)
        ss = StoredState(
            id=workflow_id, state=new_state, version=stored.version + len(events)
        )
        return ss, events

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------

    async def advance_time(self, delta: datetime.timedelta) -> list[tuple[str, Any]]:
        """Fire all pending delays whose fire time ≤ simulated_now + delta.

        Processes delays in chronological order.  Each delay that fires
        causes ``event_to_cmd`` → ``send_command`` to execute on the
        target workflow.

        Returns a list of ``(workflow_id, EvDelayComplete)`` tuples for
        every delay that fired.
        """
        self._simulated_now += delta
        fired = []

        # Sort by fire_at so delays fire in order
        due = sorted(
            [d for d in self._pending_delays if d.fire_at <= self._simulated_now],
            key=lambda d: d.fire_at,
        )

        for pending in due:
            self._pending_delays.remove(pending)
            ev_complete = EvDelayComplete(
                delay_id=pending.delay_id,
                at=pending.fire_at,
                next_cmd=pending.next_cmd,
            )
            cmd = self._workflow_type.event_to_cmd(ev_complete)
            if cmd is not None and pending.workflow_id in self._states:
                await self.send_command(pending.workflow_id, cmd)

            # Reschedule cron
            if pending.cron_expression:
                next_fire = self._next_cron_fire(
                    pending.cron_expression, pending.timezone
                )
                if next_fire:
                    self._pending_delays.append(
                        _PendingDelay(
                            workflow_id=pending.workflow_id,
                            delay_id=pending.delay_id,
                            fire_at=next_fire,
                            next_cmd=pending.next_cmd,
                            cron_expression=pending.cron_expression,
                            timezone=pending.timezone,
                        )
                    )

            fired.append((pending.workflow_id, ev_complete))

        return fired

    # ------------------------------------------------------------------
    # Assertions
    # ------------------------------------------------------------------

    def assert_subscriptions(
        self,
        workflow_id: str,
        expected: list[Sub],
    ) -> None:
        """Assert that ``workflow_id`` has exactly the given subscriptions.

        Raises ``AssertionError`` on mismatch.
        """
        stored = self._states.get(workflow_id)
        if stored is None:
            raise AssertionError(f"Workflow '{workflow_id}' not found in harness")

        actual = list(getattr(stored.state, "subscriptions", []))
        assert actual == expected, (
            f"Subscription mismatch for '{workflow_id}':\n"
            f"  expected: {expected}\n"
            f"  actual:   {actual}"
        )

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    def get_state(self, workflow_id: str) -> StoredState:
        """Return current stored state for ``workflow_id``.

        Raises ``KeyError`` if not found.
        """
        return self._states[workflow_id]

    @property
    def workflow_ids(self) -> list[str]:
        """All workflow IDs currently tracked by the harness."""
        return list(self._states.keys())

    @property
    def pending_delays(self) -> list[_PendingDelay]:
        """Read-only view of pending delays."""
        return list(self._pending_delays)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_delays(
        self, workflow_id: str, events: list, current_version: int
    ) -> None:
        """Scan events for EvDelay instances and register them as pending delays."""
        for ev in events:
            if isinstance(ev, EvDelay):
                # Remove any existing delay with the same id for this workflow
                self._pending_delays = [
                    d
                    for d in self._pending_delays
                    if not (d.workflow_id == workflow_id and d.delay_id == ev.id)
                ]
                self._pending_delays.append(
                    _PendingDelay(
                        workflow_id=workflow_id,
                        delay_id=ev.id,
                        fire_at=ev.delay_until,
                        next_cmd=ev.next_cmd,
                        cron_expression=ev.cron_expression,
                        timezone=ev.timezone,
                    )
                )

    def _next_cron_fire(
        self, cron_expression: str, timezone_name: str | None
    ) -> datetime.datetime | None:
        try:
            from croniter import croniter  # type: ignore[import-untyped]
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                tz = ZoneInfo(timezone_name or "UTC")
            except ZoneInfoNotFoundError:
                tz = ZoneInfo("UTC")

            now = self._simulated_now.astimezone(tz)
            cron = croniter(cron_expression, now)
            next_dt: datetime.datetime = cron.get_next(datetime.datetime)
            if next_dt.tzinfo is None:
                next_dt = next_dt.replace(tzinfo=tz)
            return next_dt
        except Exception:
            return None
