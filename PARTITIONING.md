# Parallelization and Partitioning Guide

This guide explains how to parallelize workflow runners using hash-based partitioning and how to handle scaling operations.

## Overview

The framework supports parallelization by running multiple runner processes, **each running ONE partition**. Each partition processes a subset of workflow IDs based on hash-based partitioning. This allows you to:

- **Scale horizontally**: Add more processes/containers to increase throughput
- **Partition workloads**: Each partition processes approximately 1/N of all workflow IDs
- **Maintain consistency**: Same workflow ID always goes to the same partition (when partition count is constant)

**Important**: Each process should run **one partition only**. Run multiple processes (one per partition) to achieve parallelization across processes, machines, or containers.

## Quick Start

### Running a Single Partition

Each process runs ONE partition. Configure it using environment variables:

```python
import os
from fleuve.config import WorkflowConfig, make_partitioned_runner_from_config
from fleuve.partitioning import PartitionedRunnerConfig

# Configure partition (usually from environment variables)
PARTITION_INDEX = int(os.getenv("PARTITION_INDEX", "0"))
TOTAL_PARTITIONS = int(os.getenv("TOTAL_PARTITIONS", "3"))

# Create workflow configuration
config = WorkflowConfig(
    workflow_type=OrderWorkflow,
    adapter=OrderAdapter(...),
    # ... other config ...
)

# Create partition configuration
partition_config = PartitionedRunnerConfig(
    partition_index=PARTITION_INDEX,
    total_partitions=TOTAL_PARTITIONS,
    workflow_type=config.workflow_type.name(),
)

# Create runner for this partition
runner = make_partitioned_runner_from_config(
    config=config,
    partition_config=partition_config,
    repo=repo,
    session_maker=session_maker,
)

# Run this partition
async with ephemeral_storage, runner:
    await runner.run()
```

### Running Multiple Partitions

To run 3 partitions, start 3 separate processes (one per partition):

**Process 1:**
```bash
PARTITION_INDEX=0 TOTAL_PARTITIONS=3 python -m examples.order_processing.partitioned_runner_setup
```

**Process 2:**
```bash
PARTITION_INDEX=1 TOTAL_PARTITIONS=3 python -m examples.order_processing.partitioned_runner_setup
```

**Process 3:**
```bash
PARTITION_INDEX=2 TOTAL_PARTITIONS=3 python -m examples.order_processing.partitioned_runner_setup
```

Or use the helper script:
```bash
# Using shell script
./examples/order_processing/start_partitions.sh

# Or using Python script
python examples/order_processing/start_partitions.py --total-partitions 3
```

Each partition will process approximately 1/3 of all workflow IDs.

## How Partitioning Works

### Hash-Based Partitioning

Workflow IDs are partitioned using MD5 hash:

```python
from fleuve.partitioning import make_hash_partition_rule

# Create a rule for partition 0 of 3
rule = make_hash_partition_rule(partition_index=0, total_partitions=3)

# Check if a workflow ID belongs to this partition
rule("workflow-123")  # True or False
```

- Each workflow ID is hashed (MD5)
- Hash value modulo `total_partitions` determines the partition
- Same workflow ID always maps to the same partition (when `total_partitions` is constant)

### Partition Configurations

```python
from fleuve.partitioning import PartitionedRunnerConfig, create_partitioned_configs

# Create configurations for 3 partitions
configs = create_partitioned_configs(
    total_partitions=3,
    workflow_type="OrderWorkflow",
)

# Each config contains:
# - partition_index: 0, 1, or 2
# - reader_name: Unique name for this partition
# - wf_id_rule: Function to filter workflow IDs for this partition
```

## Scaling Operations

### Scaling Up (Adding Partitions)

When adding partitions (e.g., 3 → 5):

1. **Stop all runners gracefully**
2. **Initialize new partition offsets**:

```python
from fleuve.scaling import migrate_offsets_on_scale_up
from fleuve.partitioning import create_partitioned_configs

old_configs = create_partitioned_configs(3, "OrderWorkflow")
new_configs = create_partitioned_configs(5, "OrderWorkflow")

old_reader_names = [c.reader_name for c in old_configs]
new_reader_names = [c.reader_name for c in new_configs]
added_readers = [n for n in new_reader_names if n not in old_reader_names]

await migrate_offsets_on_scale_up(
    session_maker=session_maker,
    offset_model=OrderOffsetModel,
    new_reader_names=added_readers,
    existing_reader_names=old_reader_names,
)
```

3. **Start runners with new configuration**

New partitions start from the minimum offset of existing partitions to ensure no events are missed.

### Scaling Down (Removing Partitions)

When removing partitions (e.g., 5 → 3):

1. **Stop all runners gracefully**
2. **Merge offsets** (optional):

```python
from fleuve.scaling import merge_offsets_on_scale_down

old_configs = create_partitioned_configs(5, "OrderWorkflow")
new_configs = create_partitioned_configs(3, "OrderWorkflow")

old_reader_names = [c.reader_name for c in old_configs]
new_reader_names = [c.reader_name for c in new_configs]
removed_readers = [n for n in old_reader_names if n not in new_reader_names]

max_offset = await merge_offsets_on_scale_down(
    session_maker=session_maker,
    offset_model=OrderOffsetModel,
    removed_reader_names=removed_readers,
)
```

3. **Start runners with new configuration**

### Automatic Rebalancing

Use `rebalance_partitions` to handle both scaling up and down:

```python
from fleuve.scaling import rebalance_partitions

await rebalance_partitions(
    session_maker=session_maker,
    offset_model=OrderOffsetModel,
    old_partition_configs=old_configs,
    new_partition_configs=new_configs,
)
```

## Stream Offset Considerations

### How Offsets Work

- Each reader has its own offset tracked in the `Offset` table
- Offset represents the last `global_id` that the reader has processed
- All readers read from the same global event stream sequentially

### Potential Issues

1. **Duplicate Processing**: When scaling up, new partitions may process events that were already processed. This is safe because:
   - Workflow processing is idempotent
   - Actions are idempotent (checked by ActionExecutor)
   - Command processing is version-based

2. **Missed Events**: When scaling down, workflows are reassigned. However, all readers read from the same stream and have processed events up to at least the max offset, so no events should be missed.

3. **Event Ordering**: Events for the same workflow are always processed in order within a partition. When workflows are reassigned, the receiving partition processes events in order starting from the reassignment point.

### Best Practices

1. **Graceful Shutdown**: Always stop runners gracefully before scaling
2. **Monitor Offsets**: Check offsets before and after scaling
3. **Test Scaling**: Test in development first
4. **Idempotency**: Ensure all workflows and actions are idempotent
5. **Gradual Scaling**: Consider scaling gradually (3 → 4 → 5) rather than large jumps

## Examples

See:
- `examples/order_processing/partitioned_runner_setup.py` - Basic partitioned runner setup
- `examples/order_processing/scale_runners.py` - Scaling script
- `examples/order_processing/SCALING.md` - Detailed scaling guide

## API Reference

### `les.partitioning`

- `make_hash_partition_rule(partition_index, total_partitions)` - Create hash-based partition rule
- `make_reader_name(workflow_type, partition_index, total_partitions)` - Generate reader name
- `PartitionedRunnerConfig` - Configuration for a single partition
- `create_partitioned_configs(total_partitions, workflow_type)` - Create all partition configs

### `les.scaling`

- `get_min_offset(session_maker, offset_model, reader_names)` - Get minimum offset
- `migrate_offsets_on_scale_up(...)` - Initialize new partitions
- `merge_offsets_on_scale_down(...)` - Merge offsets from removed partitions
- `rebalance_partitions(...)` - Handle both scaling up and down

### Orchestrating Multiple Processes

To run multiple partitions, you can:

1. **Use the helper scripts**:
   - `examples/order_processing/start_partitions.sh` - Bash script to start all partitions
   - `examples/order_processing/start_partitions.py` - Python script to start all partitions

2. **Use process managers** (Docker, Kubernetes, systemd, etc.):
   - Start multiple containers/pods, each with a different `PARTITION_INDEX`
   - Use the same `TOTAL_PARTITIONS` value across all instances

3. **Manual process management**:
   - Start each partition in a separate process
   - Each process should have `PARTITION_INDEX` set to a unique value (0 to TOTAL_PARTITIONS-1)

### `les.config`

- `make_partitioned_runner_from_config(...)` - Create runner for a single partition
