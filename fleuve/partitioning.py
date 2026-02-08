"""
Utilities for partitioning workflow runners across multiple instances.

This module provides tools for:
- Hash-based partitioning of workflow IDs
- Creating partitioned runner configurations
- Managing offsets during scaling operations
"""

import hashlib
import logging
from typing import Callable

logger = logging.getLogger(__name__)


def make_hash_partition_rule(
    partition_index: int, total_partitions: int
) -> Callable[[str], bool]:
    """
    Create a partition rule function that assigns workflow IDs to a specific partition
    based on hash remainder.

    Args:
        partition_index: The partition index (0-based, e.g., 0, 1, 2 for 3 partitions)
        total_partitions: Total number of partitions

    Returns:
        A function that returns True if a workflow_id belongs to this partition

    Example:
        >>> rule = make_hash_partition_rule(0, 3)  # First of 3 partitions
        >>> rule("workflow-123")  # True if hash("workflow-123") % 3 == 0
    """
    if partition_index < 0 or partition_index >= total_partitions:
        raise ValueError(
            f"partition_index must be in [0, {total_partitions}), got {partition_index}"
        )
    if total_partitions <= 0:
        raise ValueError(f"total_partitions must be > 0, got {total_partitions}")

    def partition_rule(wf_id: str) -> bool:
        # Use MD5 hash for consistent partitioning
        # MD5 is sufficient for this use case (not cryptographic)
        hash_value = int(hashlib.md5(wf_id.encode()).hexdigest(), 16)
        assigned_partition = hash_value % total_partitions
        return assigned_partition == partition_index

    return partition_rule


def make_reader_name(
    workflow_type: str, partition_index: int, total_partitions: int
) -> str:
    """
    Create a consistent reader name for a partitioned runner.

    Args:
        workflow_type: The workflow type name
        partition_index: The partition index (0-based)
        total_partitions: Total number of partitions

    Returns:
        A reader name in the format: {workflow_type}_runner_partition_{partition_index}_of_{total_partitions}
    """
    return f"{workflow_type}_runner_partition_{partition_index}_of_{total_partitions}"


class PartitionedRunnerConfig:
    """
    Configuration for a single partitioned runner instance.

    This class encapsulates the configuration needed to run one partition
    of a workflow runner.
    """

    def __init__(
        self,
        partition_index: int,
        total_partitions: int,
        workflow_type: str,
        reader_name: str | None = None,
        wf_id_rule: Callable[[str], bool] | None = None,
    ):
        """
        Initialize a partitioned runner configuration.

        Args:
            partition_index: The partition index (0-based)
            total_partitions: Total number of partitions
            workflow_type: The workflow type name
            reader_name: Optional custom reader name. If None, will be auto-generated
            wf_id_rule: Optional custom partition rule. If None, will use hash-based partitioning
        """
        if partition_index < 0 or partition_index >= total_partitions:
            raise ValueError(
                f"partition_index must be in [0, {total_partitions}), got {partition_index}"
            )
        if total_partitions <= 0:
            raise ValueError(f"total_partitions must be > 0, got {total_partitions}")

        self.partition_index = partition_index
        self.total_partitions = total_partitions
        self.workflow_type = workflow_type
        self.reader_name = reader_name or make_reader_name(
            workflow_type, partition_index, total_partitions
        )
        self.wf_id_rule = wf_id_rule or make_hash_partition_rule(
            partition_index, total_partitions
        )

    def __repr__(self) -> str:
        return (
            f"PartitionedRunnerConfig("
            f"partition_index={self.partition_index}, "
            f"total_partitions={self.total_partitions}, "
            f"reader_name={self.reader_name!r}"
            f")"
        )


def create_partitioned_configs(
    total_partitions: int,
    workflow_type: str,
) -> list[PartitionedRunnerConfig]:
    """
    Create configurations for all partitions of a workflow runner.

    Args:
        total_partitions: Total number of partitions to create
        workflow_type: The workflow type name

    Returns:
        A list of PartitionedRunnerConfig, one for each partition

    Example:
        >>> configs = create_partitioned_configs(3, "OrderWorkflow")
        >>> len(configs)  # 3
        >>> configs[0].partition_index  # 0
        >>> configs[1].partition_index  # 1
        >>> configs[2].partition_index  # 2
    """
    if total_partitions <= 0:
        raise ValueError(f"total_partitions must be > 0, got {total_partitions}")

    return [
        PartitionedRunnerConfig(
            partition_index=i,
            total_partitions=total_partitions,
            workflow_type=workflow_type,
        )
        for i in range(total_partitions)
    ]
