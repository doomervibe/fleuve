"""Adapter for {{project_title}} workflow side effects."""
from fleuve.model import Adapter
from fleuve.stream import ConsumedEvent

from .models import {{project_title_no_spaces}}Event


class {{project_title_no_spaces}}Adapter(Adapter[{{project_title_no_spaces}}Event, None]):
    """Adapter handling side effects for {{project_title}} workflow."""

    async def act_on(
        self,
        event: ConsumedEvent[{{project_title_no_spaces}}Event],
        context=None,
    ) -> None:
        """Execute side effects for events."""
        # Implement your side effects here
        # Examples: send emails, call APIs, update external systems, etc.
        pass

    def to_be_act_on(self, event: {{project_title_no_spaces}}Event) -> bool:
        """Determine which events should trigger actions."""
        # Return True for events that need side effects
        return False
