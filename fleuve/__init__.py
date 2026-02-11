"""
Fleuve - Workflow Framework for Python

A type-safe, production-ready workflow framework that helps you build
reliable, scalable event-driven applications with durable workflow execution,
automatic state management, side effects, and horizontal scaling.
"""

__version__ = "0.1.0"

# Core workflow abstractions
from fleuve.model import (
    ActionContext,
    ActionTimeout,
    Adapter,
    CheckpointYield,
    EventBase,
    EvDelay,
    EvDelayComplete,
    EvDirectMessage,
    ExternalSub,
    Rejection,
    AlreadyExists,
    StateBase,
    Sub,
    Workflow,
)

# Repository and storage
from fleuve.repo import AsyncRepo, EuphStorageNATS, StoredState, WorkflowNotFound

# Runner and side effects
from fleuve.runner import WorkflowsRunner, SideEffects

# Configuration
from fleuve.config import (
    WorkflowConfig,
    make_runner_from_config,
    make_partitioned_runner_from_config,
)

# Partitioning
from fleuve.partitioning import (
    PartitionedRunnerConfig,
    create_partitioned_configs,
    make_hash_partition_rule,
    make_reader_name,
)

# PostgreSQL models
from fleuve.postgres import (
    RetryPolicy,
    StoredEvent,
    Subscription,
    ExternalSubscription,
    Activity,
    DelaySchedule,
    Offset,
    ScalingOperation,
    Base,
    PydanticType,
    EncryptedPydanticType,
)

# Stream
from fleuve.stream import Reader, Readers, ConsumedEvent, Sleeper

# Actions
from fleuve.actions import ActionExecutor, ActionStatus

# Delay
from fleuve.delay import DelayScheduler

# Scaling
from fleuve.scaling import (
    rebalance_partitions,
    scale_up_partitions,
    scale_down_partitions,
    get_max_offset,
    get_min_offset,
)

# Simplified setup
from fleuve.setup import create_workflow_runner, WorkflowRunnerResources

# External NATS messaging
from fleuve.external_messaging import (
    parse_subject,
    resolve_workflow_ids,
    ExternalMessageConsumer,
    EXTERNAL_SUBJECT_PREFIX,
    ROUTING_ALL,
    ROUTING_TAG,
    ROUTING_ID,
    ROUTING_TOPIC,
)

__all__ = [
    # Version
    "__version__",
    # Core
    "ActionContext",
    "ActionTimeout",
    "Adapter",
    "EventBase",
    "StateBase",
    "Workflow",
    "Rejection",
    "AlreadyExists",
    "CheckpointYield",
    "EvDelay",
    "EvDelayComplete",
    "EvDirectMessage",
    "Sub",
    "ExternalSub",
    # Repository
    "AsyncRepo",
    "EuphStorageNATS",
    "StoredState",
    "WorkflowNotFound",
    # Runner
    "WorkflowsRunner",
    "SideEffects",
    # Config
    "WorkflowConfig",
    "make_runner_from_config",
    "make_partitioned_runner_from_config",
    # Partitioning
    "PartitionedRunnerConfig",
    "create_partitioned_configs",
    "make_hash_partition_rule",
    "make_reader_name",
    # PostgreSQL
    "RetryPolicy",
    "StoredEvent",
    "Subscription",
    "ExternalSubscription",
    "Activity",
    "DelaySchedule",
    "Offset",
    "ScalingOperation",
    "Base",
    "PydanticType",
    "EncryptedPydanticType",
    # Stream
    "Reader",
    "Readers",
    "ConsumedEvent",
    "Sleeper",
    # Actions
    "ActionExecutor",
    "ActionStatus",
    # Delay
    "DelayScheduler",
    # Scaling
    "rebalance_partitions",
    "scale_up_partitions",
    "scale_down_partitions",
    "get_max_offset",
    "get_min_offset",
    # Setup
    "create_workflow_runner",
    "WorkflowRunnerResources",
    # External messaging
    "parse_subject",
    "resolve_workflow_ids",
    "ExternalMessageConsumer",
    "EXTERNAL_SUBJECT_PREFIX",
    "ROUTING_ALL",
    "ROUTING_TAG",
    "ROUTING_ID",
    "ROUTING_TOPIC",
]
