"""HTTP Command Gateway for Fleuve workflows.

Exposes workflow commands via REST API for non-Python clients.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fleuve.repo import AsyncRepo, Rejection


class FleuveCommandGateway:
    """FastAPI router for ingesting workflow commands via HTTP.

    Command parsers map (command_type, payload) -> Command for each workflow type.
    """

    def __init__(
        self,
        repos: dict[str, AsyncRepo],
        command_parsers: dict[str, Callable[[str, dict], BaseModel]],
        action_executor: Any = None,
    ):
        """
        Args:
            repos: workflow_type_name -> AsyncRepo
            command_parsers: workflow_type_name -> (cmd_type, payload) -> Command
            action_executor: Optional ActionExecutor for retry endpoint
        """
        self.router = APIRouter(prefix="/commands", tags=["commands"])
        self._repos = repos
        self._parsers = command_parsers
        self._action_executor = action_executor
        self._setup_routes()

    def _setup_routes(self):
        @self.router.post("/{workflow_type}/{workflow_id}")
        async def process_command(
            workflow_type: str,
            workflow_id: str,
            body: dict,
        ):
            """Process a command for an existing workflow."""
            repo = self._repos.get(workflow_type)
            if not repo:
                raise HTTPException(
                    404, detail=f"Unknown workflow type: {workflow_type}"
                )

            parser = self._parsers.get(workflow_type)
            if not parser:
                raise HTTPException(
                    501,
                    detail=f"No command parser for workflow type: {workflow_type}",
                )

            cmd_type = body.get("command_type", "")
            payload = body.get("payload", {})
            try:
                cmd = parser(cmd_type, payload)
            except (ValueError, TypeError) as e:
                raise HTTPException(400, detail=str(e))

            result = await repo.process_command(workflow_id, cmd)
            if isinstance(result, Rejection):
                raise HTTPException(400, detail=result.msg)
            stored, events = result
            return {
                "status": "ok",
                "workflow_id": stored.id,
                "version": stored.version,
                "events_count": len(events),
            }

        @self.router.post("/{workflow_type}")
        async def create_workflow(workflow_type: str, body: dict):
            """Create a new workflow."""
            repo = self._repos.get(workflow_type)
            if not repo:
                raise HTTPException(
                    404, detail=f"Unknown workflow type: {workflow_type}"
                )

            parser = self._parsers.get(workflow_type)
            if not parser:
                raise HTTPException(
                    501,
                    detail=f"No command parser for workflow type: {workflow_type}",
                )

            workflow_id = body.get("workflow_id", "")
            if not workflow_id:
                raise HTTPException(400, detail="workflow_id is required")

            cmd_type = body.get("command_type", "create")
            payload = body.get("payload", {})
            try:
                cmd = parser(cmd_type, payload)
            except (ValueError, TypeError) as e:
                raise HTTPException(400, detail=str(e))

            result = await repo.create_new(cmd, workflow_id)
            if isinstance(result, Rejection):
                raise HTTPException(400, detail=result.msg)
            return {
                "status": "ok",
                "workflow_id": result.id,
                "version": result.version,
            }

        @self.router.post("/{workflow_type}/{workflow_id}/pause")
        async def pause_workflow(
            workflow_type: str,
            workflow_id: str,
            reason: str = "",
        ):
            """Pause a workflow."""
            repo = self._repos.get(workflow_type)
            if not repo:
                raise HTTPException(
                    404, detail=f"Unknown workflow type: {workflow_type}"
                )

            result = await repo.pause_workflow(workflow_id, reason)
            if isinstance(result, Rejection):
                raise HTTPException(400, detail=result.msg)
            return {"status": "ok", "message": "Workflow paused"}

        @self.router.post("/{workflow_type}/{workflow_id}/resume")
        async def resume_workflow(workflow_type: str, workflow_id: str):
            """Resume a paused workflow."""
            repo = self._repos.get(workflow_type)
            if not repo:
                raise HTTPException(
                    404, detail=f"Unknown workflow type: {workflow_type}"
                )

            result = await repo.resume_workflow(workflow_id)
            if isinstance(result, Rejection):
                raise HTTPException(400, detail=result.msg)
            return {"status": "ok", "message": "Workflow resumed"}

        @self.router.post("/{workflow_type}/{workflow_id}/cancel")
        async def cancel_workflow(
            workflow_type: str,
            workflow_id: str,
            reason: str = "",
        ):
            """Cancel a workflow."""
            repo = self._repos.get(workflow_type)
            if not repo:
                raise HTTPException(
                    404, detail=f"Unknown workflow type: {workflow_type}"
                )

            result = await repo.cancel_workflow(
                workflow_id, reason, action_executor=self._action_executor
            )
            if isinstance(result, Rejection):
                raise HTTPException(400, detail=result.msg)
            return {"status": "ok", "message": "Workflow cancelled"}

        @self.router.post("/{workflow_type}/{workflow_id}/retry/{event_number}")
        async def retry_failed_action(
            workflow_type: str,
            workflow_id: str,
            event_number: int,
        ):
            """Retry a permanently failed action."""
            if not self._action_executor:
                raise HTTPException(
                    501,
                    detail="Retry not available: action_executor not configured",
                )
            ok = await self._action_executor.retry_failed_action(
                workflow_id, event_number
            )
            if not ok:
                raise HTTPException(
                    404,
                    detail="Activity not found or not in failed state",
                )
            return {"status": "ok", "message": "Action re-queued for retry"}
