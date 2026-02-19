"""Tests for Fleuve UI API, including command gateway integration."""

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from fleuve.repo import AsyncRepo, StoredState
from fleuve.postgres import StoredEvent, Activity, DelaySchedule, Subscription

from fleuve_ui.backend.api import create_app

from fleuve.tests.conftest import TestState


def _parse_command(cmd_type: str, payload: dict):
    from pydantic import BaseModel

    class TestCommand(BaseModel):
        action: str
        value: int = 0

    return TestCommand(action=cmd_type, value=payload.get("value", 0))


class TestCreateAppWithCommandGateway:
    """Tests for create_app with command gateway (repos + command_parsers)."""

    def test_command_gateway_mounted_when_repos_and_parsers_provided(self):
        """Command gateway routes are available when repos and command_parsers provided."""
        mock_repo = AsyncMock(spec=AsyncRepo)

        app = create_app(
            session_maker=MagicMock(),
            event_model=MagicMock(),
            activity_model=MagicMock(),
            delay_schedule_model=MagicMock(),
            subscription_model=MagicMock(),
            repos={"test_workflow": mock_repo},
            command_parsers={"test_workflow": _parse_command},
        )

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        command_routes = [r for r in routes if "/commands" in r]
        assert len(command_routes) > 0

    def test_command_gateway_not_mounted_without_parsers(self):
        """Command gateway is not mounted when command_parsers is empty."""
        mock_repo = AsyncMock(spec=AsyncRepo)

        app = create_app(
            session_maker=MagicMock(),
            event_model=MagicMock(),
            activity_model=MagicMock(),
            delay_schedule_model=MagicMock(),
            subscription_model=MagicMock(),
            repos={"test_workflow": mock_repo},
            command_parsers={},
        )

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        command_routes = [r for r in routes if "/commands" in r]
        assert len(command_routes) == 0

    def test_command_gateway_built_from_repo_and_workflow_types(self):
        """When single repo and single workflow_type, gateway_repos is built."""
        mock_repo = AsyncMock(spec=AsyncRepo)
        mock_workflow = MagicMock()
        stored = StoredState(
            id="wf-1",
            version=2,
            state=TestState(counter=10, subscriptions=[], external_subscriptions=[]),
        )
        mock_repo.process_command.return_value = (stored, [])
        mock_repo.process_command.__name__ = "process_command"

        app = create_app(
            session_maker=MagicMock(),
            event_model=MagicMock(),
            activity_model=MagicMock(),
            delay_schedule_model=MagicMock(),
            subscription_model=MagicMock(),
            repo=mock_repo,
            workflow_types={"my_workflow": mock_workflow},
            command_parsers={"my_workflow": _parse_command},
        )

        client = TestClient(app)
        response = client.post(
            "/commands/my_workflow/wf-1",
            json={"command_type": "update", "payload": {"value": 5}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["workflow_id"] == "wf-1"
        assert data["version"] == 2
