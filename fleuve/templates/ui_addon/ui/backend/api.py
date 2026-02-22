"""FastAPI application for Fleuve Framework UI."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, distinct, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.postgres import StoredEvent, Activity, DelaySchedule, Subscription

from .models import (
    WorkflowSummary,
    WorkflowDetail,
    EventResponse,
    ActivityResponse,
    DelayResponse,
    StatsResponse,
    WorkflowTypeInfo,
)
from .discovery import discover_workflow_types, get_workflow_type_stats

logger = logging.getLogger(__name__)


class FleuveUIBackend:
    """Backend for Fleuve Framework UI."""

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        event_model: type[StoredEvent],
        activity_model: type[Activity],
        delay_schedule_model: type[DelaySchedule],
        subscription_model: type[Subscription],
        frontend_dist_path: Optional[Path] = None,
    ):
        """
        Initialize the Fleuve UI backend.

        Args:
            session_maker: Database session maker
            event_model: StoredEvent model class
            activity_model: Activity model class
            delay_schedule_model: DelaySchedule model class
            subscription_model: Subscription model class
            frontend_dist_path: Path to frontend dist directory (optional)
        """
        self.session_maker = session_maker
        self.event_model = event_model
        self.activity_model = activity_model
        self.delay_schedule_model = delay_schedule_model
        self.subscription_model = subscription_model
        self.frontend_dist_path = frontend_dist_path

        self.app = FastAPI(title="Fleuve Framework UI", version="1.0.0")
        self._setup_routes()
        self._setup_static_files()

    def _setup_static_files(self):
        """Set up static file serving for React app."""
        if self.frontend_dist_path and self.frontend_dist_path.exists():
            # Mount static assets
            assets_dir = self.frontend_dist_path / "assets"
            if assets_dir.exists():
                self.app.mount(
                    "/assets", StaticFiles(directory=str(assets_dir)), name="assets"
                )
        else:
            # CORS for development
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=["http://localhost:3000", "http://localhost:5173"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

    def _setup_routes(self):
        """Set up API routes."""

        @self.app.get("/health")
        async def health():
            """Health check endpoint."""
            return {"status": "ok"}

        @self.app.get("/")
        async def root():
            """Serve the React app or return API info."""
            if (
                self.frontend_dist_path
                and (self.frontend_dist_path / "index.html").exists()
            ):
                return FileResponse(str(self.frontend_dist_path / "index.html"))
            return {
                "status": "ok",
                "message": "Fleuve Framework UI API",
                "web_app": "not_built",
            }

        @self.app.get("/api/workflow-types", response_model=List[WorkflowTypeInfo])
        async def get_workflow_types():
            """List all workflow types in the system."""
            async with self.session_maker() as s:
                workflow_types = await discover_workflow_types(s, self.event_model)
                stats = []
                for wt in workflow_types:
                    stat = await get_workflow_type_stats(s, self.event_model, wt)
                    stats.append(WorkflowTypeInfo(**stat))
                return stats

        @self.app.get("/api/workflows", response_model=List[WorkflowSummary])
        async def list_workflows(
            workflow_type: Optional[str] = Query(
                None, description="Filter by workflow type"
            ),
            search: Optional[str] = Query(None, description="Search by workflow ID"),
            limit: int = Query(
                100, ge=1, le=1000, description="Maximum number of results"
            ),
            offset: int = Query(0, ge=0, description="Offset for pagination"),
        ):
            """List workflows with optional filtering."""
            async with self.session_maker() as s:
                # Build query for distinct workflow IDs
                query = select(distinct(self.event_model.workflow_id))

                if workflow_type:
                    query = query.where(self.event_model.workflow_type == workflow_type)

                if search:
                    query = query.where(self.event_model.workflow_id.contains(search))

                # Get workflow IDs
                result = await s.execute(query.limit(limit).offset(offset))
                workflow_ids = [row[0] for row in result.fetchall()]

                workflows = []
                for workflow_id in workflow_ids:
                    try:
                        # Get latest event for this workflow
                        event_result = await s.execute(
                            select(self.event_model)
                            .where(self.event_model.workflow_id == workflow_id)
                            .order_by(self.event_model.workflow_version.desc())
                            .limit(1)
                        )
                        latest_event = event_result.scalar_one_or_none()

                        if latest_event:
                            # Get first event for created_at
                            first_event_result = await s.execute(
                                select(self.event_model)
                                .where(self.event_model.workflow_id == workflow_id)
                                .order_by(self.event_model.workflow_version.asc())
                                .limit(1)
                            )
                            first_event = first_event_result.scalar_one_or_none()

                            # Try to get state from body (for display)
                            state = {}
                            if hasattr(latest_event.body, "model_dump"):
                                state = latest_event.body.model_dump()
                            elif isinstance(latest_event.body, dict):
                                state = latest_event.body

                            workflows.append(
                                WorkflowSummary(
                                    workflow_id=workflow_id,
                                    workflow_type=latest_event.workflow_type,
                                    version=latest_event.workflow_version,
                                    state=state,
                                    created_at=(
                                        first_event.at
                                        if first_event
                                        else latest_event.at
                                    ),
                                    updated_at=latest_event.at,
                                    is_completed=False,  # Would need workflow class to determine
                                )
                            )
                    except Exception as e:
                        logger.warning(f"Error getting workflow {workflow_id}: {e}")
                        continue

                return workflows

        @self.app.get("/api/workflows/{workflow_id}", response_model=WorkflowDetail)
        async def get_workflow(workflow_id: str):
            """Get detailed information about a workflow."""
            async with self.session_maker() as s:
                # Get latest event
                event_result = await s.execute(
                    select(self.event_model)
                    .where(self.event_model.workflow_id == workflow_id)
                    .order_by(self.event_model.workflow_version.desc())
                    .limit(1)
                )
                latest_event = event_result.scalar_one_or_none()

                if not latest_event:
                    raise HTTPException(status_code=404, detail="Workflow not found")

                # Get first event
                first_event_result = await s.execute(
                    select(self.event_model)
                    .where(self.event_model.workflow_id == workflow_id)
                    .order_by(self.event_model.workflow_version.asc())
                    .limit(1)
                )
                first_event = first_event_result.scalar_one_or_none()

                # Get state from latest event body
                state = {}
                if hasattr(latest_event.body, "model_dump"):
                    state = latest_event.body.model_dump()
                elif isinstance(latest_event.body, dict):
                    state = latest_event.body

                # Get subscriptions
                sub_result = await s.execute(
                    select(self.subscription_model).where(
                        self.subscription_model.workflow_id == workflow_id
                    )
                )
                subscriptions = []
                for sub in sub_result.fetchall():
                    subscriptions.append(
                        {
                            "workflow_id": sub.subscribed_to_workflow,
                            "event_type": sub.subscribed_to_event_type,
                        }
                    )

                return WorkflowDetail(
                    workflow_id=workflow_id,
                    workflow_type=latest_event.workflow_type,
                    version=latest_event.workflow_version,
                    state=state,
                    created_at=first_event.at if first_event else latest_event.at,
                    updated_at=latest_event.at,
                    is_completed=False,
                    subscriptions=subscriptions,
                )

        @self.app.get(
            "/api/workflows/{workflow_id}/events", response_model=List[EventResponse]
        )
        async def get_workflow_events(workflow_id: str):
            """Get all events for a workflow."""
            async with self.session_maker() as s:
                result = await s.execute(
                    select(self.event_model)
                    .where(self.event_model.workflow_id == workflow_id)
                    .order_by(self.event_model.workflow_version.asc())
                )
                events = []
                for event in result.scalars().all():
                    body = {}
                    if hasattr(event.body, "model_dump"):
                        body = event.body.model_dump()
                    elif isinstance(event.body, dict):
                        body = event.body

                    events.append(
                        EventResponse(
                            global_id=event.global_id,
                            workflow_id=event.workflow_id,
                            workflow_type=event.workflow_type,
                            workflow_version=event.workflow_version,
                            event_type=event.event_type,
                            body=body,
                            at=event.at,
                            metadata=(
                                event.metadata_ if hasattr(event, "metadata_") else {}
                            ),
                        )
                    )

                return events

        @self.app.get(
            "/api/workflows/{workflow_id}/state/{version}",
            response_model=Dict[str, Any],
        )
        async def get_workflow_state_at_version(workflow_id: str, version: int):
            """Get workflow state at a specific version (time travel)."""
            async with self.session_maker() as s:
                # Get all events up to this version
                result = await s.execute(
                    select(self.event_model)
                    .where(
                        and_(
                            self.event_model.workflow_id == workflow_id,
                            self.event_model.workflow_version <= version,
                        )
                    )
                    .order_by(self.event_model.workflow_version.asc())
                )
                events = result.scalars().all()

                if not events:
                    raise HTTPException(
                        status_code=404, detail="No events found for this version"
                    )

                # Return events - state reconstruction would require workflow class
                return {
                    "workflow_id": workflow_id,
                    "version": version,
                    "events": [
                        {
                            "version": e.workflow_version,
                            "type": e.event_type,
                            "body": (
                                e.body.model_dump()
                                if hasattr(e.body, "model_dump")
                                else e.body
                            ),
                            "at": e.at.isoformat(),
                        }
                        for e in events
                    ],
                    "note": "State reconstruction requires workflow-specific code. Showing events instead.",
                }

        @self.app.get("/api/events", response_model=List[EventResponse])
        async def list_events(
            workflow_type: Optional[str] = Query(None),
            workflow_id: Optional[str] = Query(None),
            event_type: Optional[str] = Query(None),
            limit: int = Query(100, ge=1, le=1000),
            offset: int = Query(0, ge=0),
        ):
            """List events across workflows with filtering."""
            async with self.session_maker() as s:
                query = select(self.event_model)

                if workflow_type:
                    query = query.where(self.event_model.workflow_type == workflow_type)
                if workflow_id:
                    query = query.where(self.event_model.workflow_id == workflow_id)
                if event_type:
                    query = query.where(self.event_model.event_type == event_type)

                result = await s.execute(
                    query.order_by(self.event_model.global_id.desc())
                    .limit(limit)
                    .offset(offset)
                )

                events = []
                for event in result.scalars().all():
                    body = {}
                    if hasattr(event.body, "model_dump"):
                        body = event.body.model_dump()
                    elif isinstance(event.body, dict):
                        body = event.body

                    events.append(
                        EventResponse(
                            global_id=event.global_id,
                            workflow_id=event.workflow_id,
                            workflow_type=event.workflow_type,
                            workflow_version=event.workflow_version,
                            event_type=event.event_type,
                            body=body,
                            at=event.at,
                            metadata=(
                                event.metadata_ if hasattr(event, "metadata_") else {}
                            ),
                        )
                    )

                return events

        @self.app.get("/api/events/{event_id}", response_model=EventResponse)
        async def get_event(event_id: int):
            """Get a specific event by global ID."""
            async with self.session_maker() as s:
                result = await s.execute(
                    select(self.event_model).where(
                        self.event_model.global_id == event_id
                    )
                )
                event = result.scalar_one_or_none()

                if not event:
                    raise HTTPException(status_code=404, detail="Event not found")

                body = {}
                if hasattr(event.body, "model_dump"):
                    body = event.body.model_dump()
                elif isinstance(event.body, dict):
                    body = event.body

                return EventResponse(
                    global_id=event.global_id,
                    workflow_id=event.workflow_id,
                    workflow_type=event.workflow_type,
                    workflow_version=event.workflow_version,
                    event_type=event.event_type,
                    body=body,
                    at=event.at,
                    metadata=event.metadata_ if hasattr(event, "metadata_") else {},
                )

        @self.app.get("/api/activities", response_model=List[ActivityResponse])
        async def list_activities(
            workflow_id: Optional[str] = Query(None),
            workflow_type: Optional[str] = Query(None),
            status: Optional[str] = Query(None),
            limit: int = Query(100, ge=1, le=1000),
            offset: int = Query(0, ge=0),
        ):
            """List activities with filtering."""
            async with self.session_maker() as s:
                query = select(self.activity_model)

                if workflow_id:
                    query = query.where(self.activity_model.workflow_id == workflow_id)
                if workflow_type:
                    query = query.where(self.activity_model.workflow_type == workflow_type)
                if status:
                    query = query.where(self.activity_model.status == status)

                result = await s.execute(
                    query.order_by(self.activity_model.started_at.desc())
                    .limit(limit)
                    .offset(offset)
                )

                activities = []
                for activity in result.scalars().all():
                    checkpoint = {}
                    if hasattr(activity, "checkpoint") and activity.checkpoint:
                        checkpoint = (
                            activity.checkpoint
                            if isinstance(activity.checkpoint, dict)
                            else {}
                        )

                    activities.append(
                        ActivityResponse(
                            workflow_id=activity.workflow_id,
                            workflow_type=getattr(activity, "workflow_type", ""),
                            event_number=activity.event_number,
                            status=activity.status,
                            started_at=activity.started_at,
                            finished_at=activity.finished_at,
                            last_attempt_at=activity.last_attempt_at,
                            retry_count=activity.retry_count,
                            max_retries=activity.max_retries,
                            error_message=activity.error_message,
                            error_type=activity.error_type,
                            checkpoint=checkpoint,
                        )
                    )

                return activities

        @self.app.get(
            "/api/workflows/{workflow_id}/activities",
            response_model=List[ActivityResponse],
        )
        async def get_workflow_activities(workflow_id: str):
            """Get activities for a specific workflow."""
            return await list_activities(
                workflow_id=workflow_id, status=None, limit=1000, offset=0
            )

        @self.app.get("/api/delays", response_model=List[DelayResponse])
        async def list_delays(
            workflow_type: Optional[str] = Query(None),
            workflow_id: Optional[str] = Query(None),
            limit: int = Query(100, ge=1, le=1000),
            offset: int = Query(0, ge=0),
        ):
            """List scheduled delays."""
            async with self.session_maker() as s:
                query = select(self.delay_schedule_model)

                if workflow_type:
                    query = query.where(
                        self.delay_schedule_model.workflow_type == workflow_type
                    )
                if workflow_id:
                    query = query.where(
                        self.delay_schedule_model.workflow_id == workflow_id
                    )

                result = await s.execute(
                    query.order_by(self.delay_schedule_model.delay_until.asc())
                    .limit(limit)
                    .offset(offset)
                )

                delays = []
                for delay in result.scalars().all():
                    next_command = {}
                    if delay.next_command:
                        if hasattr(delay.next_command, "model_dump"):
                            next_command = delay.next_command.model_dump()
                        elif isinstance(delay.next_command, dict):
                            next_command = delay.next_command

                    delays.append(
                        DelayResponse(
                            workflow_id=delay.workflow_id,
                            workflow_type=delay.workflow_type,
                            delay_until=delay.delay_until,
                            event_version=delay.event_version,
                            created_at=delay.created_at,
                            next_command=next_command,
                        )
                    )

                return delays

        @self.app.get(
            "/api/workflows/{workflow_id}/delays", response_model=List[DelayResponse]
        )
        async def get_workflow_delays(workflow_id: str):
            """Get delays for a specific workflow."""
            return await list_delays(
                workflow_type=None, workflow_id=workflow_id, limit=1000, offset=0
            )

        @self.app.get("/api/stats", response_model=StatsResponse)
        async def get_stats():
            """Get dashboard statistics."""
            async with self.session_maker() as s:
                # Total workflows
                workflows_result = await s.execute(
                    select(func.count(distinct(self.event_model.workflow_id)))
                )
                total_workflows = workflows_result.scalar() or 0

                # Workflows by type
                workflows_by_type_result = await s.execute(
                    select(
                        self.event_model.workflow_type,
                        func.count(distinct(self.event_model.workflow_id)),
                    ).group_by(self.event_model.workflow_type)
                )
                workflows_by_type = {
                    row[0]: row[1] for row in workflows_by_type_result.fetchall()
                }

                # Total events
                events_result = await s.execute(
                    select(func.count(self.event_model.global_id))
                )
                total_events = events_result.scalar() or 0

                # Events by type
                events_by_type_result = await s.execute(
                    select(
                        self.event_model.event_type,
                        func.count(self.event_model.global_id),
                    ).group_by(self.event_model.event_type)
                )
                events_by_type = {
                    row[0]: row[1] for row in events_by_type_result.fetchall()
                }

                # Total activities
                activities_result = await s.execute(
                    select(func.count(self.activity_model.workflow_id))
                )
                total_activities = activities_result.scalar() or 0

                # Activities by status
                activities_by_status_result = await s.execute(
                    select(
                        self.activity_model.status,
                        func.count(self.activity_model.workflow_id),
                    ).group_by(self.activity_model.status)
                )
                activities_by_status = {
                    row[0]: row[1] for row in activities_by_status_result.fetchall()
                }

                # Pending activities
                pending_result = await s.execute(
                    select(func.count(self.activity_model.workflow_id)).where(
                        self.activity_model.status == "pending"
                    )
                )
                pending_activities = pending_result.scalar() or 0

                # Failed activities
                failed_result = await s.execute(
                    select(func.count(self.activity_model.workflow_id)).where(
                        self.activity_model.status == "failed"
                    )
                )
                failed_activities = failed_result.scalar() or 0

                # Total delays
                delays_result = await s.execute(
                    select(func.count(self.delay_schedule_model.workflow_id))
                )
                total_delays = delays_result.scalar() or 0

                # Active delays (not yet executed)
                now = datetime.now()
                active_delays_result = await s.execute(
                    select(func.count(self.delay_schedule_model.workflow_id)).where(
                        self.delay_schedule_model.delay_until > now
                    )
                )
                active_delays = active_delays_result.scalar() or 0

                # Workflows by state - this is tricky without workflow class
                # We'll use a placeholder for now
                workflows_by_state = {}

                return StatsResponse(
                    total_workflows=total_workflows,
                    workflows_by_type=workflows_by_type,
                    workflows_by_state=workflows_by_state,
                    total_events=total_events,
                    events_by_type=events_by_type,
                    total_activities=total_activities,
                    activities_by_status=activities_by_status,
                    pending_activities=pending_activities,
                    failed_activities=failed_activities,
                    total_delays=total_delays,
                    active_delays=active_delays,
                )

        # Catch-all route for React Router (must be last)
        @self.app.get("/{full_path:path}")
        async def serve_react_app(full_path: str):
            """Serve React app for all non-API routes."""
            if (
                self.frontend_dist_path
                and (self.frontend_dist_path / "index.html").exists()
            ):
                # Don't serve API routes
                if full_path.startswith("api/"):
                    raise HTTPException(status_code=404, detail="Not found")
                if full_path == "health":
                    raise HTTPException(status_code=404, detail="Not found")

                # Check if it's a file request
                file_path = self.frontend_dist_path / full_path
                if file_path.exists() and file_path.is_file():
                    return FileResponse(str(file_path))

                # Otherwise serve index.html for client-side routing
                return FileResponse(str(self.frontend_dist_path / "index.html"))

            raise HTTPException(status_code=404, detail="Web app not built")


def create_app(
    session_maker: async_sessionmaker[AsyncSession],
    event_model: type[StoredEvent],
    activity_model: type[Activity],
    delay_schedule_model: type[DelaySchedule],
    subscription_model: type[Subscription],
    frontend_dist_path: Optional[Path] = None,
) -> FastAPI:
    """
    Create and configure the Fleuve UI FastAPI application.

    Args:
        session_maker: Database session maker
        event_model: StoredEvent model class
        activity_model: Activity model class
        delay_schedule_model: DelaySchedule model class
        subscription_model: Subscription model class
        frontend_dist_path: Path to frontend dist directory (optional)

    Returns:
        Configured FastAPI application
    """
    backend = FleuveUIBackend(
        session_maker=session_maker,
        event_model=event_model,
        activity_model=activity_model,
        delay_schedule_model=delay_schedule_model,
        subscription_model=subscription_model,
        frontend_dist_path=frontend_dist_path,
    )
    return backend.app
