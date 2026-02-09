"""Adapter for {{workflow_title}} workflow side effects."""
from fleuve.model import Adapter
from fleuve.stream import ConsumedEvent

from .models import {{workflow_class_name}}Event


class {{workflow_class_name}}Adapter(Adapter[{{workflow_class_name}}Event, None]):
    """Adapter handling side effects for {{workflow_title}} workflow."""

    async def act_on(
        self,
        event: ConsumedEvent[{{workflow_class_name}}Event],
        context=None,
    ):
        """Execute side effects for events; yield zero or more commands to process."""
        # Implement your side effects here
        # Examples: send emails, call APIs, update external systems, etc.
        # Yield commands to trigger follow-up workflow processing, e.g.:
        # yield SomeCommand(...)
        if False:
            yield

    def to_be_act_on(self, event: {{workflow_class_name}}Event) -> bool:
        """Determine which events should trigger actions."""
        # Return True for events that need side effects
        return False
