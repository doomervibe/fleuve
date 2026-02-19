"""Tests for FleuveCommandGateway."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fleuve.gateway import FleuveCommandGateway
from fleuve.model import Rejection
from fleuve.repo import AsyncRepo, StoredState

from fleuve.tests.conftest import TestCommand, TestEvent, TestState, TestWorkflow


def _parse_command(cmd_type: str, payload: dict) -> TestCommand:
    if cmd_type in ("create", "update", "process"):
        return TestCommand(action=cmd_type, value=payload.get("value", 0))
    raise ValueError(f"Unknown command: {cmd_type}")


class TestFleuveCommandGateway:
    """Tests for FleuveCommandGateway."""

    @pytest.fixture
    def mock_repo(self):
        """Create a mock AsyncRepo."""
        repo = pytest.importorskip("unittest.mock").AsyncMock(spec=AsyncRepo)
        return repo

    @pytest.fixture
    def gateway(self, mock_repo):
        """Create a FleuveCommandGateway with mock repo."""
        return FleuveCommandGateway(
            repos={"test_workflow": mock_repo},
            command_parsers={"test_workflow": _parse_command},
        )

    @pytest.fixture
    def app(self, gateway):
        """Create FastAPI app with gateway router mounted."""
        app = FastAPI()
        app.include_router(gateway.router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create TestClient for the app."""
        return TestClient(app)

    def test_process_command_success(self, client, mock_repo):
        """Test POST /commands/{workflow_type}/{workflow_id} with valid command."""
        stored = StoredState(
            id="wf-1", version=2, state=TestState(counter=15, subscriptions=[])
        )
        mock_repo.process_command.return_value = (stored, [TestEvent(value=5)])
        mock_repo.process_command.__name__ = "process_command"

        response = client.post(
            "/commands/test_workflow/wf-1",
            json={"command_type": "update", "payload": {"value": 5}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["workflow_id"] == "wf-1"
        assert data["version"] == 2
        assert data["events_count"] == 1
        mock_repo.process_command.assert_called_once()
        call_args = mock_repo.process_command.call_args
        assert call_args[0][0] == "wf-1"
        assert call_args[0][1].action == "update"
        assert call_args[0][1].value == 5

    def test_process_command_rejection(self, client, mock_repo):
        """Test process_command returns 400 on Rejection."""
        mock_repo.process_command.return_value = Rejection(msg="Workflow is paused")
        mock_repo.process_command.__name__ = "process_command"

        response = client.post(
            "/commands/test_workflow/wf-1",
            json={"command_type": "update", "payload": {"value": 5}},
        )

        assert response.status_code == 400
        assert "paused" in response.json()["detail"].lower()

    def test_process_command_unknown_workflow_type(self, client):
        """Test 404 for unknown workflow type."""
        response = client.post(
            "/commands/unknown_type/wf-1",
            json={"command_type": "update", "payload": {"value": 5}},
        )
        assert response.status_code == 404

    def test_create_workflow_success(self, client, mock_repo):
        """Test POST /commands/{workflow_type} creates workflow."""
        stored = StoredState(
            id="wf-new", version=1, state=TestState(counter=10, subscriptions=[])
        )
        mock_repo.create_new.return_value = stored
        mock_repo.create_new.__name__ = "create_new"

        response = client.post(
            "/commands/test_workflow",
            json={
                "workflow_id": "wf-new",
                "command_type": "create",
                "payload": {"value": 10},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["workflow_id"] == "wf-new"
        assert data["version"] == 1
        mock_repo.create_new.assert_called_once()
        call_args = mock_repo.create_new.call_args
        assert call_args[0][1] == "wf-new"
        assert call_args[0][0].value == 10

    def test_create_workflow_missing_workflow_id(self, client):
        """Test 400 when workflow_id is missing."""
        response = client.post(
            "/commands/test_workflow",
            json={"command_type": "create", "payload": {"value": 10}},
        )
        assert response.status_code == 400
        assert "workflow_id" in response.json()["detail"].lower()

    def test_pause_workflow_success(self, client, mock_repo):
        """Test POST /commands/{workflow_type}/{workflow_id}/pause."""
        stored = StoredState(
            id="wf-1",
            version=2,
            state=TestState(counter=10, subscriptions=[], lifecycle="paused"),
        )
        mock_repo.pause_workflow.return_value = stored
        mock_repo.pause_workflow.__name__ = "pause_workflow"

        response = client.post("/commands/test_workflow/wf-1/pause?reason=maintenance")

        assert response.status_code == 200
        assert response.json()["message"] == "Workflow paused"
        mock_repo.pause_workflow.assert_called_once_with("wf-1", "maintenance")

    def test_resume_workflow_success(self, client, mock_repo):
        """Test POST /commands/{workflow_type}/{workflow_id}/resume."""
        stored = StoredState(
            id="wf-1",
            version=3,
            state=TestState(counter=10, subscriptions=[], lifecycle="active"),
        )
        mock_repo.resume_workflow.return_value = stored
        mock_repo.resume_workflow.__name__ = "resume_workflow"

        response = client.post("/commands/test_workflow/wf-1/resume")

        assert response.status_code == 200
        mock_repo.resume_workflow.assert_called_once_with("wf-1")

    def test_cancel_workflow_success(self, client, mock_repo):
        """Test POST /commands/{workflow_type}/{workflow_id}/cancel."""
        stored = StoredState(
            id="wf-1",
            version=4,
            state=TestState(counter=10, subscriptions=[], lifecycle="cancelled"),
        )
        mock_repo.cancel_workflow.return_value = stored
        mock_repo.cancel_workflow.__name__ = "cancel_workflow"

        response = client.post("/commands/test_workflow/wf-1/cancel?reason=done")

        assert response.status_code == 200
        mock_repo.cancel_workflow.assert_called_once()
        call_args = mock_repo.cancel_workflow.call_args
        assert call_args[0][0] == "wf-1"
        assert call_args[0][1] == "done"

    def test_retry_failed_action_no_executor(self, client):
        """Test retry endpoint returns 501 when action_executor not configured."""
        gateway = FleuveCommandGateway(
            repos={"test_workflow": pytest.importorskip("unittest.mock").MagicMock()},
            command_parsers={"test_workflow": _parse_command},
            action_executor=None,
        )
        app = FastAPI()
        app.include_router(gateway.router)
        c = TestClient(app)

        response = c.post("/commands/test_workflow/wf-1/retry/1")
        assert response.status_code == 501

    def test_retry_failed_action_success(self, client, mock_repo):
        """Test retry endpoint when action_executor is configured."""
        mock_executor = pytest.importorskip("unittest.mock").AsyncMock()
        mock_executor.retry_failed_action.return_value = True
        mock_executor.retry_failed_action.__name__ = "retry_failed_action"

        gateway = FleuveCommandGateway(
            repos={"test_workflow": mock_repo},
            command_parsers={"test_workflow": _parse_command},
            action_executor=mock_executor,
        )
        app = FastAPI()
        app.include_router(gateway.router)
        c = TestClient(app)

        response = c.post("/commands/test_workflow/wf-1/retry/1")
        assert response.status_code == 200
        mock_executor.retry_failed_action.assert_called_once_with("wf-1", 1)
