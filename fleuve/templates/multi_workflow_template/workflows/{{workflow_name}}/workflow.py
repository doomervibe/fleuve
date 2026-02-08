"""Workflow definition for {{workflow_title}}."""
from fleuve.model import Rejection, Workflow
from fleuve.stream import ConsumedEvent

from .models import (
    {{workflow_class_name}}State,
    {{workflow_class_name}}Command,
    {{workflow_class_name}}Event,
    CmdStart{{workflow_class_name}},
    Ev{{workflow_class_name}}Started,
)


class {{workflow_class_name}}Workflow(Workflow[
    {{workflow_class_name}}Event,
    {{workflow_class_name}}Command,
    {{workflow_class_name}}State,
    ConsumedEvent,
]):
    """{{workflow_title}} workflow."""

    @classmethod
    def name(cls) -> str:
        return "{{workflow_name}}"

    @staticmethod
    def decide(
        state: {{workflow_class_name}}State | None,
        cmd: {{workflow_class_name}}Command,
    ) -> list[{{workflow_class_name}}Event] | Rejection:
        """Process commands and emit events."""
        if isinstance(cmd, CmdStart{{workflow_class_name}}):
            if state is not None:
                return Rejection(msg="Workflow already started")
            return [Ev{{workflow_class_name}}Started()]

        return Rejection(msg="Unknown command")

    @staticmethod
    def evolve(
        state: {{workflow_class_name}}State | None,
        event: {{workflow_class_name}}Event,
    ) -> {{workflow_class_name}}State:
        """Derive new state from events."""
        if state is None:
            state = {{workflow_class_name}}State(subscriptions=[])

        if isinstance(event, Ev{{workflow_class_name}}Started):
            state.started = True

        return state

    @classmethod
    def event_to_cmd(
        cls, e: ConsumedEvent
    ) -> {{workflow_class_name}}Command | None:
        """Convert external events to commands."""
        # Implement if you need cross-workflow communication
        return None

    @staticmethod
    def is_final_event(e: {{workflow_class_name}}Event) -> bool:
        """Determine if event indicates workflow completion."""
        # Return True for final events
        return False
