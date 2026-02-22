"""Minimal database models for standalone Fleuve UI server.

When run standalone, fleuve_ui needs concrete models to query the database.
These models use generic body/command types so they work with any workflow data.
For project-specific UIs, use your project's db_models instead.
"""
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.declarative import declared_attr

from fleuve.postgres import (
    Activity as Activity_,
    DelaySchedule as DelaySchedule_,
    StoredEvent as StoredEvent_,
    Subscription as Subscription_,
    PydanticType,
)


class GenericEventBody(BaseModel):
    """Accepts any event body as JSON for UI display."""

    model_config = ConfigDict(extra="allow")


class GenericCommand(BaseModel):
    """Accepts any command as JSON for delay schedules."""

    model_config = ConfigDict(extra="allow")


class StoredEvent(StoredEvent_):
    """Concrete event table for standalone UI."""

    __tablename__ = "events"

    @declared_attr
    def body(cls) -> Mapped:
        return mapped_column(PydanticType(GenericEventBody), nullable=False)


class Subscription(Subscription_):
    """Concrete subscription table."""

    __tablename__ = "subscriptions"


class Activity(Activity_):
    """Concrete activity table."""

    __tablename__ = "activities"


class DelaySchedule(DelaySchedule_):
    """Concrete delay schedule table."""

    __tablename__ = "delay_schedules"

    @declared_attr
    def next_command(cls) -> Mapped:
        return mapped_column(PydanticType(GenericCommand), nullable=False)
