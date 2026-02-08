"""Workflow definition for Project."""
from fleuve.model import Rejection, Workflow
from fleuve.stream import ConsumedEvent

from .models import (
    ProjectState,
    ProjectCommand,
    ProjectEvent,
    CmdStartProject,
    EvProjectStarted,
)


class ProjectWorkflow(Workflow[
    ProjectEvent,
    ProjectCommand,
    ProjectState,
    ConsumedEvent,
]):
    """Project workflow."""

    @classmethod
    def name(cls) -> str:
        return "project"

    @staticmethod
    def decide(
        state: ProjectState | None,
        cmd: ProjectCommand,
    ) -> list[ProjectEvent] | Rejection:
        """Process commands and emit events."""
        if isinstance(cmd, CmdStartProject):
            if state is not None:
                return Rejection(msg="Workflow already started")
            return [EvProjectStarted()]

        return Rejection(msg="Unknown command")

    @staticmethod
    def evolve(
        state: ProjectState | None,
        event: ProjectEvent,
    ) -> ProjectState:
        """Derive new state from events."""
        if state is None:
            state = ProjectState(subscriptions=[])

        if isinstance(event, EvProjectStarted):
            state.started = True

        return state

    @classmethod
    def event_to_cmd(
        cls, e: ConsumedEvent
    ) -> ProjectCommand | None:
        """Convert external events to commands."""
        # Implement if you need cross-workflow communication
        return None

    @staticmethod
    def is_final_event(e: ProjectEvent) -> bool:
        """Determine if event indicates workflow completion."""
        # Return True for final events
        return False
