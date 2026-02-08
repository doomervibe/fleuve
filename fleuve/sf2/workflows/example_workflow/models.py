"""Models for the Example Workflow workflow.

Define your Events, Commands, and State here.
"""
from typing import Literal

from pydantic import BaseModel

from fleuve.model import EventBase, StateBase


# ============================================================================
# Commands - External inputs that trigger workflow decisions
# ============================================================================

class CmdStartExampleWorkflow(BaseModel):
    """Command to start the workflow."""
    pass


# ============================================================================
# Events - Immutable state changes emitted by the workflow
# ============================================================================

class EvExampleWorkflowStarted(EventBase):
    """Event indicating the workflow has started."""
    type: Literal["example_workflow.started"] = "example_workflow.started"
    pass


# Union type for all events
ExampleWorkflowEvent = EvExampleWorkflowStarted

# Union type for all commands
ExampleWorkflowCommand = CmdStartExampleWorkflow


# ============================================================================
# State - Workflow state derived from events
# ============================================================================

class ExampleWorkflowState(StateBase):
    """State for the Example Workflow workflow."""
    # Add your state fields here
    started: bool = False
    subscriptions: list = []  # Required field
