import os
import tomllib
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


def load_fleuve_toml(path: str | None = None) -> dict[str, Any]:
    """Load a ``fleuve.toml`` configuration file.

    Searches (in order):
    1. The explicit ``path`` argument.
    2. ``$FLEUVE_CONFIG`` environment variable.
    3. ``fleuve.toml`` in the current working directory.

    Returns an empty dict if no file is found.

    The TOML file can contain a ``[fleuve]`` section with any of the following
    keys (all optional):

    .. code-block:: toml

        [fleuve]
        database_url = "postgresql+asyncpg://..."
        nats_url = "nats://localhost:4222"
        snapshot_interval = 100
        enable_truncation = true
        truncation_min_retention_days = 7
        truncation_batch_size = 1000
        max_inflight = 4
        max_events_per_second = 500.0
        enable_otel = false
        max_cache_size = 10000

    Environment variables prefixed with ``FLEUVE_`` override TOML values (e.g.
    ``FLEUVE_MAX_INFLIGHT=8``).
    """
    candidates = [
        path,
        os.getenv("FLEUVE_CONFIG"),
        "fleuve.toml",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            with open(candidate, "rb") as fh:
                data = tomllib.load(fh)
            result: dict[str, Any] = data.get("fleuve", {})
            _apply_env_overrides(result)
            return result

    result = {}
    _apply_env_overrides(result)
    return result


def _apply_env_overrides(cfg: dict[str, Any]) -> None:
    """Apply ``FLEUVE_*`` environment variables on top of cfg dict (in-place)."""
    _BOOL_KEYS = {
        "enable_truncation",
        "enable_otel",
        "enable_jetstream",
        "enable_reconciliation",
        "enable_external_messaging",
        "create_tables",
        "trust_cache",
    }
    _INT_KEYS = {
        "snapshot_interval",
        "truncation_batch_size",
        "truncation_min_retention_days",
        "max_inflight",
        "max_cache_size",
        "outbox_batch_size",
    }
    _FLOAT_KEYS = {
        "max_events_per_second",
        "outbox_poll_interval",
    }

    for env_key, env_val in os.environ.items():
        if not env_key.startswith("FLEUVE_"):
            continue
        cfg_key = env_key[len("FLEUVE_"):].lower()
        if cfg_key in _BOOL_KEYS:
            cfg[cfg_key] = env_val.lower() in ("1", "true", "yes")
        elif cfg_key in _INT_KEYS:
            try:
                cfg[cfg_key] = int(env_val)
            except ValueError:
                pass
        elif cfg_key in _FLOAT_KEYS:
            try:
                cfg[cfg_key] = float(env_val)
            except ValueError:
                pass
        else:
            cfg[cfg_key] = env_val


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
    max_events_per_second: float | None = None,
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
        max_events_per_second=max_events_per_second,
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
