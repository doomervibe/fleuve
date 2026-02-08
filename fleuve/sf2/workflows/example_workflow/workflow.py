"""Workflow definition for Example Workflow."""
from fleuve.model import Rejection, Workflow
from fleuve.stream import ConsumedEvent

from .models import (
    ExampleWorkflowState,
    ExampleWorkflowCommand,
    ExampleWorkflowEvent,
    CmdStartExampleWorkflow,
    EvExampleWorkflowStarted,
)


class ExampleWorkflowWorkflow(Workflow[
    ExampleWorkflowEvent,
    ExampleWorkflowCommand,
    ExampleWorkflowState,
    ConsumedEvent,
]):
    """Example Workflow workflow."""

    @classmethod
    def name(cls) -> str:
        return "example_workflow"

    @staticmethod
    def decide(
        state: ExampleWorkflowState | None,
        cmd: ExampleWorkflowCommand,
    ) -> list[ExampleWorkflowEvent] | Rejection:
        """Process commands and emit events."""
        if isinstance(cmd, CmdStartExampleWorkflow):
            if state is not None:
                return Rejection(msg="Workflow already started")
            return [EvExampleWorkflowStarted()]

        return Rejection(msg="Unknown command")

    @staticmethod
    def evolve(
        state: ExampleWorkflowState | None,
        event: ExampleWorkflowEvent,
    ) -> ExampleWorkflowState:
        """Derive new state from events."""
        if state is None:
            state = ExampleWorkflowState(subscriptions=[])

        if isinstance(event, EvExampleWorkflowStarted):
            state.started = True

        return state

    @classmethod
    def event_to_cmd(
        cls, e: ConsumedEvent
    ) -> ExampleWorkflowCommand | None:
        """Convert external events to commands."""
        # Implement if you need cross-workflow communication
        return None

    @staticmethod
    def is_final_event(e: ExampleWorkflowEvent) -> bool:
        """Determine if event indicates workflow completion."""
        # Return True for final events
        return False
