"""FleuveApp — multi-workflow registry and shared-infrastructure runner factory.

Eliminates the per-workflow wiring boilerplate that accumulates in
``fleuve_setup.py`` when a project runs several workflow types.  All workflows
share one database engine and one NATS connection; each gets its own
``AsyncRepo`` and ``WorkflowsRunner``.

Example::

    from fleuve.app import FleuveApp

    app = FleuveApp(
        database_url="postgresql+asyncpg://user:pass@localhost/mydb",
        nats_url="nats://localhost:4222",
    )

    app.register(
        name="domain",
        workflow=DomainWorkflow,
        adapter=DomainAdapter(settings),
        state=DomainState,
        db_event_model=DomainEvent,
        db_sub_model=DomainSub,
        db_activity_model=DomainActivity,
        db_delay_schedule_model=DomainDelay,
        db_offset_model=DomainOffset,
    )
    app.register(
        name="vault",
        workflow=VaultWorkflow,
        adapter=VaultAdapter(settings),
        state=VaultState,
        db_event_model=VaultEvent,
        db_sub_model=VaultSub,
        db_activity_model=VaultActivity,
        db_delay_schedule_model=VaultDelay,
        db_offset_model=VaultOffset,
    )

    # Start all runners with shared infra
    async with app.runners() as runners:
        await asyncio.gather(*(r.run() for r in runners.values()))

    # Read-only access (no runner / NATS required)
    async with app.readonly_repos(["domain", "vault"]) as repos:
        state = await repos["domain"].get_current_state(session, workflow_id)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, AsyncIterator, Type

from nats.aio.client import Client as NATS
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fleuve.config import WorkflowConfig, make_runner_from_config
from fleuve.model import Adapter, StateBase, Workflow
from fleuve.postgres import (
    Activity,
    Base,
    DelaySchedule,
    Offset,
    Snapshot,
    StoredEvent,
    Subscription,
)
from fleuve.repo import (
    AsyncRepo,
    EuphStorageNATS,
    InProcessEuphemeralStorage,
    SyncDbHandler,
    TieredEuphemeralStorage,
)
from fleuve.runner import WorkflowsRunner
from fleuve.tracing import FleuveTracer


@dataclass
class WorkflowRegistration:
    """Per-workflow configuration stored in the registry.

    Most fields mirror the parameters of ``create_workflow_runner`` / ``AsyncRepo``.
    """

    name: str
    workflow: Type[Workflow]
    adapter: Adapter
    state: Type[StateBase]
    db_event_model: Type[StoredEvent]
    db_sub_model: Type[Subscription]
    db_activity_model: Type[Activity]
    db_delay_schedule_model: Type[DelaySchedule]
    db_offset_model: Type[Offset]
    # Optional per-workflow overrides
    nats_bucket: str | None = None
    db_snapshot_model: Type[Snapshot] | None = None
    snapshot_interval: int = 0
    db_workflow_metadata_model: Any = None
    db_external_sub_model: Any = None
    sync_db: SyncDbHandler | None = None
    tracer: FleuveTracer | None = None
    enable_otel: bool = False
    enable_jetstream: bool = False
    jetstream_stream_name: str | None = None
    runner_kwargs: dict[str, Any] = field(default_factory=dict)


class FleuveApp:
    """Multi-workflow registry and shared-infrastructure runner factory.

    ``FleuveApp`` holds a registry of workflow configurations and manages the
    lifecycle of the shared database engine and NATS connection so each
    registered workflow doesn't need to wire its own infrastructure.

    The two main context managers are:

    - ``runners(names=None)`` — creates ``WorkflowsRunner`` instances for the
      requested workflows (default: all registered), yields
      ``dict[str, WorkflowsRunner]``.
    - ``readonly_repos(names=None)`` — creates ``AsyncRepo`` instances without
      starting a NATS connection or runner loop, yields
      ``dict[str, AsyncRepo]``.
    """

    def __init__(
        self,
        database_url: str | None = None,
        nats_url: str | None = None,
        create_tables: bool = True,
        engine_echo: bool = False,
        max_cache_size: int = 10_000,
        trust_cache: bool = False,
    ) -> None:
        self._database_url: str = (
            database_url
            or os.getenv(
                "DATABASE_URL",
                "postgresql+asyncpg://postgres:postgres@localhost/fleuve",
            )
            or "postgresql+asyncpg://postgres:postgres@localhost/fleuve"
        )
        self._nats_url: str = (
            nats_url
            or os.getenv("NATS_URL", "nats://localhost:4222")
            or "nats://localhost:4222"
        )
        self._create_tables = create_tables
        self._engine_echo = engine_echo
        self._max_cache_size = max_cache_size
        self._trust_cache = trust_cache
        self._registry: dict[str, WorkflowRegistration] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        workflow: Type[Workflow],
        adapter: Adapter,
        state: Type[StateBase],
        db_event_model: Type[StoredEvent],
        db_sub_model: Type[Subscription],
        db_activity_model: Type[Activity],
        db_delay_schedule_model: Type[DelaySchedule],
        db_offset_model: Type[Offset],
        *,
        nats_bucket: str | None = None,
        db_snapshot_model: Type[Snapshot] | None = None,
        snapshot_interval: int = 0,
        db_workflow_metadata_model: Any = None,
        db_external_sub_model: Any = None,
        sync_db: SyncDbHandler | None = None,
        tracer: FleuveTracer | None = None,
        enable_otel: bool = False,
        enable_jetstream: bool = False,
        jetstream_stream_name: str | None = None,
        **runner_kwargs: Any,
    ) -> None:
        """Register a workflow with the app.

        Args:
            name: Unique name for this workflow within the app.
            workflow: The ``Workflow`` subclass.
            adapter: Constructed adapter instance for side effects.
            state: The workflow state class (``StateBase`` subclass).
            db_event_model: SQLAlchemy model for the events table.
            db_sub_model: SQLAlchemy model for the subscriptions table.
            db_activity_model: SQLAlchemy model for the activities table.
            db_delay_schedule_model: SQLAlchemy model for the delay_schedules table.
            db_offset_model: SQLAlchemy model for the offsets table.
            nats_bucket: Override the NATS KV bucket name (default: ``<workflow_type>_states``).
            db_snapshot_model: Optional SQLAlchemy model for snapshots.
            snapshot_interval: Snapshot every N events; 0 = disabled.
            db_workflow_metadata_model: Optional model for workflow metadata.
            db_external_sub_model: Optional model for external subscriptions.
            sync_db: Optional strongly-consistent DB side-effect handler.
            tracer: Optional ``FleuveTracer`` for OTel spans.
            enable_otel: Auto-create a ``FleuveTracer`` when True and no
                explicit ``tracer`` is given.
            enable_jetstream: Enable NATS JetStream for event streaming.
            jetstream_stream_name: JetStream stream name override.
            **runner_kwargs: Extra kwargs forwarded to ``make_runner_from_config``.
        """
        if name in self._registry:
            raise ValueError(
                f"Workflow '{name}' is already registered in this FleuveApp"
            )
        self._registry[name] = WorkflowRegistration(
            name=name,
            workflow=workflow,
            adapter=adapter,
            state=state,
            db_event_model=db_event_model,
            db_sub_model=db_sub_model,
            db_activity_model=db_activity_model,
            db_delay_schedule_model=db_delay_schedule_model,
            db_offset_model=db_offset_model,
            nats_bucket=nats_bucket,
            db_snapshot_model=db_snapshot_model,
            snapshot_interval=snapshot_interval,
            db_workflow_metadata_model=db_workflow_metadata_model,
            db_external_sub_model=db_external_sub_model,
            sync_db=sync_db,
            tracer=tracer,
            enable_otel=enable_otel,
            enable_jetstream=enable_jetstream,
            jetstream_stream_name=jetstream_stream_name,
            runner_kwargs=runner_kwargs,
        )

    @property
    def registered_names(self) -> list[str]:
        """Names of all registered workflows."""
        return list(self._registry)

    # ------------------------------------------------------------------
    # Context managers
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def runners(
        self, names: list[str] | None = None
    ) -> AsyncIterator[dict[str, WorkflowsRunner]]:
        """Context manager that creates runners for the requested workflows.

        Sets up a single shared database engine and NATS connection, then
        creates one ``WorkflowsRunner`` per workflow.  On exit, all runners
        and the shared infrastructure are torn down in reverse order.

        Args:
            names: Subset of registered workflow names to run.
                   Defaults to all registered workflows.

        Yields:
            ``dict[str, WorkflowsRunner]`` keyed by the registered name.

        Example::

            async with app.runners(["domain", "vault"]) as runners:
                await asyncio.gather(*(r.run() for r in runners.values()))
        """
        selected = self._resolve_names(names)
        engine = create_async_engine(self._database_url, echo=self._engine_echo)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)

        if self._create_tables:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        nc = NATS()
        await nc.connect(self._nats_url)

        try:
            runner_objs: dict[str, WorkflowsRunner] = {}
            ephemeral_stores: list[TieredEuphemeralStorage] = []
            runner_cms: list[Any] = []

            try:
                for name in selected:
                    reg = self._registry[name]
                    es, runner = await self._create_runner(
                        reg, session_maker, nc, engine
                    )
                    ephemeral_stores.append(es)
                    runner_cms.append(runner)
                    runner_objs[name] = runner

                yield runner_objs
            finally:
                for runner in runner_cms:
                    try:
                        await runner.__aexit__(None, None, None)
                    except Exception:
                        pass
                for es in ephemeral_stores:
                    try:
                        await es.__aexit__(None, None, None)
                    except Exception:
                        pass
        finally:
            await nc.close()
            await engine.dispose()

    @asynccontextmanager
    async def readonly_repos(
        self, names: list[str] | None = None
    ) -> AsyncIterator[dict[str, AsyncRepo]]:
        """Context manager that creates read-only repos (no runner / NATS).

        Useful for API servers that only need to read workflow state or issue
        commands without running the event loop.

        Args:
            names: Subset of registered workflow names.
                   Defaults to all registered workflows.

        Yields:
            ``dict[str, AsyncRepo]`` keyed by the registered name.

        Example::

            async with app.readonly_repos(["domain"]) as repos:
                state = await repos["domain"].get_current_state(s, workflow_id)
        """
        selected = self._resolve_names(names)
        engine = create_async_engine(self._database_url, echo=self._engine_echo)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)

        try:
            repo_objs: dict[str, AsyncRepo] = {}
            for name in selected:
                reg = self._registry[name]
                repo_objs[name] = self._create_repo(reg, session_maker)
            yield repo_objs
        finally:
            await engine.dispose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_names(self, names: list[str] | None) -> list[str]:
        if names is None:
            return list(self._registry)
        unknown = [n for n in names if n not in self._registry]
        if unknown:
            raise KeyError(
                f"Unknown workflow name(s): {unknown}. "
                f"Registered: {list(self._registry)}"
            )
        return names

    def _create_repo(
        self,
        reg: WorkflowRegistration,
        session_maker: async_sessionmaker[AsyncSession],
        ephemeral_storage: TieredEuphemeralStorage | None = None,
    ) -> AsyncRepo:
        tracer = reg.tracer
        if tracer is None and reg.enable_otel:
            tracer = FleuveTracer(workflow_type=reg.workflow.name(), enable=True)
        return AsyncRepo(
            session_maker=session_maker,
            es=ephemeral_storage,  # type: ignore[arg-type]
            model=reg.workflow,
            db_event_model=reg.db_event_model,
            db_sub_model=reg.db_sub_model,
            db_workflow_metadata_model=reg.db_workflow_metadata_model,
            db_external_sub_model=reg.db_external_sub_model,
            sync_db=reg.sync_db,
            adapter=reg.adapter,
            db_snapshot_model=reg.db_snapshot_model,
            snapshot_interval=reg.snapshot_interval,
            db_delay_schedule_model=reg.db_delay_schedule_model,
            tracer=tracer,
            trust_cache=self._trust_cache,
        )

    async def _create_runner(
        self,
        reg: WorkflowRegistration,
        session_maker: async_sessionmaker[AsyncSession],
        nc: NATS,
        engine: AsyncEngine,
    ) -> tuple[TieredEuphemeralStorage, WorkflowsRunner]:
        nats_bucket = reg.nats_bucket or f"{reg.workflow.name()}_states"
        l1: InProcessEuphemeralStorage = InProcessEuphemeralStorage(
            max_size=self._max_cache_size
        )
        l2: EuphStorageNATS = EuphStorageNATS(nc, nats_bucket, reg.state)
        es: TieredEuphemeralStorage = TieredEuphemeralStorage(l1=l1, l2=l2)
        await es.__aenter__()

        tracer = reg.tracer
        if tracer is None and reg.enable_otel:
            tracer = FleuveTracer(workflow_type=reg.workflow.name(), enable=True)

        repo: AsyncRepo = AsyncRepo(
            session_maker=session_maker,
            es=es,
            model=reg.workflow,
            db_event_model=reg.db_event_model,
            db_sub_model=reg.db_sub_model,
            db_workflow_metadata_model=reg.db_workflow_metadata_model,
            db_external_sub_model=reg.db_external_sub_model,
            sync_db=reg.sync_db,
            adapter=reg.adapter,
            db_snapshot_model=reg.db_snapshot_model,
            snapshot_interval=reg.snapshot_interval,
            db_delay_schedule_model=reg.db_delay_schedule_model,
            tracer=tracer,
            trust_cache=self._trust_cache,
        )

        config = WorkflowConfig(
            nats_bucket=nats_bucket,
            workflow_type=reg.workflow,
            adapter=reg.adapter,
            db_sub_type=reg.db_sub_model,
            db_event_model=reg.db_event_model,
            db_activity_model=reg.db_activity_model,
            db_delay_schedule_model=reg.db_delay_schedule_model,
            db_offset_model=reg.db_offset_model,
            db_workflow_metadata_model=reg.db_workflow_metadata_model,
            db_external_sub_type=reg.db_external_sub_model,
            db_snapshot_model=reg.db_snapshot_model,
            snapshot_interval=reg.snapshot_interval,
            tracer=tracer,
        )

        nats_for_runner = nc if reg.enable_jetstream else None
        runner = make_runner_from_config(
            config=config,
            repo=repo,
            session_maker=session_maker,
            jetstream_enabled=reg.enable_jetstream,
            jetstream_stream_name=reg.jetstream_stream_name
            or f"{reg.workflow.name()}_stream",
            nats_client=nats_for_runner,
            **reg.runner_kwargs,
        )
        await runner.__aenter__()
        return es, runner
