"""
Unit tests for les.repo module.
"""
import asyncio
import uuid
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

import pytest
from nats.aio.client import Client as NATS
from pydantic import BaseModel

from sqlalchemy import insert, select

from fleuve.model import EventBase, Rejection, StateBase, Workflow
from fleuve.repo import AsyncRepo, EuphStorageNATS, StoredState, WorkflowNotFound


# Use test models from conftest
from fleuve.tests.conftest import TestCommand, TestEvent, TestState, TestWorkflow

# Aliases for backward compatibility
MockState = TestState
MockEvent = TestEvent
MockCommand = TestCommand
MockWorkflow = TestWorkflow


class TestStoredState:
    """Tests for StoredState."""

    def test_stored_state_creation(self):
        """Test creating a stored state."""
        state = MockState(counter=42, subscriptions=[])
        stored = StoredState(id="wf-1", version=5, state=state)
        assert stored.id == "wf-1"
        assert stored.version == 5
        assert stored.state.counter == 42


class TestEuphStorageNATS:
    """Tests for EuphStorageNATS using real NATS."""

    @pytest.mark.asyncio
    async def test_create_bucket_if_not_exists(self, nats_client: NATS, nats_bucket):
        """Test creating bucket if it doesn't exist."""
        from fleuve.tests.conftest import TestState

        bucket_name = f"test_bucket_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(
            c=nats_client,
            bucket=bucket_name,
            s=TestState,
        )

        async with storage:
            assert storage._bucket is not None
            # Verify bucket exists by trying to get it
            js = nats_client.jetstream()
            bucket = await js.key_value(bucket_name)
            assert bucket is not None

        # Cleanup
        try:
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_put_state(self, nats_client: NATS, nats_bucket):
        """Test putting state into storage."""
        from fleuve.tests.conftest import TestState

        bucket_name = f"test_bucket_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(
            c=nats_client,
            bucket=bucket_name,
            s=TestState,
        )

        async with storage:
            state = TestState(counter=10, subscriptions=[])
            stored = StoredState(id="wf-1", version=1, state=state)
            await storage.put_state(stored)

            # Verify state was stored
            result = await storage.get_state("wf-1")
            assert result is not None
            assert result.id == "wf-1"
            assert result.state.counter == 10

        # Cleanup
        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_get_state(self, nats_client: NATS, nats_bucket):
        """Test getting state from storage."""
        from fleuve.tests.conftest import TestState

        bucket_name = f"test_bucket_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(
            c=nats_client,
            bucket=bucket_name,
            s=TestState,
        )

        async with storage:
            # First store a state
            state = TestState(counter=10, subscriptions=[])
            stored = StoredState(id="wf-1", version=1, state=state)
            await storage.put_state(stored)

            # Then retrieve it
            result = await storage.get_state("wf-1")
            assert result is not None
            assert result.id == "wf-1"
            assert result.state.counter == 10

        # Cleanup
        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_get_state_not_found(self, nats_client: NATS, nats_bucket):
        """Test getting state when it doesn't exist."""
        from fleuve.tests.conftest import TestState

        bucket_name = f"test_bucket_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(
            c=nats_client,
            bucket=bucket_name,
            s=TestState,
        )

        async with storage:
            result = await storage.get_state("nonexistent-wf")
            assert result is None

        # Cleanup
        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_remove_state(self, nats_client: NATS, nats_bucket):
        """Test removing state from storage."""
        from fleuve.tests.conftest import TestState

        bucket_name = f"test_bucket_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(
            c=nats_client,
            bucket=bucket_name,
            s=TestState,
        )

        async with storage:
            # First store a state
            state = TestState(counter=10, subscriptions=[])
            stored = StoredState(id="wf-1", version=1, state=state)
            await storage.put_state(stored)

            # Verify it exists
            result = await storage.get_state("wf-1")
            assert result is not None

            # Remove it
            await storage.remove_state("wf-1")

            # Verify it's gone
            result = await storage.get_state("wf-1")
            assert result is None

        # Cleanup
        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass


class TestAsyncRepo:
    """Tests for AsyncRepo using real PostgreSQL and NATS."""

    @pytest.fixture
    async def ephemeral_storage(self, nats_client: NATS):
        """Create a real ephemeral storage with NATS."""
        from fleuve.repo import EuphStorageNATS
        from fleuve.tests.conftest import TestState

        bucket_name = f"test_states_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(
            c=nats_client,
            bucket=bucket_name,
            s=TestState,
        )

        # Enter context manager to initialize bucket
        await storage.__aenter__()
        
        yield storage

        # Cleanup: exit context manager and delete bucket
        await storage.__aexit__(None, None, None)
        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.fixture
    def repo(
        self,
        test_session_maker,
        ephemeral_storage,
        test_event_model,
        test_subscription_model,
    ):
        """Create an AsyncRepo instance with real database and NATS."""
        from fleuve.tests.conftest import TestWorkflow

        return AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
        )

    @pytest.mark.asyncio
    async def test_create_new_success(
        self,
        repo,
        test_session,
        clean_tables,
    ):
        """Test creating a new workflow."""
        from fleuve.tests.conftest import TestCommand

        cmd = TestCommand(action="create", value=10)

        result = await repo.create_new(cmd, "wf-1")

        assert not isinstance(result, Rejection)
        assert isinstance(result, StoredState)
        assert result.id == "wf-1"
        assert result.state.counter == 10

        # Verify event was stored in database
        from sqlalchemy import select
        event = await test_session.scalar(
            select(repo.db_event_model)
            .where(repo.db_event_model.workflow_id == "wf-1")
            .where(repo.db_event_model.workflow_version == 1)
        )
        assert event is not None
        assert event.event_type == "test_event"
        assert event.body.value == 10

    @pytest.mark.asyncio
    async def test_create_new_rejection(
        self,
        repo,
        clean_tables,
    ):
        """Test creating a new workflow with rejection."""
        from fleuve.tests.conftest import TestCommand

        cmd = TestCommand(action="create", value=-10)  # Negative value causes rejection
        result = await repo.create_new(cmd, "wf-1")
        assert isinstance(result, Rejection)

    @pytest.mark.asyncio
    async def test_get_current_state_from_ephemeral(
        self,
        repo,
        test_session,
        clean_tables,
    ):
        """Test getting current state from ephemeral storage."""
        from fleuve.tests.conftest import TestCommand, TestState

        # Create a workflow first
        cmd = TestCommand(action="create", value=42)
        result = await repo.create_new(cmd, "wf-1")
        assert not isinstance(result, Rejection)

        # Get state from ephemeral storage
        result = await repo.get_current_state(test_session, "wf-1")
        assert result.version == 1
        assert result.state.counter == 42

    @pytest.mark.asyncio
    async def test_get_current_state_not_found(
        self,
        repo,
        test_session,
        clean_tables,
    ):
        """Test getting current state when workflow doesn't exist."""
        with pytest.raises(WorkflowNotFound):
            await repo.get_current_state(test_session, "wf-nonexistent")

    @pytest.mark.asyncio
    async def test_load_state(
        self,
        repo,
        test_session,
        clean_tables,
    ):
        """Test loading state from events."""
        from fleuve.tests.conftest import TestCommand
        from sqlalchemy import insert

        # Create events directly in database
        cmd1 = TestCommand(action="create", value=10)
        await repo.create_new(cmd1, "wf-1")

        # Add another event
        cmd2 = TestCommand(action="update", value=20)
        result = await repo.process_command("wf-1", cmd2)
        assert not isinstance(result, Rejection)

        # Load state from events
        stored = await repo.load_state(test_session, "wf-1")
        assert stored is not None
        assert stored.state.counter == 30  # 10 + 20
        assert stored.version == 2

    @pytest.mark.asyncio
    async def test_load_state_at_version(
        self,
        repo,
        test_session,
        clean_tables,
    ):
        """Test loading state at a specific version."""
        from fleuve.tests.conftest import TestCommand

        # Create events
        cmd1 = TestCommand(action="create", value=10)
        await repo.create_new(cmd1, "wf-1")

        cmd2 = TestCommand(action="update", value=20)
        await repo.process_command("wf-1", cmd2)

        # Load state at version 1
        stored = await repo.load_state(test_session, "wf-1", at_version=1)
        assert stored is not None
        assert stored.version == 1
        assert stored.state.counter == 10  # Only first event

    @pytest.mark.asyncio
    async def test_sync_db_same_transaction_as_event_insert(
        self,
        test_session_maker,
        ephemeral_storage,
        test_event_model,
        test_subscription_model,
        test_session,
        clean_tables,
    ):
        """sync_db runs in the same transaction as event insert; on rejection it is not called."""
        from fleuve.tests.conftest import TestCommand
        from fleuve.tests.models import WorkflowSyncLogModel

        async def sync_db(s, workflow_id, old_state, new_state, events):
            await s.execute(
                insert(WorkflowSyncLogModel).values(
                    workflow_id=workflow_id,
                    events_count=len(events),
                )
            )

        repo = AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
            sync_db=sync_db,
        )

        # create_new success: sync_db runs, row visible after commit
        result = await repo.create_new(TestCommand(action="create", value=10), "wf-sync-1")
        assert not isinstance(result, Rejection)
        rows = (
            await test_session.execute(
                select(WorkflowSyncLogModel).where(
                    WorkflowSyncLogModel.workflow_id == "wf-sync-1"
                )
            )
        )
        log_rows = rows.scalars().all()
        assert len(log_rows) == 1
        assert log_rows[0].events_count == 1

        # process_command: sync_db runs again, second row in same DB
        await repo.process_command("wf-sync-1", TestCommand(action="update", value=5))
        rows2 = (
            await test_session.execute(
                select(WorkflowSyncLogModel).where(
                    WorkflowSyncLogModel.workflow_id == "wf-sync-1"
                )
            )
        )
        log_rows2 = rows2.scalars().all()
        assert len(log_rows2) == 2
        assert sorted(r.events_count for r in log_rows2) == [1, 1]

        # create_new rejection: sync_db is not called, no row for that workflow
        reject_result = await repo.create_new(
            TestCommand(action="create", value=-1), "wf-reject"
        )
        assert isinstance(reject_result, Rejection)
        rows_reject = (
            await test_session.execute(
                select(WorkflowSyncLogModel).where(
                    WorkflowSyncLogModel.workflow_id == "wf-reject"
                )
            )
        )
        assert len(rows_reject.scalars().all()) == 0

    @pytest.mark.asyncio
    async def test_sync_db_via_adapter(
        self,
        test_session_maker,
        ephemeral_storage,
        test_event_model,
        test_subscription_model,
        test_session,
        clean_tables,
    ):
        """sync_db can be provided by adapter.sync_db when adapter is passed to repo."""
        from fleuve.model import Adapter
        from fleuve.tests.conftest import TestCommand
        from fleuve.tests.models import WorkflowSyncLogModel

        class AdapterWithSyncDb(Adapter):
            async def act_on(self, event, context=None):
                if False:
                    yield  # async generator

            def to_be_act_on(self, event):
                return False

            async def sync_db(self, s, workflow_id, old_state, new_state, events):
                await s.execute(
                    insert(WorkflowSyncLogModel).values(
                        workflow_id=workflow_id,
                        events_count=len(events),
                    )
                )

        adapter = AdapterWithSyncDb()
        repo = AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
            adapter=adapter,
        )

        result = await repo.create_new(TestCommand(action="create", value=10), "wf-adapter-1")
        assert not isinstance(result, Rejection)
        rows_result = await test_session.execute(
            select(WorkflowSyncLogModel).where(
                WorkflowSyncLogModel.workflow_id == "wf-adapter-1"
            )
        )
        rows = rows_result.scalars().all()
        assert len(rows) == 1
        assert rows[0].events_count == 1
