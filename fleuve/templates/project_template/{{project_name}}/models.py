"""Models for the {{project_title}} workflow.

Define your Events, Commands, and State here.
"""
from typing import Literal

from pydantic import BaseModel

from fleuve.model import EventBase, StateBase


# ============================================================================
# Commands - External inputs that trigger workflow decisions
# ============================================================================

class CmdStart{{project_title_no_spaces}}(BaseModel):
    """Command to start the workflow."""
    pass


# ============================================================================
# Events - Immutable state changes emitted by the workflow
# ============================================================================

class Ev{{project_title_no_spaces}}Started(EventBase):
    """Event indicating the workflow has started."""
    type: Literal["{{project_name}}.started"] = "{{project_name}}.started"
    pass


# Union type for all events
{{project_title_no_spaces}}Event = Ev{{project_title_no_spaces}}Started

# Union type for all commands
{{project_title_no_spaces}}Command = CmdStart{{project_title_no_spaces}}


# ============================================================================
# State - Workflow state derived from events
# ============================================================================

class {{state_name}}(StateBase):
    """State for the {{project_title}} workflow."""
    # Add your state fields here
    started: bool = False
    subscriptions: list = []  # Required field
