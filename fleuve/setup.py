"""Simplified setup utilities for Fleuve workflows.

This module provides a convenient way to set up a workflow runner with minimal
boilerplate code. It handles:
- Database connection and table creation
- NATS connection
- Ephemeral storage setup
- Repository creation
- Runner configuration

Example:
    async with create_workflow_runner(
        workflow_type=MyWorkflow,
        state_type=MyState,
        adapter=MyAdapter(),
    ) as resources:
        repo = resources.repo
        runner = resources.runner
        # Use repo and runner...
"""
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Type

from nats.aio.client import Client as NATS
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from fleuve.config import WorkflowConfig, make_runner_from_config
from fleuve.model import Adapter, StateBase, Workflow
from fleuve.postgres import (
    Activity,
    Base,
    DelaySchedule,
    Offset,
    StoredEvent,
    Subscription,
)
from fleuve.repo import AsyncRepo, EuphStorageNATS, SyncDbHandler
from fleuve.runner import WorkflowsRunner


@dataclass
class WorkflowRunnerResources:
    """Resources created by create_workflow_runner."""
    repo: AsyncRepo
    runner: WorkflowsRunner
    session_maker: async_sessionmaker[AsyncSession]
    ephemeral_storage: EuphStorageNATS
    engine: AsyncEngine
    nc: NATS
    outbox_publisher: "JetStreamPublisher | None" = None
    reconciliation_service: "ReconciliationService | None" = None


@asynccontextmanager
async def create_workflow_runner(
    workflow_type: Type[Workflow],
    state_type: Type[StateBase],
    adapter: Adapter,
    db_event_model: Type[StoredEvent],
    db_subscription_model: Type[Subscription],
    db_activity_model: Type[Activity],
    db_delay_schedule_model: Type[DelaySchedule],
    db_offset_model: Type[Offset],
    database_url: str | None = None,
    nats_url: str | None = None,
    nats_bucket: str | None = None,
    create_tables: bool = True,
    engine_echo: bool = False,
    db_workflow_metadata_model: Type[Any] | None = None,
    # JetStream configuration
    enable_jetstream: bool = False,
    jetstream_stream_name: str | None = None,
    enable_reconciliation: bool = True,
    outbox_batch_size: int = 100,
    outbox_poll_interval: float = 0.1,
    outbox_enable_lock: bool = True,
    # External NATS messaging (optional)
    enable_external_messaging: bool = False,
    external_stream_name: str | None = None,
    external_message_parser: Any = None,
    db_external_subscription_model: Type[Any] | None = None,
    sync_db: SyncDbHandler | None = None,
    **runner_kwargs: Any,
):
    """Create a workflow runner with all necessary infrastructure.
    
    This is a convenience function that sets up everything needed to run a
    Fleuve workflow with minimal boilerplate.
    
    Args:
        workflow_type: The workflow class
        state_type: The state class
        adapter: The adapter instance for side effects
        db_event_model: SQLAlchemy model for events table
        db_subscription_model: SQLAlchemy model for subscriptions table
        db_activity_model: SQLAlchemy model for activities table
        db_delay_schedule_model: SQLAlchemy model for delay_schedules table
        db_offset_model: SQLAlchemy model for offsets table
        database_url: PostgreSQL connection string (defaults to env var DATABASE_URL)
        nats_url: NATS server URL (defaults to env var NATS_URL)
        nats_bucket: NATS KV bucket name (defaults to workflow name + "_states")
        create_tables: Whether to create database tables (default: True)
        engine_echo: Whether to echo SQL statements (default: False)
        db_workflow_metadata_model: SQLAlchemy model for workflow_metadata table (optional)
        enable_jetstream: Enable NATS JetStream for event streaming (default: False)
        jetstream_stream_name: JetStream stream name (defaults to workflow name + "_stream")
        enable_reconciliation: Enable reconciliation service for consistency monitoring (default: True)
        outbox_batch_size: Batch size for outbox publisher (default: 100)
        outbox_poll_interval: Poll interval for outbox publisher in seconds (default: 0.1)
        outbox_enable_lock: Enable distributed lock to ensure single publisher (default: True)
        enable_external_messaging: Enable external NATS message consumer for workflows (default: False)
        external_stream_name: JetStream stream name for external messages (default: external_{workflow_type})
        external_message_parser: Callable[[bytes], BaseModel] or Pydantic type to parse external message payload
        sync_db: Optional async (session, workflow_id, old_state, new_state, events) -> None; runs in same transaction as event insert for strongly consistent denormalized/auxiliary DB updates
        **runner_kwargs: Additional kwargs to pass to make_runner_from_config
        
    Yields:
        WorkflowRunnerResources: Container with repo, runner, and other resources
        
    Example:
        async with create_workflow_runner(
            workflow_type=MyWorkflow,
            state_type=MyState,
            adapter=MyAdapter(),
            db_event_model=StoredEvent,
            db_subscription_model=Subscription,
            db_activity_model=Activity,
            db_delay_schedule_model=DelaySchedule,
            db_offset_model=Offset,
        ) as resources:
            # Create a workflow
            result = await resources.repo.create_new(
                cmd=MyCommand(),
                workflow_id="my-workflow-1",
            )
            
            # Run the runner
            await resources.runner.run()
    """
    # Get configuration from environment or use defaults
    database_url = database_url or os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/fleuve"
    )
    nats_url = nats_url or os.getenv("NATS_URL", "nats://localhost:4222")
    
    # Default bucket name from workflow
    if nats_bucket is None:
        nats_bucket = f"{workflow_type.name()}_states"
    
    # Create database engine and session maker
    engine = create_async_engine(database_url, echo=engine_echo)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    # Create database tables if requested
    if create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    # Connect to NATS
    nc = NATS()
    await nc.connect(nats_url)
    
    try:
        # Create ephemeral storage for workflow state
        ephemeral_storage = EuphStorageNATS(nc, nats_bucket, state_type)
        await ephemeral_storage.__aenter__()
        
        try:
            # Create repository
            repo = AsyncRepo(
                session_maker=session_maker,
                es=ephemeral_storage,
                model=workflow_type,
                db_event_model=db_event_model,
                db_sub_model=db_subscription_model,
                db_workflow_metadata_model=db_workflow_metadata_model,
                db_external_sub_model=db_external_subscription_model,
                sync_db=sync_db,
            )
            
            # Create OutboxPublisher if JetStream enabled
            outbox_publisher = None
            reconciliation_service = None
            
            if enable_jetstream:
                from fleuve.jetstream import JetStreamPublisher
                from fleuve.reconciliation import ReconciliationService
                
                stream_name = jetstream_stream_name or f"{workflow_type.name()}_stream"
                
                outbox_publisher = JetStreamPublisher(
                    nats_client=nc,
                    session_maker=session_maker,
                    event_model=db_event_model,
                    stream_name=stream_name,
                    workflow_type=workflow_type.name(),
                    batch_size=outbox_batch_size,
                    poll_interval=outbox_poll_interval,
                    enable_lock=outbox_enable_lock,
                )
                await outbox_publisher.__aenter__()
                await outbox_publisher.start()
                
                if enable_reconciliation:
                    reconciliation_service = ReconciliationService(
                        session_maker=session_maker,
                        event_model=db_event_model,
                        workflow_type=workflow_type.name(),
                    )
                    await reconciliation_service.start()
            
            try:
                # Create workflow configuration
                config = WorkflowConfig(
                    nats_bucket=nats_bucket,
                    workflow_type=workflow_type,
                    adapter=adapter,
                    db_sub_type=db_subscription_model,
                    db_event_model=db_event_model,
                    db_activity_model=db_activity_model,
                    db_delay_schedule_model=db_delay_schedule_model,
                    db_offset_model=db_offset_model,
                    db_workflow_metadata_model=db_workflow_metadata_model,
                    db_external_sub_type=db_external_subscription_model,
                    external_messaging_enabled=enable_external_messaging,
                    external_stream_name=external_stream_name,
                    external_message_parser=external_message_parser,
                )
                nats_for_runner = nc if (enable_jetstream or enable_external_messaging) else None
                # Create runner with JetStream and/or external messaging configuration
                runner = make_runner_from_config(
                    config=config,
                    repo=repo,
                    session_maker=session_maker,
                    jetstream_enabled=enable_jetstream,
                    jetstream_stream_name=jetstream_stream_name or f"{workflow_type.name()}_stream",
                    nats_client=nats_for_runner,
                    batch_size=outbox_batch_size,
                    external_messaging_enabled=enable_external_messaging,
                    external_stream_name=external_stream_name,
                    external_message_parser=external_message_parser,
                    **runner_kwargs,
                )
                
                # Yield resources in async context manager
                async with runner:
                    yield WorkflowRunnerResources(
                        repo=repo,
                        runner=runner,
                        session_maker=session_maker,
                        ephemeral_storage=ephemeral_storage,
                        engine=engine,
                        nc=nc,
                        outbox_publisher=outbox_publisher,
                        reconciliation_service=reconciliation_service,
                    )
            finally:
                # Clean up JetStream components
                if reconciliation_service:
                    await reconciliation_service.stop()
                if outbox_publisher:
                    await outbox_publisher.__aexit__(None, None, None)
        finally:
            # Clean up ephemeral storage
            await ephemeral_storage.__aexit__(None, None, None)
    finally:
        # Clean up NATS and engine
        await nc.close()
        await engine.dispose()
