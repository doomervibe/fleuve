"""Models for the {{workflow_title}} workflow.

Define your Events, Commands, and State here.
"""
from typing import Literal

from pydantic import BaseModel

from fleuve.model import EventBase, StateBase


# ============================================================================
# Commands - External inputs that trigger workflow decisions
# ============================================================================

class CmdStart{{workflow_class_name}}(BaseModel):
    """Command to start the workflow."""
    pass


# ============================================================================
# Events - Immutable state changes emitted by the workflow
# ============================================================================

class Ev{{workflow_class_name}}Started(EventBase):
    """Event indicating the workflow has started."""
    type: Literal["{{workflow_name}}.started"] = "{{workflow_name}}.started"
    pass


# Union type for all events
{{workflow_class_name}}Event = Ev{{workflow_class_name}}Started

# Union type for all commands
{{workflow_class_name}}Command = CmdStart{{workflow_class_name}}


# ============================================================================
# State - Workflow state derived from events
# ============================================================================

class {{workflow_class_name}}State(StateBase):
    """State for the {{workflow_title}} workflow."""
    # Add your state fields here
    started: bool = False
    subscriptions: list = []  # Required field
