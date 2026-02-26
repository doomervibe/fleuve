"""
Pytest configuration and shared fixtures for fleuve framework tests.
"""

import asyncio
import datetime
import os
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from nats.aio.client import Client as NATS
from pydantic import BaseModel, Field
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Set STORAGE_KEY before importing postgres models that need encryption
TEST_STORAGE_KEY = os.getenv("TEST_STORAGE_KEY", "test-storage-key-32-characters-long!")
os.environ["STORAGE_KEY"] = TEST_STORAGE_KEY

from fleuve.model import (
    ActionContext,
    EventBase,
    Rejection,
    RetryPolicy,
    StateBase,
    Workflow,
)
from fleuve.postgres import Base, Offset

# Test configuration
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://pguser:pg123@localhost/db1"
)
TEST_NATS_URL = os.getenv("TEST_NATS_URL", "nats://localhost:4222")


# Pytest configuration - let pytest-asyncio handle event loop


# Model fixtures for testing
class TestEvent(EventBase):
    type: str = "test_event"
    value: int = 0
    metadata_: dict = Field(
        default_factory=dict
    )  # optional; repo injects workflow_tags here


class TestCommand(BaseModel):
    action: str
    value: int = 0


class TestState(StateBase):
    counter: int = 0
    subscriptions: list = []
    external_subscriptions: list = []


class TestWorkflow(Workflow[TestEvent, TestCommand, TestState, TestEvent]):
    @classmethod
    def name(cls) -> str:
        return "test_workflow"

    @staticmethod
    def decide(
        state: TestState | None, cmd: TestCommand
    ) -> list[TestEvent] | Rejection:
        if cmd.value < 0:
            return Rejection()
        return [TestEvent(value=cmd.value)]

    @staticmethod
    def evolve(state: TestState | None, event: TestEvent) -> TestState:
        if state is None:
            return TestState(
                counter=event.value, subscriptions=[], external_subscriptions=[]
            )
        return TestState(
            counter=state.counter + event.value,
            subscriptions=state.subscriptions,
            external_subscriptions=state.external_subscriptions,
        )

    @classmethod
    def event_to_cmd(cls, e: TestEvent) -> TestCommand | None:
        if e.value > 0:
            return TestCommand(action="process", value=e.value)
        return None

    @staticmethod
    def is_final_event(e: TestEvent) -> bool:
        return e.value >= 100


# Database fixtures
@pytest.fixture(scope="function")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a test database engine and recreate tables for each test."""
    # Import models here (after all conftest classes are defined) to avoid circular imports
    # SQLAlchemy evaluates declared_attr methods during class initialization,
    # so we need to import after TestEvent/TestCommand are fully defined
    from fleuve.tests.models import (  # noqa: E401
        TestActivityModel,
        TestDelayScheduleModel,
        TestSnapshotModel,
        DbEventModel,
        TestExternalSubscriptionModel,
        TestOffsetModel,
        TestSubscriptionModel,
        WorkflowSyncLogModel,
    )

    # Ensure STORAGE_KEY is set (already set at module level)
    if "STORAGE_KEY" not in os.environ:
        os.environ["STORAGE_KEY"] = TEST_STORAGE_KEY

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Drop all tables before creating new ones (clean state for each test)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Clean up: drop all tables after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def test_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with automatic rollback."""
    async_session_maker = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()


@pytest.fixture
def test_session_maker(
    test_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create a test session maker."""
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def clean_tables(test_session: AsyncSession):
    """Clean all test tables before and after each test."""
    # Import here to avoid circular dependency
    from fleuve.tests.models import (
        TestActivityModel,
        TestDelayScheduleModel,
        TestSnapshotModel,
        DbEventModel,
        TestExternalSubscriptionModel,
        TestOffsetModel,
        TestSubscriptionModel,
        WorkflowSyncLogModel,
    )

    # Delete all data from test tables before test
    for table in [
        DbEventModel,
        TestActivityModel,
        TestDelayScheduleModel,
        TestSubscriptionModel,
        TestExternalSubscriptionModel,
        TestOffsetModel,
        TestSnapshotModel,
        WorkflowSyncLogModel,
    ]:
        try:
            await test_session.execute(delete(table))
        except Exception:
            pass  # Table might not exist yet
    await test_session.commit()
    yield
    # Clean up after test
    for table in [
        DbEventModel,
        TestActivityModel,
        TestDelayScheduleModel,
        TestSubscriptionModel,
        TestExternalSubscriptionModel,
        TestOffsetModel,
        TestSnapshotModel,
        WorkflowSyncLogModel,
    ]:
        try:
            await test_session.execute(delete(table))
        except Exception:
            pass
    await test_session.commit()


# NATS fixtures
@pytest.fixture
async def nats_client() -> AsyncGenerator[NATS, None]:
    """Create a test NATS client connection."""
    nc = NATS()
    await nc.connect(TEST_NATS_URL)
    yield nc
    await nc.close()


@pytest.fixture
async def nats_bucket(nats_client: NATS):
    """Create a test NATS KV bucket."""
    from nats.js.api import KeyValueConfig

    js = nats_client.jetstream()
    bucket_name = f"test_states_{uuid.uuid4().hex[:8]}"

    try:
        bucket = await js.create_key_value(KeyValueConfig(bucket=bucket_name))
    except Exception:
        # Bucket might already exist
        bucket = await js.key_value(bucket_name)

    yield bucket

    # Cleanup: delete the bucket
    try:
        await js.delete_key_value(bucket_name)
    except Exception:
        pass


# Model instances
@pytest.fixture
def retry_policy() -> RetryPolicy:
    """Create a default retry policy."""
    return RetryPolicy(
        max_retries=3,
        backoff_strategy="exponential",
        backoff_factor=2.0,
        backoff_max=datetime.timedelta(seconds=60),
        backoff_min=datetime.timedelta(seconds=1),
        backoff_jitter=0.5,
    )


@pytest.fixture
def action_context(retry_policy: RetryPolicy) -> ActionContext:
    """Create a default action context."""
    return ActionContext(
        workflow_id="test-workflow-1",
        event_number=1,
        checkpoint={},
        retry_count=0,
        retry_policy=retry_policy,
    )


@pytest.fixture
def test_workflow() -> type[TestWorkflow]:
    """Return the test workflow class."""
    return TestWorkflow


@pytest.fixture
def test_event() -> TestEvent:
    """Create a test event."""
    return TestEvent(value=42)


@pytest.fixture
def test_command() -> TestCommand:
    """Create a test command."""
    return TestCommand(action="test", value=42)


# Expose test models as fixtures
@pytest.fixture
def test_event_model() -> type:
    """Return the test event model class."""
    from fleuve.tests.models import DbEventModel

    return DbEventModel


@pytest.fixture
def test_activity_model() -> type:
    """Return the test activity model class."""
    from fleuve.tests.models import TestActivityModel

    return TestActivityModel


@pytest.fixture
def test_delay_schedule_model() -> type:
    """Return the test delay schedule model class."""
    from fleuve.tests.models import TestDelayScheduleModel

    return TestDelayScheduleModel


@pytest.fixture
def test_snapshot_model() -> type:
    """Return the test snapshot model class."""
    from fleuve.tests.models import TestSnapshotModel

    return TestSnapshotModel


@pytest.fixture
def test_subscription_model() -> type:
    """Return the test subscription model class."""
    from fleuve.tests.models import TestSubscriptionModel

    return TestSubscriptionModel


# Legacy mock fixtures (for backward compatibility with tests that might still use them)
@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession (legacy fixture)."""
    session = AsyncMock(spec=AsyncSession)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture
def mock_session_maker(test_session_maker) -> async_sessionmaker:
    """Create a mock async_sessionmaker (legacy fixture that now returns real session maker)."""
    return test_session_maker
