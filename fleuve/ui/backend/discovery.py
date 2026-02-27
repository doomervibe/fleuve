"""Utilities for discovering workflow types and schemas from the database."""

from typing import List, Dict, Any
from sqlalchemy import select, distinct, func
from sqlalchemy.ext.asyncio import AsyncSession
from fleuve.postgres import StoredEvent


async def discover_workflow_types(
    session: AsyncSession, event_model: type[StoredEvent]
) -> List[str]:
    """
    Discover all workflow types from the database.

    Args:
        session: Database session
        event_model: The StoredEvent model class

    Returns:
        List of workflow type names
    """
    result = await session.execute(select(distinct(event_model.workflow_type)))
    return [row[0] for row in result.fetchall() if row[0]]


async def get_workflow_type_stats(
    session: AsyncSession, event_model: type[StoredEvent], workflow_type: str
) -> Dict[str, Any]:
    """
    Get statistics for a specific workflow type.

    Args:
        session: Database session
        event_model: The StoredEvent model class
        workflow_type: The workflow type name

    Returns:
        Dictionary with statistics
    """
    # Count workflows
    workflow_count_result = await session.execute(
        select(func.count(distinct(event_model.workflow_id))).where(
            event_model.workflow_type == workflow_type
        )
    )
    workflow_count = workflow_count_result.scalar() or 0

    # Count events
    event_count_result = await session.execute(
        select(func.count(event_model.global_id)).where(
            event_model.workflow_type == workflow_type
        )
    )
    event_count = event_count_result.scalar() or 0

    # Last event time
    last_event_result = await session.execute(
        select(func.max(event_model.at)).where(
            event_model.workflow_type == workflow_type
        )
    )
    last_event_at = last_event_result.scalar()

    return {
        "workflow_type": workflow_type,
        "workflow_count": workflow_count,
        "event_count": event_count,
        "last_event_at": last_event_at,
    }
