"""Models for the Project workflow.

Define your Events, Commands, and State here.
"""
from typing import Literal

from pydantic import BaseModel

from fleuve.model import EventBase, StateBase


# ============================================================================
# Commands - External inputs that trigger workflow decisions
# ============================================================================

class CmdStartProject(BaseModel):
    """Command to start the workflow."""
    pass


# ============================================================================
# Events - Immutable state changes emitted by the workflow
# ============================================================================

class EvProjectStarted(EventBase):
    """Event indicating the workflow has started."""
    type: Literal["project.started"] = "project.started"
    pass


# Union type for all events
ProjectEvent = EvProjectStarted

# Union type for all commands
ProjectCommand = CmdStartProject


# ============================================================================
# State - Workflow state derived from events
# ============================================================================

class ProjectState(StateBase):
    """State for the Project workflow."""
    # Add your state fields here
    started: bool = False
    subscriptions: list = []  # Required field
