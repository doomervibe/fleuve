"""Database models for {{project_title}} workflow."""
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

from .models import {{project_title_no_spaces}}Event, {{project_title_no_spaces}}Command


class StoredEvent(StoredEvent_):
    """Table for storing workflow events."""
    __tablename__ = "events"

    @declared_attr
    def body(cls) -> Mapped:
        return mapped_column(
            PydanticType({{project_title_no_spaces}}Event),
            nullable=False,
        )


class Subscription(Subscription_):
    """Table for storing workflow subscriptions."""
    __tablename__ = "subscriptions"


class Activity(Activity_):
    """Table for storing action execution tracking."""
    __tablename__ = "activities"

    @declared_attr
    def resulting_command(cls) -> Mapped:
        return mapped_column(
            PydanticType({{project_title_no_spaces}}Command | None),
            nullable=True,
        )


class DelaySchedule(DelaySchedule_):
    """Table for storing delay schedules."""
    __tablename__ = "delay_schedules"

    @declared_attr
    def next_command(cls) -> Mapped:
        return mapped_column(
            PydanticType({{project_title_no_spaces}}Command),
            nullable=False,
        )


class Offset(Offset_):
    """Table for storing stream reader offsets."""
    __tablename__ = "offsets"
