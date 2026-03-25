"""SQLAlchemy models mapped to Fleuve tables."""
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import Mapped, mapped_column

from fleuve.postgres import (
    Activity as Activity_,
    DelaySchedule as DelaySchedule_,
    Offset as Offset_,
    StoredEvent as StoredEvent_,
    Subscription as Subscription_,
    PydanticType,
)

from .models import MinimalCommand, MinimalEvent


class StoredEvent(StoredEvent_):
    __tablename__ = "minimal_events"

    @declared_attr
    def body(cls) -> Mapped:
        return mapped_column(PydanticType(MinimalEvent), nullable=False)


class Subscription(Subscription_):
    __tablename__ = "minimal_subscriptions"


class Activity(Activity_):
    __tablename__ = "minimal_activities"


class DelaySchedule(DelaySchedule_):
    __tablename__ = "minimal_delay_schedules"

    @declared_attr
    def next_command(cls) -> Mapped:
        return mapped_column(PydanticType(MinimalCommand), nullable=False)


class Offset(Offset_):
    __tablename__ = "minimal_offsets"
