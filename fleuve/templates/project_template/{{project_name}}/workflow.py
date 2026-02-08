"""Workflow definition for {{project_title}}."""
from fleuve.model import Rejection, Workflow
from fleuve.stream import ConsumedEvent

from .models import (
    {{state_name}},
    {{project_title_no_spaces}}Command,
    {{project_title_no_spaces}}Event,
    CmdStart{{project_title_no_spaces}},
    Ev{{project_title_no_spaces}}Started,
)


class {{workflow_name}}(Workflow[
    {{project_title_no_spaces}}Event,
    {{project_title_no_spaces}}Command,
    {{state_name}},
    ConsumedEvent,
]):
    """{{project_title}} workflow."""

    @classmethod
    def name(cls) -> str:
        return "{{project_name}}"

    @staticmethod
    def decide(
        state: {{state_name}} | None,
        cmd: {{project_title_no_spaces}}Command,
    ) -> list[{{project_title_no_spaces}}Event] | Rejection:
        """Process commands and emit events."""
        if isinstance(cmd, CmdStart{{project_title_no_spaces}}):
            if state is not None:
                return Rejection(msg="Workflow already started")
            return [Ev{{project_title_no_spaces}}Started()]

        return Rejection(msg="Unknown command")

    @staticmethod
    def evolve(
        state: {{state_name}} | None,
        event: {{project_title_no_spaces}}Event,
    ) -> {{state_name}}:
        """Derive new state from events."""
        if state is None:
            state = {{state_name}}(subscriptions=[])

        if isinstance(event, Ev{{project_title_no_spaces}}Started):
            state.started = True

        return state

    @classmethod
    def event_to_cmd(
        cls, e: ConsumedEvent
    ) -> {{project_title_no_spaces}}Command | None:
        """Convert external events to commands."""
        # Implement if you need cross-workflow communication
        return None

    @staticmethod
    def is_final_event(e: {{project_title_no_spaces}}Event) -> bool:
        """Determine if event indicates workflow completion."""
        # Return True for final events
        return False
