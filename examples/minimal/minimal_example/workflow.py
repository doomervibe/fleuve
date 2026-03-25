"""Minimal workflow definition."""
from fleuve.model import Rejection, Workflow
from fleuve.stream import ConsumedEvent

from .models import (
    CmdStartMinimal,
    EvMinimalStarted,
    MinimalCommand,
    MinimalEvent,
    MinimalState,
)


class MinimalWorkflow(
    Workflow[MinimalEvent, MinimalCommand, MinimalState, ConsumedEvent],
):
    """Single-purpose demo workflow: start once, then reject further starts."""

    @classmethod
    def name(cls) -> str:
        return "minimal"

    @staticmethod
    def decide(
        state: MinimalState | None,
        cmd: MinimalCommand,
    ) -> list[MinimalEvent] | Rejection:
        if isinstance(cmd, CmdStartMinimal):
            if state is not None:
                return Rejection(msg="Workflow already started")
            return [EvMinimalStarted()]
        return Rejection(msg="Unknown command")

    @staticmethod
    def _evolve(
        state: MinimalState | None,
        event: MinimalEvent,
    ) -> MinimalState:
        if state is None:
            state = MinimalState(subscriptions=[])
        if isinstance(event, EvMinimalStarted):
            state.started = True
        return state

    @classmethod
    def event_to_cmd(cls, e: ConsumedEvent) -> MinimalCommand | None:
        return None

    @staticmethod
    def is_final_event(e: MinimalEvent) -> bool:
        return False
