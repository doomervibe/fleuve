"""Integration tests for the class-based (OOP) workflow definition style.

This file defines a self-contained ``Counter`` workflow that uses
``@command`` / ``@event_handler`` decorators and exercises every
integration point listed in the OOP rework spec:

- ``AsyncRepo.process_command`` / ``bulk_process_command`` /
  ``create_new`` / ``cancel_workflow`` / ``pause_workflow`` /
  ``resume_workflow`` / ``replay_workflow``.
- ``repo.invoke`` / ``repo.bulk_invoke`` / ``repo.workflow(id).method()``.
- ``EvDelay`` with class-based commands as ``next_cmd`` payload (the
  riskiest round-trip: serialize → store → fire → ``EvDelayComplete``
  unwrap → re-dispatch).
- Snapshots via ``db_snapshot_model`` + ``snapshot_interval`` — replay
  must reconstruct identical state.
- Subscriptions and the ``Adapter.act_on`` enrichment pattern.
- ``WorkflowRejection`` exception → ``Rejection`` boundary conversion.
"""

import datetime
import uuid
from typing import Any, AsyncGenerator, Literal, Union

import pytest
from nats.aio.client import Client as NATS
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import Mapped, mapped_column

from fleuve import (
    Adapter,
    AsyncRepo,
    EuphStorageNATS,
    EvDelay,
    EvDelayComplete,
    Rejection,
    StateBase,
    StoredState,
    Sub,
    Workflow,
    WorkflowRejection,
    command,
    event_handler,
    handles,
)
from fleuve.model import (
    EventBase,
    EvSystemCancel,
    EvSystemPause,
    EvSystemResume,
)
from fleuve.postgres import (
    Base,
    DelaySchedule,
    PydanticType,
    Snapshot,
    StoredEvent,
    Subscription,
)
from sqlalchemy import BigInteger, Computed, String


# ---------------------------------------------------------------------------
# Test workflow: Counter
#
# An OOP workflow that:
# - increments a counter
# - emits a domain event for each increment
# - schedules a tick via EvDelay (next_cmd routes back through the OOP path)
# - exposes a "stop" method that emits a terminal event
# - subscribes to events from another workflow via Sub
# ---------------------------------------------------------------------------


class CounterState(StateBase):
    """Persistent state for the Counter workflow."""

    count: int = 0
    ticks: int = 0
    history: list[int] = Field(default_factory=list)
    subscriptions: list[Sub] = Field(default_factory=list)
    external_subscriptions: list = Field(default_factory=list)


class EvIncremented(EventBase):
    type: Literal["counter.incremented"] = "counter.incremented"
    by: int


class EvTicked(EventBase):
    type: Literal["counter.ticked"] = "counter.ticked"
    at: datetime.datetime


class EvStopped(EventBase):
    type: Literal["counter.stopped"] = "counter.stopped"
    reason: str


class EvObserved(EventBase):
    """Emitted when an external event flows in via subscription."""

    type: Literal["counter.observed"] = "counter.observed"
    source: str
    by: int


class CounterTickDelay(EvDelay["CounterCmdUnion"]):  # type: ignore[type-arg]
    """User-declared concrete EvDelay for tick scheduling.

    The Generic ``next_cmd`` type points at the auto-built command union
    so that the framework can serialize/deserialize the round-trip cleanly.
    """

    type: Literal["counter.tick_delay"] = "counter.tick_delay"


# Stub forward reference target until the class is built.
CounterCmdUnion: Any = None


class Counter(Workflow):
    """Class-based Counter workflow used by every OOP integration test."""

    state: CounterState | None = None

    @classmethod
    def name(cls) -> str:
        return "oop_counter"

    @command
    def increment(self, by: int) -> list[EvIncremented]:
        if by <= 0:
            raise WorkflowRejection("by must be positive")
        return [EvIncremented(by=by)]

    @command
    def increment_with_meta(
        self, by: int, when: datetime.datetime
    ) -> list[EvIncremented]:
        # Validates that nested non-trivial annotations (datetime here, but
        # also exercised with Pydantic models in the unit tests below) flow
        # through the dispatcher unchanged.
        assert isinstance(when, datetime.datetime)
        return [EvIncremented(by=by)]

    @command
    def schedule_tick(
        self, in_seconds: int, then_increment_by: int
    ) -> list[CounterTickDelay]:
        delay_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            seconds=in_seconds
        )
        # Build the round-trip cmd via the typed helper.
        next_cmd = type(self).cmd("tick", increment_by=then_increment_by)
        return [
            CounterTickDelay(
                id=f"tick-{in_seconds}",
                delay_until=delay_until,
                next_cmd=next_cmd,
            )
        ]

    @command
    def tick(self, increment_by: int) -> list[Any]:
        return [
            EvTicked(at=datetime.datetime.now(datetime.timezone.utc)),
            EvIncremented(by=increment_by),
        ]

    @command
    def stop(self, reason: str) -> list[EvStopped]:
        return [EvStopped(reason=reason)]

    @command
    def observe(self, source: str, by: int) -> list[EvObserved]:
        return [EvObserved(source=source, by=by)]

    @event_handler
    def _on_incremented(self, ev: EvIncremented) -> CounterState:
        cur = self.state or CounterState()
        return cur.apply(
            count=cur.count + ev.by,
            history=cur.history + [ev.by],
        )

    @event_handler
    def _on_ticked(self, ev: EvTicked) -> CounterState:
        cur = self.state or CounterState()
        return cur.apply(ticks=cur.ticks + 1)

    @event_handler
    def _on_stopped(self, ev: EvStopped) -> CounterState:
        cur = self.state or CounterState()
        # State is unchanged but lifecycle propagates via system events.
        return cur

    @event_handler
    def _on_observed(self, ev: EvObserved) -> CounterState:
        cur = self.state or CounterState()
        return cur.apply(count=cur.count + ev.by)

    @staticmethod
    def is_final_event(e: Any) -> bool:
        return isinstance(e, EvStopped)


# Now that the class exists with all its @command methods, finalize the
# typed cmd union for use in DB columns / typed clients.
CounterCmdUnion = Counter.command_union()


# ---------------------------------------------------------------------------
# Source workflow used for subscription tests (publishes an EvSourcePublished
# that Counter subscribes to via Sub).
# ---------------------------------------------------------------------------


class EvSourcePublished(EventBase):
    type: Literal["src.published"] = "src.published"
    by: int


class SourceState(StateBase):
    last: int = 0
    subscriptions: list[Sub] = Field(default_factory=list)
    external_subscriptions: list = Field(default_factory=list)


class Source(Workflow):
    state: SourceState | None = None

    @classmethod
    def name(cls) -> str:
        return "oop_source"

    @command
    def publish(self, by: int) -> list[EvSourcePublished]:
        return [EvSourcePublished(by=by)]

    @event_handler
    def _on_published(self, ev: EvSourcePublished) -> SourceState:
        cur = self.state or SourceState()
        return cur.apply(last=ev.by)


SourceCmdUnion = Source.command_union()


# ---------------------------------------------------------------------------
# Adapter: when Counter subscribes to Source.EvSourcePublished, the runner
# would invoke this adapter. We test via direct invocation.
# ---------------------------------------------------------------------------


class CounterAdapter(Adapter[EvSourcePublished, BaseModel]):
    @handles(EvSourcePublished)
    async def _on_source(
        self, ev: EvSourcePublished, context: Any
    ) -> AsyncGenerator[BaseModel, None]:
        yield Counter.cmd("observe", source="src", by=ev.by)


# ---------------------------------------------------------------------------
# Database models for Counter — stored under a separate set of tables so they
# do not collide with the legacy TestWorkflow tables in conftest.
# ---------------------------------------------------------------------------


_CounterEventBody = Union[
    EvIncremented,
    EvTicked,
    EvStopped,
    EvObserved,
    CounterTickDelay,
    EvDelayComplete[CounterCmdUnion],  # type: ignore[valid-type]
    EvSystemPause,
    EvSystemResume,
    EvSystemCancel,
]


class CounterEventModel(StoredEvent):
    __tablename__ = "oop_counter_events"

    @declared_attr
    def body(cls) -> Mapped:  # type: ignore[type-arg,override]
        return mapped_column(
            PydanticType(_CounterEventBody),  # type: ignore[arg-type]
            nullable=False,
        )

    body_raw: Mapped[dict] = mapped_column(
        JSONB, Computed("body", persisted=True), nullable=True
    )


class CounterSubscriptionModel(Subscription):
    __tablename__ = "oop_counter_subs"


class CounterDelayScheduleModel(DelaySchedule):
    __tablename__ = "oop_counter_delays"

    @declared_attr
    def next_command(cls) -> Mapped:  # type: ignore[type-arg,override]
        return mapped_column(
            PydanticType(CounterCmdUnion),
            nullable=False,
        )


class CounterSnapshotModel(Snapshot):
    __tablename__ = "oop_counter_snapshots"

    @declared_attr
    def state(cls) -> Mapped:  # type: ignore[type-arg,override]
        return mapped_column(
            PydanticType(CounterState),
            nullable=False,
        )


# Source workflow has no DB models in this test file: the adapter test
# constructs a synthetic EvSourcePublished and feeds it directly into the
# CounterAdapter, which is the only OOP-relevant path.


# ---------------------------------------------------------------------------
# Pure unit tests (no DB) — fast feedback on the dispatcher itself
# ---------------------------------------------------------------------------


class TestOopUnit:
    """Pure-Python checks for decorators, schema derivation, and dispatch."""

    def test_command_models_registered(self) -> None:
        models = Counter._command_models  # type: ignore[attr-defined]
        assert set(models) >= {
            "increment",
            "tick",
            "schedule_tick",
            "stop",
            "observe",
        }

    def test_wire_format_is_nested(self) -> None:
        cmd = Counter.cmd("increment", by=2)
        dumped = cmd.model_dump()
        assert dumped == {"method": "increment", "params": {"by": 2}}
        # And round-trips through JSON
        rebuilt = type(cmd).model_validate_json(cmd.model_dump_json())
        assert rebuilt.method == "increment"
        assert rebuilt.params.by == 2  # type: ignore[attr-defined]

    def test_command_union_is_discriminated(self) -> None:
        # Using the union to validate a JSON payload picks the right tag
        # without needing to know the concrete model class.
        from pydantic import TypeAdapter

        adapter = TypeAdapter(CounterCmdUnion)
        cmd = adapter.validate_python(
            {"method": "tick", "params": {"increment_by": 5}}
        )
        assert cmd.method == "tick"
        assert cmd.params.increment_by == 5  # type: ignore[attr-defined]

    def test_unknown_method_via_cmd_raises(self) -> None:
        with pytest.raises(KeyError):
            Counter.cmd("does_not_exist")

    def test_command_union_empty_workflow_raises(self) -> None:
        # A class declared with @event_handler but no @command should not be
        # able to build a command union (advisor-flagged guardrail).
        class HandlersOnly(Workflow):
            state: CounterState | None = None

            @classmethod
            def name(cls) -> str:
                return "handlers_only"

            @event_handler
            def _h(self, ev: EvIncremented) -> CounterState:
                return self.state or CounterState()

        with pytest.raises(TypeError):
            HandlersOnly.command_union()

    def test_kwargs_preserve_nested_pydantic(self) -> None:
        # Advisor's mandatory test: nested Pydantic objects must reach the
        # handler intact (not as a dict from model_dump()).
        class Param(BaseModel):
            tag: str
            n: int

        captured: dict[str, Any] = {}

        class WithNested(Workflow):
            state: CounterState | None = None

            @classmethod
            def name(cls) -> str:
                return "with_nested"

            @command
            def take(self, p: Param, k: int) -> list[EvIncremented]:
                captured["p"] = p
                captured["k"] = k
                return [EvIncremented(by=k)]

            @event_handler
            def _h(self, ev: EvIncremented) -> CounterState:
                return self.state or CounterState()

        cmd = WithNested.cmd("take", p=Param(tag="a", n=1), k=7)
        events = WithNested.decide(None, cmd)
        assert isinstance(events, list)
        assert isinstance(captured["p"], Param)
        assert captured["p"].tag == "a"
        assert captured["k"] == 7

    def test_rejection_via_exception(self) -> None:
        bad = Counter.cmd("increment", by=-1)
        result = Counter.decide(None, bad)
        assert isinstance(result, Rejection)
        assert "positive" in result.msg

    def test_evolve_dispatch(self) -> None:
        s = Counter.evolve_(None, [EvIncremented(by=2), EvIncremented(by=3)])
        assert s.count == 5
        assert s.history == [2, 3]

    def test_buggy_handler_does_not_crash_framework(self) -> None:
        """Pin down what the shallow-copy guardrail actually protects.

        Pydantic's ``model_copy`` is shallow, so it shares nested
        container references (e.g. lists).  The guardrail prevents
        a *top-level field reassignment* inside an ``@command`` from
        bleeding back to the caller; mutations to a nested list can
        still leak.  The contract is "do not mutate self.state" — this
        test only verifies the framework does not blow up when a buggy
        handler does.
        """
        captured: dict[str, Any] = {}

        class Mutator(Workflow):
            state: CounterState | None = None

            @classmethod
            def name(cls) -> str:
                return "mutator"

            @command
            def evil_top_level(self, new_count: int) -> list[EvIncremented]:
                # Reassign a top-level field (object.__setattr__ to bypass
                # any frozen-ish protection).
                if self.state:
                    object.__setattr__(self.state, "count", new_count)
                    captured["mutated_local_count"] = self.state.count
                return [EvIncremented(by=1)]

            @event_handler
            def _h(self, ev: EvIncremented) -> CounterState:
                return self.state or CounterState()

        original = CounterState(count=0, history=[1, 2, 3])
        Mutator.decide(original, Mutator.cmd("evil_top_level", new_count=42))

        # Top-level reassignment on the shallow copy did not bleed back to
        # the caller — that's what the guardrail buys us.
        assert original.count == 0
        assert captured["mutated_local_count"] == 42


# ---------------------------------------------------------------------------
# Integration tests — require the DB (and NATS for some).  Reuse the
# conftest test_engine / test_session_maker fixtures, which call
# Base.metadata.create_all at the start of each test.
# ---------------------------------------------------------------------------


@pytest.fixture
async def counter_storage(nats_client: NATS) -> AsyncGenerator[EuphStorageNATS, None]:
    bucket_name = f"oop_counter_{uuid.uuid4().hex[:8]}"
    storage: EuphStorageNATS = EuphStorageNATS(
        c=nats_client, bucket=bucket_name, s=CounterState
    )
    await storage.__aenter__()
    yield storage
    await storage.__aexit__(None, None, None)
    try:
        js = nats_client.jetstream()
        await js.delete_key_value(bucket_name)
    except Exception:
        pass


@pytest.fixture
def counter_repo(test_session_maker, counter_storage) -> AsyncRepo:
    return AsyncRepo(
        session_maker=test_session_maker,
        es=counter_storage,
        model=Counter,
        db_event_model=CounterEventModel,
        db_sub_model=CounterSubscriptionModel,
        db_snapshot_model=CounterSnapshotModel,
        db_delay_schedule_model=CounterDelayScheduleModel,
        snapshot_interval=3,
    )


class TestOopRepo:
    """End-to-end repo tests: create_new + invoke + workflow proxy + bulk_invoke."""

    @pytest.mark.asyncio
    async def test_create_new_via_invoke(self, counter_repo, test_session) -> None:
        # Build the cmd with the model.cmd helper — repo.create_new still
        # accepts a typed Pydantic command.
        result = await counter_repo.create_new(
            Counter.cmd("increment", by=10), "wf-1"
        )
        assert not isinstance(result, Rejection)
        assert result.state.count == 10
        assert result.state.history == [10]

        # Event row exists with the discriminator set to our event type.
        ev = await test_session.scalar(
            select(CounterEventModel)
            .where(CounterEventModel.workflow_id == "wf-1")
            .where(CounterEventModel.workflow_version == 1)
        )
        assert ev is not None
        assert ev.event_type == "counter.incremented"
        assert ev.body.by == 10

    @pytest.mark.asyncio
    async def test_invoke_routes_through_process_command(self, counter_repo) -> None:
        await counter_repo.create_new(Counter.cmd("increment", by=1), "wf-2")
        result = await counter_repo.invoke("wf-2", "increment", by=4)
        assert not isinstance(result, Rejection)
        stored, events = result
        assert stored.state.count == 5
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_workflow_proxy(self, counter_repo) -> None:
        await counter_repo.create_new(Counter.cmd("increment", by=2), "wf-3")
        proxy = counter_repo.workflow("wf-3")
        result = await proxy.increment(by=3)
        assert not isinstance(result, Rejection)
        stored, _ = result
        assert stored.state.count == 5

    @pytest.mark.asyncio
    async def test_workflow_proxy_unknown_attr(self, counter_repo) -> None:
        proxy = counter_repo.workflow("wf-x")
        with pytest.raises(AttributeError):
            _ = proxy.no_such_method  # noqa: F841

    @pytest.mark.asyncio
    async def test_invoke_unknown_method_raises(self, counter_repo) -> None:
        with pytest.raises(KeyError):
            await counter_repo.invoke("anything", "no_such_method", by=1)

    @pytest.mark.asyncio
    async def test_rejection_via_invoke(self, counter_repo) -> None:
        await counter_repo.create_new(Counter.cmd("increment", by=1), "wf-rej")
        result = await counter_repo.invoke("wf-rej", "increment", by=-99)
        assert isinstance(result, Rejection)

    @pytest.mark.asyncio
    async def test_bulk_invoke_fan_out(self, counter_repo) -> None:
        ids = [f"wf-bulk-{i}" for i in range(5)]
        for i, wf_id in enumerate(ids):
            await counter_repo.create_new(
                Counter.cmd("increment", by=i + 1), wf_id
            )
        result = await counter_repo.bulk_invoke(ids, "increment", by=10)
        assert len(result) == 5
        for i, wf_id in enumerate(ids):
            outcome = result[wf_id]
            assert not isinstance(outcome, Rejection)
            stored, events = outcome
            assert stored.state.count == (i + 1) + 10
            assert len(events) == 1


class TestOopSnapshot:
    """Snapshot creation + replay reconstruct identical state."""

    @pytest.mark.asyncio
    async def test_snapshot_and_replay(self, counter_repo, test_session) -> None:
        # snapshot_interval is 3; do 6 commands so two snapshots fire.
        await counter_repo.create_new(Counter.cmd("increment", by=1), "snap-1")
        for i in range(2, 7):
            await counter_repo.invoke("snap-1", "increment", by=i)

        # Two snapshots should exist (at version 3 and version 6); the upsert
        # collapses to one row keyed on workflow_id with version=6.
        snap = await test_session.scalar(
            select(CounterSnapshotModel).where(
                CounterSnapshotModel.workflow_id == "snap-1"
            )
        )
        assert snap is not None
        assert snap.version == 6

        # Force replay: drop the ephemeral cache and re-hydrate from DB.
        await counter_repo._es.remove_state("snap-1")
        rehydrated = await counter_repo.hydrate_state_("snap-1")
        assert rehydrated is not None
        assert rehydrated.state.count == 1 + 2 + 3 + 4 + 5 + 6
        assert rehydrated.state.history == [1, 2, 3, 4, 5, 6]


class TestOopDelay:
    """The riskiest integration: EvDelay round-trip with class-based commands.

    Schedule a delay whose ``next_cmd`` is a class-based cmd, persist it,
    fire it via the synthesized ``EvDelayComplete``, and verify the
    workflow re-dispatches through the OOP path with the same kwargs.
    """

    @pytest.mark.asyncio
    async def test_evdelay_roundtrip_via_event_log_and_event_to_cmd(
        self, counter_repo, test_session
    ) -> None:
        """Persist a class-based ``EvDelay``, deserialize via the body union,
        synthesize ``EvDelayComplete``, and verify the OOP dispatcher
        re-runs the original cmd with all kwargs preserved.

        This is the riskiest integration: it exercises the auto-built
        command union as a Pydantic discriminator over the persisted
        next_cmd payload."""
        await counter_repo.create_new(Counter.cmd("increment", by=1), "wf-tick")

        # Schedule a delay whose next_cmd is the class-based "tick" command.
        result = await counter_repo.invoke(
            "wf-tick", "schedule_tick", in_seconds=60, then_increment_by=7
        )
        assert not isinstance(result, Rejection)

        # The EvDelay row is persisted in the events table; the body column
        # is typed as the workflow's PydanticType union — fetching it back
        # forces Pydantic to deserialize ``next_cmd`` through the
        # ``method``-discriminated CounterCmdUnion.  This round-trip is the
        # whole point of the test.
        delay_event = await test_session.scalar(
            select(CounterEventModel)
            .where(CounterEventModel.workflow_id == "wf-tick")
            .where(CounterEventModel.event_type == "counter.tick_delay")
        )
        assert delay_event is not None
        next_cmd = delay_event.body.next_cmd
        assert next_cmd.method == "tick"
        assert next_cmd.params.increment_by == 7

        # Simulate what DelayScheduler does when the delay fires: it
        # synthesizes an EvDelayComplete and feeds it to the runner, which
        # calls event_to_cmd → process_command.
        ev_complete = EvDelayComplete[CounterCmdUnion](  # type: ignore[type-arg]
            delay_id=delay_event.body.id,
            at=datetime.datetime.now(datetime.timezone.utc),
            next_cmd=next_cmd,
        )
        cmd = Counter.event_to_cmd(ev_complete)
        assert cmd is not None
        assert cmd.method == "tick"  # type: ignore[union-attr]

        # The cmd from event_to_cmd flows back into process_command — same
        # OOP dispatch path as a fresh repo.invoke().
        outcome = await counter_repo.process_command("wf-tick", cmd)
        assert not isinstance(outcome, Rejection)
        stored, events = outcome
        # tick emits EvTicked + EvIncremented(by=7), so count goes 1 -> 8 and
        # ticks goes 0 -> 1.
        assert stored.state.count == 8
        assert stored.state.ticks == 1
        assert len(events) == 2


class TestOopLifecycle:
    """Cancel / pause / resume / final-event eviction."""

    @pytest.mark.asyncio
    async def test_pause_blocks_then_resume_unblocks(self, counter_repo) -> None:
        await counter_repo.create_new(Counter.cmd("increment", by=1), "wf-life")
        await counter_repo.pause_workflow("wf-life", reason="maintenance")

        rej = await counter_repo.invoke("wf-life", "increment", by=99)
        assert isinstance(rej, Rejection)
        assert "paused" in rej.msg.lower()

        await counter_repo.resume_workflow("wf-life")
        ok = await counter_repo.invoke("wf-life", "increment", by=4)
        assert not isinstance(ok, Rejection)
        stored, _ = ok
        assert stored.state.count == 5

    @pytest.mark.asyncio
    async def test_cancel_blocks_further_commands(self, counter_repo) -> None:
        await counter_repo.create_new(Counter.cmd("increment", by=1), "wf-cx")
        await counter_repo.cancel_workflow("wf-cx", reason="done")
        rej = await counter_repo.invoke("wf-cx", "increment", by=1)
        assert isinstance(rej, Rejection)
        assert "cancelled" in rej.msg.lower()

    @pytest.mark.asyncio
    async def test_final_event_evicts_from_cache(
        self, counter_repo
    ) -> None:
        await counter_repo.create_new(Counter.cmd("increment", by=1), "wf-stop")
        await counter_repo.invoke("wf-stop", "stop", reason="end of test")
        cached = await counter_repo._es.get_state("wf-stop")
        assert cached is None


class TestOopContinueAsNew:
    """``continue_as_new`` resets the event log while preserving state.

    Path: load state -> force snapshot -> truncate events -> insert
    ``EvContinueAsNew`` marker -> optionally process new_cmd.
    """

    @pytest.mark.asyncio
    async def test_continue_as_new_preserves_state_and_resets_log(
        self, counter_repo, test_session
    ) -> None:
        # Build up some history.
        await counter_repo.create_new(Counter.cmd("increment", by=1), "wf-can")
        for n in (2, 3, 4):
            await counter_repo.invoke("wf-can", "increment", by=n)

        # Sanity: 4 events stored, count=10.
        rows = (
            await test_session.execute(
                select(CounterEventModel.workflow_version)
                .where(CounterEventModel.workflow_id == "wf-can")
                .order_by(CounterEventModel.workflow_version)
            )
        ).fetchall()
        assert [r[0] for r in rows] == [1, 2, 3, 4]

        # Continue as new — pass an OOP command for the next run.
        result = await counter_repo.continue_as_new(
            "wf-can",
            new_cmd=Counter.cmd("increment", by=100),
            reason="rotate",
        )
        assert not isinstance(result, Rejection)

        # Old events are gone; only the marker (v1) and the new command's
        # events should remain.  State is preserved across the reset.
        post = (
            await test_session.execute(
                select(
                    CounterEventModel.workflow_version, CounterEventModel.event_type
                )
                .where(CounterEventModel.workflow_id == "wf-can")
                .order_by(CounterEventModel.workflow_version)
            )
        ).fetchall()
        assert post[0][1] == "system_continue_as_new"
        # The new_cmd's event is appended.
        assert any(r[1] == "counter.incremented" for r in post)

        async with counter_repo._session_maker() as s:
            stored = await counter_repo.get_current_state(s, "wf-can")
        assert stored.state.count == 1 + 2 + 3 + 4 + 100


class TestOopAdapter:
    """Adapter delivery via Sub: external event arrives → adapter yields a
    class-based cmd → repo.process_command routes through OOP dispatch."""

    @pytest.mark.asyncio
    async def test_adapter_yields_oop_command_into_counter(
        self, counter_repo
    ) -> None:
        await counter_repo.create_new(Counter.cmd("increment", by=10), "wf-sub")

        # Simulate what the runner does: adapter yields a Counter cmd built
        # via Counter.cmd("observe", ...).  Drive through the @handles ->
        # generated act_on dispatch (not the private method) so the whole
        # chain is exercised: ConsumedEvent -> act_on -> OOP cmd ->
        # process_command.
        from fleuve.stream import ConsumedEvent

        adapter = CounterAdapter()
        ev = EvSourcePublished(by=5)
        consumed: ConsumedEvent = ConsumedEvent(
            event=ev,
            workflow_id="src-1",
            event_no=1,
            global_id=1,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="oop_source",
            event_type=ev.type,
        )

        # @handles must auto-route the event to the right handler.
        assert adapter.to_be_act_on(consumed)

        produced: list[Any] = []
        async for cmd in adapter.act_on(consumed, None):
            produced.append(cmd)
            outcome = await counter_repo.process_command("wf-sub", cmd)
            assert not isinstance(outcome, Rejection)

        assert len(produced) == 1
        assert produced[0].method == "observe"  # type: ignore[union-attr]

        # State reflects the observed delta.
        from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

        async with counter_repo._session_maker() as s:  # type: ignore[attr-defined]
            stored = await counter_repo.get_current_state(s, "wf-sub")
        assert stored.state.count == 15
