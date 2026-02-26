from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Type

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.external_messaging import ExternalMessageConsumer
from fleuve.model import Adapter, Workflow
from fleuve.partitioning import PartitionedRunnerConfig
from fleuve.postgres import (
    Activity,
    DelaySchedule,
    Offset,
    ScalingOperation,
    Snapshot,
    StoredEvent,
    Subscription,
)
from fleuve.repo import AsyncRepo, SyncDbHandler
from fleuve.runner import SideEffects, WorkflowsRunner
from fleuve.stream import Readers


@dataclass
class WorkflowConfig:
    nats_bucket: str
    workflow_type: Type[Workflow]
    adapter: Adapter
    db_sub_type: Type[Subscription]
    db_event_model: Type[StoredEvent]
    db_activity_model: Type[Activity]
    db_delay_schedule_model: Type[DelaySchedule]
    db_offset_model: Type[Offset]
    wf_id_rule: Callable[[str], bool] | None = None
    db_scaling_operation_model: Type[ScalingOperation] | None = None
    # External NATS messaging (optional)
    external_messaging_enabled: bool = False
    external_stream_name: str | None = None
    external_message_parser: Any = None  # Callable[[bytes], BaseModel] or Pydantic type
    db_workflow_metadata_model: Type[Any] | None = None
    db_external_sub_type: Type[Any] | None = (
        None  # ExternalSubscription model for topic routing
    )
    # Strongly consistent DB sync: pass to AsyncRepo(sync_db=...) when building repo from config
    sync_db: SyncDbHandler | None = None
    # Snapshotting
    db_snapshot_model: Type[Snapshot] | None = None
    snapshot_interval: int = 0  # 0 = disabled; snapshot every N events per workflow
    # Event truncation (requires snapshotting)
    truncation_enabled: bool = False
    truncation_min_retention: timedelta = field(
        default_factory=lambda: timedelta(days=7)
    )
    truncation_batch_size: int = 1000
    truncation_check_interval: timedelta = field(
        default_factory=lambda: timedelta(hours=1)
    )
    # OpenTelemetry tracing (optional)
    tracer: Any = None  # FleuveTracer instance


def make_runner_from_config(
    config: WorkflowConfig,
    repo: AsyncRepo,
    session_maker: async_sessionmaker[AsyncSession],
    action_executor_kwargs: dict[str, Any] = {},
    delay_scheduler_kwargs: dict[str, Any] = {},
    reader_name: str | None = None,
    # JetStream configuration
    jetstream_enabled: bool = False,
    jetstream_stream_name: str | None = None,
    nats_client: Any = None,
    batch_size: int = 100,
    # External messaging (optional; requires nats_client when enabled)
    external_messaging_enabled: bool = False,
    external_stream_name: str | None = None,
    external_message_parser: Any = None,
    max_inflight: int = 1,
) -> WorkflowsRunner:
    """
    Create a single WorkflowsRunner from a WorkflowConfig.

    Args:
        config: The workflow configuration
        repo: The workflow repository
        session_maker: Database session maker
        action_executor_kwargs: Optional kwargs for ActionExecutor
        delay_scheduler_kwargs: Optional kwargs for DelayScheduler
        reader_name: Optional custom reader name. If None, uses default from runner
        jetstream_enabled: Enable JetStream for event streaming (default: False)
        jetstream_stream_name: JetStream stream name (optional)
        nats_client: NATS client instance (required if jetstream_enabled)
        batch_size: Batch size for readers (default: 100)
        external_messaging_enabled: Enable external NATS message consumer (default: False)
        external_stream_name: JetStream stream name for external messages (default: external_{workflow_type})
        external_message_parser: Callable[[bytes], BaseModel] or Pydantic type to parse payload

    Returns:
        A configured WorkflowsRunner
    """
    external_consumer = None
    if (
        config.external_messaging_enabled or external_messaging_enabled
    ) and nats_client:
        stream_name = (
            external_stream_name
            or config.external_stream_name
            or f"external_{config.workflow_type.name()}"
        )
        parser = external_message_parser or config.external_message_parser
        external_consumer = ExternalMessageConsumer(
            nats_client=nats_client,
            stream_name=stream_name,
            consumer_name=f"{config.workflow_type.name()}_external_consumer",
            workflow_type=config.workflow_type.name(),
            workflow_type_class=config.workflow_type,
            repo=repo,
            session_maker=session_maker,
            db_external_sub_type=config.db_external_sub_type,
            db_event_model=config.db_event_model,
            db_workflow_metadata_model=config.db_workflow_metadata_model,
            parse_payload=parser,
            wf_id_rule=config.wf_id_rule,
        )
    return WorkflowsRunner(
        repo=repo,
        readers=Readers(
            pg_session_maker=session_maker,
            model=config.db_event_model,
            offset_model=config.db_offset_model,
            batch_size=batch_size,
            jetstream_enabled=jetstream_enabled,
            jetstream_stream_name=jetstream_stream_name,
            nats_client=nats_client,
            workflow_type=config.workflow_type.name() if jetstream_enabled else None,
        ),
        workflow_type=config.workflow_type,
        session_maker=session_maker,
        db_sub_type=config.db_sub_type,
        se=SideEffects.make_side_effects(
            repo=repo,
            workflow_type=config.workflow_type,
            adapter=config.adapter,
            session_maker=session_maker,
            db_activity_model=config.db_activity_model,
            db_event_model=config.db_event_model,
            db_delay_schedule_model=config.db_delay_schedule_model,
            action_executor_kwargs={
                **action_executor_kwargs,
                **({"tracer": config.tracer} if config.tracer else {}),
            },
            delay_scheduler_kwargs=delay_scheduler_kwargs,
            runner_name=reader_name,
        ),
        wf_id_rule=config.wf_id_rule,
        name=reader_name,
        db_scaling_operation_model=config.db_scaling_operation_model,
        external_message_consumer=external_consumer,
        max_inflight=max_inflight,
    )


def make_partitioned_runner_from_config(
    config: WorkflowConfig,
    partition_config: PartitionedRunnerConfig,
    repo: AsyncRepo,
    session_maker: async_sessionmaker[AsyncSession],
    action_executor_kwargs: dict[str, Any] = {},
    delay_scheduler_kwargs: dict[str, Any] = {},
) -> WorkflowsRunner:
    """
    Create a WorkflowsRunner for a specific partition.

    Args:
        config: The workflow configuration
        partition_config: The partition configuration
        repo: The workflow repository
        session_maker: Database session maker
        action_executor_kwargs: Optional kwargs for ActionExecutor
        delay_scheduler_kwargs: Optional kwargs for DelayScheduler

    Returns:
        A configured WorkflowsRunner for the specified partition
    """
    if partition_config.workflow_type != config.workflow_type.name():
        raise ValueError(
            f"Partition workflow type {partition_config.workflow_type} "
            f"does not match config workflow type {config.workflow_type.name()}"
        )

    return WorkflowsRunner(
        repo=repo,
        readers=Readers(
            pg_session_maker=session_maker,
            model=config.db_event_model,
            offset_model=config.db_offset_model,
        ),
        workflow_type=config.workflow_type,
        session_maker=session_maker,
        db_sub_type=config.db_sub_type,
        se=SideEffects.make_side_effects(
            repo=repo,
            workflow_type=config.workflow_type,
            adapter=config.adapter,
            session_maker=session_maker,
            db_activity_model=config.db_activity_model,
            db_event_model=config.db_event_model,
            db_delay_schedule_model=config.db_delay_schedule_model,
            action_executor_kwargs=action_executor_kwargs,
            delay_scheduler_kwargs=delay_scheduler_kwargs,
            runner_name=partition_config.reader_name,
        ),
        wf_id_rule=partition_config.wf_id_rule,
        name=partition_config.reader_name,
        db_scaling_operation_model=config.db_scaling_operation_model,
    )
