"""Shared database models for {{project_title}} workflows.

This file contains the SQLAlchemy models for the shared database tables used by
ALL workflows in this project. The tables store events, subscriptions, activities,
delays, and offsets for all workflow types.

When adding a new workflow:
1. Import its Event and Command types below
2. Add them to the AllEvents and AllCommands union types
"""
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.declarative import declared_attr

from fleuve.postgres import (
    Activity as Activity_,
    DelaySchedule as DelaySchedule_,
    Offset as Offset_,
    StoredEvent as StoredEvent_,
    Subscription as Subscription_,
    PydanticType,
)

# ============================================================================
# Import Event and Command types from all workflows
# ============================================================================
# TODO: Import your workflow event and command types here
# Example:
# from workflows.order_processing.models import OrderProcessingEvent, OrderProcessingCommand
# from workflows.payment.models import PaymentEvent, PaymentCommand


# ============================================================================
# Create union types for all events and commands
# ============================================================================
# TODO: Add your workflow event and command types to these unions
# Example:
# AllEvents = OrderProcessingEvent | PaymentEvent
# AllCommands = OrderProcessingCommand | PaymentCommand

# Placeholder - replace with your actual workflow types
AllEvents = None  # type: ignore
AllCommands = None  # type: ignore


# ============================================================================
# Shared Database Tables
# ============================================================================

class StoredEvent(StoredEvent_):
    """Table for storing workflow events from ALL workflows."""
    __tablename__ = "events"

    @declared_attr
    def body(cls) -> Mapped:
        return mapped_column(
            PydanticType(AllEvents),
            nullable=False,
        )


class Subscription(Subscription_):
    """Table for storing workflow subscriptions from ALL workflows."""
    __tablename__ = "subscriptions"


class Activity(Activity_):
    """Table for storing action execution tracking from ALL workflows."""
    __tablename__ = "activities"

    @declared_attr
    def resulting_command(cls) -> Mapped:
        return mapped_column(
            PydanticType(AllCommands | None),
            nullable=True,
        )


class DelaySchedule(DelaySchedule_):
    """Table for storing delay schedules from ALL workflows."""
    __tablename__ = "delay_schedules"

    @declared_attr
    def next_command(cls) -> Mapped:
        return mapped_column(
            PydanticType(AllCommands),
            nullable=False,
        )


class Offset(Offset_):
    """Table for storing stream reader offsets."""
    __tablename__ = "offsets"
