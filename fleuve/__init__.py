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
    EvActionCancel,
    EvCancelSchedule,
    EvContinueAsNew,
    EvDelay,
    EvDelayComplete,
    EvDirectMessage,
    EvExternalSubscriptionAdded,
    EvExternalSubscriptionRemoved,
    EvScheduleAdded,
    EvScheduleRemoved,
    EvSubscriptionAdded,
    EvSubscriptionRemoved,
    ExternalSub,
    Rejection,
    AlreadyExists,
    Schedule,
    StateBase,
    Sub,
    Workflow,
)

# Repository and storage
from fleuve.repo import (
    AsyncRepo,
    EuphStorageNATS,
    InProcessEuphemeralStorage,
    StoredState,
    TieredEuphemeralStorage,
    WorkflowNotFound,
)

# Runner and side effects
from fleuve.runner import WorkflowsRunner, SideEffects, InflightTracker, TokenBucket

# Configuration
from fleuve.config import (
    WorkflowConfig,
    make_runner_from_config,
    make_partitioned_runner_from_config,
    load_fleuve_toml,
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
    Snapshot,
    StoredEvent,
    Subscription,
    ExternalSubscription,
    Activity,
    DelaySchedule,
    Offset,
    ScalingOperation,
    WorkflowMetadata,
    WorkflowSearchAttributes,
    Base,
    PydanticType,
    EncryptedPydanticType,
)

# Stream
from fleuve.stream import Reader, Readers, ConsumedEvent, Sleeper

# Actions
from fleuve.actions import ActionExecutor, ActionStatus
from fleuve.action_utils import run_with_background_check

# Delay
from fleuve.delay import DelayScheduler

# Tracing
from fleuve.tracing import FleuveTracer

# Metrics
from fleuve.metrics import FleuveMetrics

# Testing helpers
from fleuve.testing import WorkflowTestHarness

# Validation
from fleuve.validation import validate_workflow, discover_and_validate

# Gateway
from fleuve.gateway import FleuveCommandGateway

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

# Truncation
from fleuve.truncation import TruncationService

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
    "Schedule",
    "CheckpointYield",
    "EvActionCancel",
    "EvCancelSchedule",
    "EvExternalSubscriptionAdded",
    "EvExternalSubscriptionRemoved",
    "EvScheduleAdded",
    "EvScheduleRemoved",
    "EvSubscriptionAdded",
    "EvSubscriptionRemoved",
    "EvContinueAsNew",
    "EvDelay",
    "EvDelayComplete",
    "EvDirectMessage",
    "Sub",
    "ExternalSub",
    # Repository
    "AsyncRepo",
    "EuphStorageNATS",
    "InProcessEuphemeralStorage",
    "TieredEuphemeralStorage",
    "StoredState",
    "WorkflowNotFound",
    # Runner
    "WorkflowsRunner",
    "SideEffects",
    "InflightTracker",
    "TokenBucket",
    # Config
    "WorkflowConfig",
    "make_runner_from_config",
    "make_partitioned_runner_from_config",
    "load_fleuve_toml",
    # Partitioning
    "PartitionedRunnerConfig",
    "create_partitioned_configs",
    "make_hash_partition_rule",
    "make_reader_name",
    # PostgreSQL
    "RetryPolicy",
    "Snapshot",
    "StoredEvent",
    "Subscription",
    "ExternalSubscription",
    "Activity",
    "DelaySchedule",
    "Offset",
    "ScalingOperation",
    "WorkflowMetadata",
    "WorkflowSearchAttributes",
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
    "run_with_background_check",
    # Delay
    "DelayScheduler",
    # Tracing
    "FleuveTracer",
    # Metrics
    "FleuveMetrics",
    # Testing
    "WorkflowTestHarness",
    # Validation
    "validate_workflow",
    "discover_and_validate",
    # Gateway
    "FleuveCommandGateway",
    # Scaling
    "rebalance_partitions",
    "scale_up_partitions",
    "scale_down_partitions",
    "get_max_offset",
    "get_min_offset",
    # Setup
    "create_workflow_runner",
    "WorkflowRunnerResources",
    # Truncation
    "TruncationService",
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
