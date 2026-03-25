"""Side-effect adapter (no-op for this demo)."""
from fleuve.model import Adapter
from fleuve.stream import ConsumedEvent

from .models import MinimalCommand, MinimalEvent


class MinimalAdapter(Adapter[MinimalEvent, MinimalCommand]):
    """Adapter: enable later for HTTP/email/etc.; nothing to run for the demo."""

    async def act_on(self, event: ConsumedEvent[MinimalEvent], context=None):
        if False:
            yield

    def to_be_act_on(self, event: MinimalEvent) -> bool:
        return False
