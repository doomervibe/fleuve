"""
Utilities for handling scaling operations with partitioned runners.

This module provides tools for:
- Coordinating synchronized scaling using database flags
- Waiting for workers to synchronize to target offset
- Initializing partition offsets after scaling
"""

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.postgres import Offset, ScalingOperation
from fleuve.partitioning import make_reader_name

if TYPE_CHECKING:
    from fleuve.partitioning import PartitionedRunnerConfig

logger = logging.getLogger(__name__)


async def get_max_offset(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    reader_names: list[str],
) -> int:
    """
    Get the maximum offset across multiple readers.

    This is useful when scaling - all workers should synchronize to
    the maximum offset before scaling.

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        reader_names: List of reader names to check

    Returns:
        The maximum offset, or 0 if no offsets exist
    """
    if not reader_names:
        return 0

    async with session_maker() as s:
        result = await s.execute(
            select(offset_model.last_read_event_no)
            .where(offset_model.reader.in_(reader_names))
            .order_by(offset_model.last_read_event_no.desc())
            .limit(1)
        )
        row = result.fetchone()
        return row.last_read_event_no if row else 0


async def get_min_offset(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    reader_names: list[str],
) -> int:
    """
    Get the minimum offset across multiple readers.

    This is useful when scaling up - new partitions should start from
    the minimum offset to ensure no events are missed.

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        reader_names: List of reader names to check

    Returns:
        The minimum offset, or 0 if no offsets exist
    """
    if not reader_names:
        return 0

    async with session_maker() as s:
        result = await s.execute(
            select(offset_model.last_read_event_no)
            .where(offset_model.reader.in_(reader_names))
            .order_by(offset_model.last_read_event_no)
            .limit(1)
        )
        row = result.fetchone()
        return row.last_read_event_no if row else 0


async def migrate_offsets_on_scale_up(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    new_reader_names: list[str],
    existing_reader_names: list[str],
) -> None:
    """
    Migrate offsets when scaling up (adding partitions).

    When scaling up, new partitions should start from the minimum offset
    of existing partitions to ensure no events are missed. New reader
    offsets are initialized to this minimum value if they don't exist.

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        new_reader_names: List of new reader names to initialize
        existing_reader_names: List of existing reader names to check for min offset
    """
    if not new_reader_names:
        return

    min_offset = await get_min_offset(
        session_maker, offset_model, existing_reader_names
    )

    async with session_maker() as s:
        # Check which new readers already have offsets
        result = await s.execute(
            select(offset_model.reader).where(offset_model.reader.in_(new_reader_names))
        )
        existing_new_readers = {row.reader for row in result.fetchall()}

        # Initialize new readers that don't have offsets yet
        readers_to_init = [
            name for name in new_reader_names if name not in existing_new_readers
        ]

        if readers_to_init:
            await s.execute(
                insert(offset_model).values(
                    [
                        {"reader": name, "last_read_event_no": min_offset}
                        for name in readers_to_init
                    ]
                )
            )
            await s.commit()
            logger.info(
                f"Initialized {len(readers_to_init)} new reader offsets to {min_offset}"
            )
        else:
            logger.info("All new readers already have offsets")


async def merge_offsets_on_scale_down(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    removed_reader_names: list[str],
    target_reader_name: str | None = None,
) -> int:
    """
    Merge offsets when scaling down (removing partitions).

    When scaling down, we need to ensure that the remaining partitions
    have seen all events that were processed by the removed partitions.
    This function merges offsets by taking the maximum offset and optionally
    updating a target reader to that offset.

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        removed_reader_names: List of reader names being removed
        target_reader_name: Optional reader name to update with merged offset.
                          If None, offsets are just merged without updating a target.

    Returns:
        The maximum offset from the removed readers (0 if none exist)
    """
    if not removed_reader_names:
        return 0

    async with session_maker() as s:
        # Get maximum offset from removed readers
        result = await s.execute(
            select(offset_model.last_read_event_no)
            .where(offset_model.reader.in_(removed_reader_names))
            .order_by(offset_model.last_read_event_no.desc())
            .limit(1)
        )
        row = result.fetchone()
        max_offset = row.last_read_event_no if row else 0

        if max_offset > 0:
            # Update target reader if provided
            if target_reader_name:
                existing_result = await s.execute(
                    select(offset_model.last_read_event_no).where(
                        offset_model.reader == target_reader_name
                    )
                )
                existing_row = existing_result.fetchone()
                existing_offset = existing_row.last_read_event_no if existing_row else 0

                # Update to maximum offset to ensure no events are missed
                if max_offset > existing_offset:
                    # Try update first
                    update_result = await s.execute(
                        update(offset_model)
                        .where(offset_model.reader == target_reader_name)
                        .values({"last_read_event_no": max_offset})
                    )
                    if update_result.rowcount == 0:
                        # Insert if doesn't exist
                        await s.execute(
                            insert(offset_model).values(
                                {
                                    "reader": target_reader_name,
                                    "last_read_event_no": max_offset,
                                }
                            )
                        )
                    await s.commit()
                    logger.info(
                        f"Updated {target_reader_name} offset to {max_offset} "
                        f"(merged from {len(removed_reader_names)} removed readers)"
                    )

            # Note: We don't delete old reader offsets by default to allow for
            # recovery and auditing. If you want to clean up old reader records,
            # uncomment the following:
            # await s.execute(
            #     delete(offset_model).where(offset_model.reader.in_(removed_reader_names))
            # )
            # await s.commit()

        return max_offset


async def get_all_reader_names(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    workflow_type: str,
    prefix: str | None = None,
) -> list[str]:
    """
    Get all reader names for a workflow type, optionally filtered by prefix.

    This is useful for discovering existing partitions when scaling.

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        workflow_type: The workflow type name
        prefix: Optional prefix to filter reader names (e.g., "{workflow_type}_runner_partition_")

    Returns:
        List of reader names
    """
    async with session_maker() as s:
        query = select(offset_model.reader)
        if prefix:
            query = query.where(offset_model.reader.like(f"{prefix}%"))
        else:
            # Default: find all readers for this workflow type
            workflow_prefix = f"{workflow_type}_runner"
            query = query.where(offset_model.reader.like(f"{workflow_prefix}%"))

        result = await s.execute(query)
        return [row.reader for row in result.fetchall()]


async def create_scaling_operation(
    session_maker: async_sessionmaker[AsyncSession],
    scaling_operation_model: type[ScalingOperation],
    workflow_type: str,
    target_offset: int,
) -> None:
    """
    Create a scaling operation in the database.

    This signals workers to prepare for scaling by stopping at target_offset.

    Args:
        session_maker: Database session maker
        scaling_operation_model: The ScalingOperation model class
        workflow_type: The workflow type name
        target_offset: The offset all workers should reach

    Raises:
        ValueError: If a scaling operation already exists for this workflow type
    """
    async with session_maker() as s:
        # Check if scaling operation already exists
        result = await s.execute(
            select(scaling_operation_model.status)
            .where(scaling_operation_model.workflow_type == workflow_type)
            .where(scaling_operation_model.status.in_(["pending", "synchronizing"]))
            .limit(1)
        )
        existing = result.fetchone()
        if existing:
            raise ValueError(
                f"Scaling operation already in progress for {workflow_type}"
            )

        # Create scaling operation
        await s.execute(
            insert(scaling_operation_model).values(
                {
                    "workflow_type": workflow_type,
                    "target_offset": target_offset,
                    "status": "pending",
                }
            )
        )
        await s.commit()
        logger.info(
            f"Created scaling operation for {workflow_type} with target_offset={target_offset}"
        )


async def update_scaling_operation_status(
    session_maker: async_sessionmaker[AsyncSession],
    scaling_operation_model: type[ScalingOperation],
    workflow_type: str,
    status: str,
) -> None:
    """
    Update the status of a scaling operation.

    Args:
        session_maker: Database session maker
        scaling_operation_model: The ScalingOperation model class
        workflow_type: The workflow type name
        status: New status (pending, synchronizing, completed, failed)
    """
    async with session_maker() as s:
        result = await s.execute(
            update(scaling_operation_model)
            .where(scaling_operation_model.workflow_type == workflow_type)
            .values({"status": status})
        )
        await s.commit()
        if result.rowcount > 0:
            logger.info(
                f"Updated scaling operation status for {workflow_type} to {status}"
            )


async def check_all_workers_at_offset(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    reader_names: list[str],
    target_offset: int,
) -> bool:
    """
    Check if all workers have reached the target offset.

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        reader_names: List of reader names to check
        target_offset: Target offset to check

    Returns:
        True if all workers have offset >= target_offset, False otherwise
    """
    if not reader_names:
        return True

    async with session_maker() as s:
        result = await s.execute(
            select(offset_model.reader, offset_model.last_read_event_no).where(
                offset_model.reader.in_(reader_names)
            )
        )
        rows = result.fetchall()

        if len(rows) < len(reader_names):
            # Some readers don't have offsets yet
            return False

        for row in rows:
            if row.last_read_event_no < target_offset:
                return False

        return True


async def wait_for_workers_to_reach_offset(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    reader_names: list[str],
    target_offset: int,
    timeout: datetime.timedelta = datetime.timedelta(minutes=5),
    check_interval: datetime.timedelta = datetime.timedelta(seconds=2),
) -> bool:
    """
    Wait for all workers to reach the target offset.

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        reader_names: List of reader names to check
        target_offset: Target offset to wait for
        timeout: Maximum time to wait
        check_interval: How often to check worker offsets

    Returns:
        True if all workers reached target_offset, False if timeout
    """
    start_time = datetime.datetime.now(datetime.timezone.utc)
    logger.info(
        f"Waiting for {len(reader_names)} workers to reach offset {target_offset}"
    )

    while True:
        if await check_all_workers_at_offset(
            session_maker, offset_model, reader_names, target_offset
        ):
            logger.info(f"All workers reached target_offset {target_offset}")
            return True

        elapsed = datetime.datetime.now(datetime.timezone.utc) - start_time
        if elapsed >= timeout:
            logger.warning(
                f"Timeout waiting for workers to reach offset {target_offset} "
                f"(timeout={timeout})"
            )
            return False

        await asyncio.sleep(check_interval.total_seconds())


async def clear_scaling_operation(
    session_maker: async_sessionmaker[AsyncSession],
    scaling_operation_model: type[ScalingOperation],
    workflow_type: str,
) -> None:
    """
    Clear a completed or failed scaling operation.

    Args:
        session_maker: Database session maker
        scaling_operation_model: The ScalingOperation model class
        workflow_type: The workflow type name
    """
    async with session_maker() as s:
        await s.execute(
            delete(scaling_operation_model).where(
                scaling_operation_model.workflow_type == workflow_type
            )
        )
        await s.commit()
        logger.info(f"Cleared scaling operation for {workflow_type}")


async def rebalance_partitions(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    old_partition_configs: list["PartitionedRunnerConfig"],
    new_partition_configs: list["PartitionedRunnerConfig"],
) -> None:
    """
    Rebalance partitions when changing the total number of partitions.

    This handles the migration from one partition configuration to another,
    including:
    - Merging offsets from removed partitions
    - Initializing offsets for new partitions

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        old_partition_configs: List of old PartitionedRunnerConfig instances
        new_partition_configs: List of new PartitionedRunnerConfig instances
    """
    old_reader_names = {config.reader_name for config in old_partition_configs}
    new_reader_names = {config.reader_name for config in new_partition_configs}

    removed_readers = list(old_reader_names - new_reader_names)
    added_readers = list(new_reader_names - old_reader_names)
    existing_readers = list(new_reader_names & old_reader_names)

    logger.info(
        f"Rebalancing partitions: {len(removed_readers)} removed, "
        f"{len(added_readers)} added, {len(existing_readers)} unchanged"
    )

    # Handle scale down: merge offsets from removed partitions
    if removed_readers:
        # For now, we don't merge into a specific target - just log
        # In practice, you might want to merge into the nearest partition
        max_offset = await merge_offsets_on_scale_down(
            session_maker, offset_model, removed_readers, target_reader_name=None
        )
        if max_offset > 0:
            logger.warning(
                f"Removed {len(removed_readers)} partitions with max offset {max_offset}. "
                f"Ensure remaining partitions have seen all events up to this offset."
            )

    # Handle scale up: initialize new partitions
    if added_readers:
        await migrate_offsets_on_scale_up(
            session_maker,
            offset_model,
            added_readers,
            existing_readers if existing_readers else removed_readers,
        )


async def initialize_partition_offsets(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    reader_names: list[str],
    target_offset: int,
) -> None:
    """
    Initialize partition offsets to a target offset.

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        reader_names: List of reader names to initialize
        target_offset: Offset to set for all readers
    """
    if not reader_names:
        return

    async with session_maker() as s:
        # Check which readers already have offsets
        result = await s.execute(
            select(offset_model.reader).where(offset_model.reader.in_(reader_names))
        )
        existing_readers = {row.reader for row in result.fetchall()}
        readers_to_init = [
            name for name in reader_names if name not in existing_readers
        ]

        # Initialize readers that don't have offsets yet
        if readers_to_init:
            await s.execute(
                insert(offset_model).values(
                    [
                        {"reader": name, "last_read_event_no": target_offset}
                        for name in readers_to_init
                    ]
                )
            )
            await s.commit()
            logger.info(
                f"Initialized {len(readers_to_init)} reader offsets to {target_offset}"
            )

        # Update existing readers to target_offset (if needed)
        for reader_name in existing_readers:
            result = await s.execute(
                select(offset_model.last_read_event_no).where(
                    offset_model.reader == reader_name
                )
            )
            row = result.fetchone()
            if row and row.last_read_event_no < target_offset:
                await s.execute(
                    update(offset_model)
                    .where(offset_model.reader == reader_name)
                    .values({"last_read_event_no": target_offset})
                )
                await s.commit()
                logger.info(f"Updated {reader_name} offset to {target_offset}")


async def scale_up_partitions(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    scaling_operation_model: type[ScalingOperation],
    workflow_type: str,
    old_partition_configs: list["PartitionedRunnerConfig"],
    new_partition_configs: list["PartitionedRunnerConfig"],
    timeout: datetime.timedelta = datetime.timedelta(minutes=5),
) -> int:
    """
    Scale up partitions using synchronized scaling.

    This function:
    1. Gets max_offset from existing partitions
    2. Creates scaling operation in database
    3. Waits for all workers to reach target_offset
    4. Initializes new partition offsets to target_offset
    5. Clears scaling operation

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        scaling_operation_model: The ScalingOperation model class
        workflow_type: The workflow type name
        old_partition_configs: List of old partition configs
        new_partition_configs: List of new partition configs
        timeout: Timeout for waiting for workers to reach target_offset

    Returns:
        The target_offset that was used for synchronization

    Note:
        Workers should be stopped externally after this function completes.
        New workers should then be started with the new partition configuration.
    """
    old_reader_names = [config.reader_name for config in old_partition_configs]
    new_reader_names = [config.reader_name for config in new_partition_configs]
    added_reader_names = [
        name for name in new_reader_names if name not in old_reader_names
    ]

    if not added_reader_names:
        logger.info("No new partitions to add")
        return 0

    # Get max_offset from existing partitions
    target_offset = await get_max_offset(session_maker, offset_model, old_reader_names)
    logger.info(
        f"Scaling up: {len(old_partition_configs)} -> {len(new_partition_configs)} partitions, "
        f"target_offset={target_offset}"
    )

    try:
        # Create scaling operation
        await create_scaling_operation(
            session_maker, scaling_operation_model, workflow_type, target_offset
        )

        # Update status to synchronizing
        await update_scaling_operation_status(
            session_maker, scaling_operation_model, workflow_type, "synchronizing"
        )

        # Wait for all workers to reach target_offset
        all_reader_names = old_reader_names  # Wait for existing workers
        reached = await wait_for_workers_to_reach_offset(
            session_maker, offset_model, all_reader_names, target_offset, timeout
        )

        if not reached:
            await update_scaling_operation_status(
                session_maker, scaling_operation_model, workflow_type, "failed"
            )
            raise TimeoutError(
                f"Timeout waiting for workers to reach offset {target_offset}"
            )

        # Initialize new partition offsets to target_offset
        await initialize_partition_offsets(
            session_maker, offset_model, added_reader_names, target_offset
        )

        # Update status to completed
        await update_scaling_operation_status(
            session_maker, scaling_operation_model, workflow_type, "completed"
        )

        # Clear scaling operation
        await clear_scaling_operation(
            session_maker, scaling_operation_model, workflow_type
        )

        logger.info(
            f"Scaling up completed. All workers synchronized to offset {target_offset}. "
            f"New partitions initialized. You can now start new workers."
        )

        return target_offset

    except Exception as e:
        # Mark as failed on error
        try:
            await update_scaling_operation_status(
                session_maker, scaling_operation_model, workflow_type, "failed"
            )
        except Exception:
            pass  # Ignore errors during cleanup
        raise


async def scale_down_partitions(
    session_maker: async_sessionmaker[AsyncSession],
    offset_model: type[Offset],
    scaling_operation_model: type[ScalingOperation],
    workflow_type: str,
    old_partition_configs: list["PartitionedRunnerConfig"],
    new_partition_configs: list["PartitionedRunnerConfig"],
    timeout: datetime.timedelta = datetime.timedelta(minutes=5),
) -> int:
    """
    Scale down partitions using synchronized scaling.

    This function:
    1. Gets max_offset from all partitions (existing + to be removed)
    2. Creates scaling operation in database
    3. Waits for all workers to reach target_offset
    4. Initializes remaining partition offsets to target_offset
    5. Clears scaling operation

    Args:
        session_maker: Database session maker
        offset_model: The Offset model class
        scaling_operation_model: The ScalingOperation model class
        workflow_type: The workflow type name
        old_partition_configs: List of old partition configs (including those to be removed)
        new_partition_configs: List of new partition configs (remaining partitions)
        timeout: Timeout for waiting for workers to reach target_offset

    Returns:
        The target_offset that was used for synchronization

    Note:
        Workers should be stopped externally after this function completes.
        Remaining workers should then be started with the new partition configuration.
    """
    old_reader_names = [config.reader_name for config in old_partition_configs]
    new_reader_names = [config.reader_name for config in new_partition_configs]
    removed_reader_names = [
        name for name in old_reader_names if name not in new_reader_names
    ]

    if not removed_reader_names:
        logger.info("No partitions to remove")
        return 0

    # Get max_offset from all partitions (existing + to be removed)
    target_offset = await get_max_offset(session_maker, offset_model, old_reader_names)
    logger.info(
        f"Scaling down: {len(old_partition_configs)} -> {len(new_partition_configs)} partitions, "
        f"target_offset={target_offset}"
    )

    try:
        # Create scaling operation
        await create_scaling_operation(
            session_maker, scaling_operation_model, workflow_type, target_offset
        )

        # Update status to synchronizing
        await update_scaling_operation_status(
            session_maker, scaling_operation_model, workflow_type, "synchronizing"
        )

        # Wait for all workers to reach target_offset
        all_reader_names = (
            old_reader_names  # Wait for all workers (including those to be removed)
        )
        reached = await wait_for_workers_to_reach_offset(
            session_maker, offset_model, all_reader_names, target_offset, timeout
        )

        if not reached:
            await update_scaling_operation_status(
                session_maker, scaling_operation_model, workflow_type, "failed"
            )
            raise TimeoutError(
                f"Timeout waiting for workers to reach offset {target_offset}"
            )

        # Initialize remaining partition offsets to target_offset
        await initialize_partition_offsets(
            session_maker, offset_model, new_reader_names, target_offset
        )

        # Update status to completed
        await update_scaling_operation_status(
            session_maker, scaling_operation_model, workflow_type, "completed"
        )

        # Clear scaling operation
        await clear_scaling_operation(
            session_maker, scaling_operation_model, workflow_type
        )

        logger.info(
            f"Scaling down completed. All workers synchronized to offset {target_offset}. "
            f"Remaining partitions initialized. You can now start remaining workers."
        )

        return target_offset

    except Exception as e:
        # Mark as failed on error
        try:
            await update_scaling_operation_status(
                session_maker, scaling_operation_model, workflow_type, "failed"
            )
        except Exception:
            pass  # Ignore errors during cleanup
        raise
