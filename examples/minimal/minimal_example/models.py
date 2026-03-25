"""Events, commands, and state for the minimal example workflow."""
from typing import Literal

from pydantic import BaseModel, Field

from fleuve.model import EventBase, StateBase, Sub


class CmdStartMinimal(BaseModel):
    """Command to create and start the demo workflow."""

    pass


class EvMinimalStarted(EventBase):
    type: Literal["minimal.started"] = "minimal.started"


MinimalEvent = EvMinimalStarted
MinimalCommand = CmdStartMinimal


class MinimalState(StateBase):
    """Workflow state."""

    subscriptions: list[Sub] = Field(default_factory=list)
    started: bool = False
