"""Default concrete database models for the standalone Fleuve UI.

These models use standard table names (events, activities, subscriptions,
delay_schedules) and generic Pydantic types for body/next_command columns,
allowing the UI to connect to any Fleuve database without project-specific models.
"""

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.declarative import declared_attr

from fleuve.postgres import (
    Activity as ActivityBase,
    DelaySchedule as DelayScheduleBase,
    StoredEvent as StoredEventBase,
    Subscription as SubscriptionBase,
    PydanticType,
)


class GenericEvent(BaseModel):
    """Generic event body that accepts any JSON structure."""

    model_config = ConfigDict(extra="allow")


class GenericCommand(BaseModel):
    """Generic command that accepts any JSON structure."""

    model_config = ConfigDict(extra="allow")


class DefaultStoredEvent(StoredEventBase):
    """Concrete StoredEvent for standalone UI."""

    __tablename__ = "events"

    @declared_attr
    def body(cls) -> Mapped:
        return mapped_column(PydanticType(GenericEvent), nullable=False)


class DefaultSubscription(SubscriptionBase):
    """Concrete Subscription for standalone UI."""

    __tablename__ = "subscriptions"


class DefaultActivity(ActivityBase):
    """Concrete Activity for standalone UI."""

    __tablename__ = "activities"


class DefaultDelaySchedule(DelayScheduleBase):
    """Concrete DelaySchedule for standalone UI."""

    __tablename__ = "delay_schedules"

    @declared_attr
    def next_command(cls) -> Mapped:
        return mapped_column(PydanticType(GenericCommand), nullable=False)
