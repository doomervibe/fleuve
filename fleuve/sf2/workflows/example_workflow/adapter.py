"""Adapter for Example Workflow workflow side effects."""
from fleuve.model import Adapter
from fleuve.stream import ConsumedEvent

from .models import ExampleWorkflowEvent


class ExampleWorkflowAdapter(Adapter[ExampleWorkflowEvent, None]):
    """Adapter handling side effects for Example Workflow workflow."""

    async def act_on(
        self,
        event: ConsumedEvent[ExampleWorkflowEvent],
        context=None,
    ) -> None:
        """Execute side effects for events."""
        # Implement your side effects here
        # Examples: send emails, call APIs, update external systems, etc.
        pass

    def to_be_act_on(self, event: ExampleWorkflowEvent) -> bool:
        """Determine which events should trigger actions."""
        # Return True for events that need side effects
        return False
