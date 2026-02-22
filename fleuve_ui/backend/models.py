"""Pydantic models for Fleuve UI API responses."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class WorkflowSummary(BaseModel):
    """Summary of a workflow for list views."""

    workflow_id: str
    workflow_type: str
    version: int
    state: Dict[str, Any]  # Generic state as JSON
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_completed: bool = False
    runner_id: Optional[str] = None  # Runner that last processed this workflow


class WorkflowDetail(BaseModel):
    """Detailed workflow information."""

    workflow_id: str
    workflow_type: str
    version: int
    state: Dict[str, Any]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_completed: bool = False
    subscriptions: List[Dict[str, str]] = []


class EventResponse(BaseModel):
    """Event information."""

    global_id: int
    workflow_id: str
    workflow_type: str
    workflow_version: int
    event_type: str
    body: Dict[str, Any]
    at: datetime
    metadata: Dict[str, Any] = {}


class ActivityResponse(BaseModel):
    """Activity (action) information."""

    workflow_id: str
    event_number: int
    status: str  # pending, running, completed, failed, retrying
    started_at: datetime
    finished_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    retry_count: int
    max_retries: int
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    checkpoint: Dict[str, Any] = {}
    runner_id: Optional[str] = None  # Runner/reader that executed this activity


class DelayResponse(BaseModel):
    """Delay schedule information."""

    workflow_id: str
    workflow_type: str
    delay_until: datetime
    event_version: int
    created_at: datetime
    next_command: Dict[str, Any]


class StatsResponse(BaseModel):
    """Dashboard statistics."""

    total_workflows: int
    workflows_by_type: Dict[str, int]
    workflows_by_state: Dict[str, int]
    total_events: int
    events_by_type: Dict[str, int]
    total_activities: int
    activities_by_status: Dict[str, int]
    pending_activities: int
    failed_activities: int
    total_delays: int
    active_delays: int


class WorkflowTypeInfo(BaseModel):
    """Information about a workflow type."""

    workflow_type: str
    workflow_count: int
    event_count: int
    last_event_at: Optional[datetime] = None


class WorkflowsListResponse(BaseModel):
    """Paginated workflows list."""

    workflows: List[WorkflowSummary]
    total: int


class EventsListResponse(BaseModel):
    """Paginated events list with filter options."""

    events: List[EventResponse]
    total: int
    event_types: List[str] = []
    tags: List[str] = []


class ActivitiesListResponse(BaseModel):
    """Paginated activities list."""

    activities: List[ActivityResponse]
    total: int


class DelaysListResponse(BaseModel):
    """Paginated delays list."""

    delays: List[DelayResponse]
    total: int
