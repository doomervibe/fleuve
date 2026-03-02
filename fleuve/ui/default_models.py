"""Default concrete database models for the standalone Fleuve UI.

These models use standard table names (events, activities, subscriptions,
delay_schedules) and generic Pydantic types for body/next_command columns,
allowing the UI to connect to any Fleuve database without project-specific models.

Table names can be overridden via environment variables to avoid collisions with
existing tables in the host application's database:

- ``FLEUVE_EVENTS_TABLE``          (default: ``events``)
- ``FLEUVE_ACTIVITIES_TABLE``      (default: ``activities``)
- ``FLEUVE_SUBSCRIPTIONS_TABLE``   (default: ``subscriptions``)
- ``FLEUVE_DELAY_SCHEDULES_TABLE`` (default: ``delay_schedules``)
"""

import os

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
    """Concrete StoredEvent for standalone UI.

    Override the table name via the ``FLEUVE_EVENTS_TABLE`` environment variable
    when the host database already has an unrelated ``events`` table.
    """

    __tablename__ = os.environ.get("FLEUVE_EVENTS_TABLE", "events")

    @declared_attr
    def body(cls) -> Mapped:
        return mapped_column(PydanticType(GenericEvent), nullable=False)


class DefaultSubscription(SubscriptionBase):
    """Concrete Subscription for standalone UI.

    Override the table name via the ``FLEUVE_SUBSCRIPTIONS_TABLE`` environment variable.
    """

    __tablename__ = os.environ.get("FLEUVE_SUBSCRIPTIONS_TABLE", "subscriptions")


class DefaultActivity(ActivityBase):
    """Concrete Activity for standalone UI.

    Override the table name via the ``FLEUVE_ACTIVITIES_TABLE`` environment variable.
    """

    __tablename__ = os.environ.get("FLEUVE_ACTIVITIES_TABLE", "activities")


class DefaultDelaySchedule(DelayScheduleBase):
    """Concrete DelaySchedule for standalone UI.

    Override the table name via the ``FLEUVE_DELAY_SCHEDULES_TABLE`` environment variable.
    """

    __tablename__ = os.environ.get("FLEUVE_DELAY_SCHEDULES_TABLE", "delay_schedules")

    @declared_attr
    def next_command(cls) -> Mapped:
        return mapped_column(PydanticType(GenericCommand), nullable=False)
