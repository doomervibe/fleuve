"""
Unit tests for fleuve.repo module.
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
from fleuve.repo import (
    AsyncRepo,
    EuphStorageNATS,
    InProcessEuphemeralStorage,
    StoredState,
    TieredEuphemeralStorage,
    WorkflowNotFound,
)


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


class TestInProcessEuphemeralStorage:
    """Tests for InProcessEuphemeralStorage (L1 cache)."""

    @pytest.mark.asyncio
    async def test_put_and_get(self):
        state = TestState(counter=42, subscriptions=[])
        stored = StoredState(id="wf-1", version=1, state=state)

        storage = InProcessEuphemeralStorage(max_size=100)
        async with storage:
            await storage.put_state(stored)
            result = await storage.get_state("wf-1")
            assert result is not None
            assert result.id == "wf-1"
            assert result.state.counter == 42
            assert result is stored

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        storage = InProcessEuphemeralStorage(max_size=100)
        async with storage:
            result = await storage.get_state("nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_remove(self):
        state = TestState(counter=1, subscriptions=[])
        stored = StoredState(id="wf-1", version=1, state=state)

        storage = InProcessEuphemeralStorage(max_size=100)
        async with storage:
            await storage.put_state(stored)
            await storage.remove_state("wf-1")
            result = await storage.get_state("wf-1")
            assert result is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        storage = InProcessEuphemeralStorage(max_size=2)
        async with storage:
            for i in range(3):
                s = TestState(counter=i, subscriptions=[])
                await storage.put_state(StoredState(id=f"wf-{i}", version=1, state=s))

            assert await storage.get_state("wf-0") is None
            assert (await storage.get_state("wf-1")) is not None
            assert (await storage.get_state("wf-2")) is not None

    @pytest.mark.asyncio
    async def test_zero_deser_cost(self):
        """get_state returns the exact same object — no copy, no deser."""
        state = TestState(counter=99, subscriptions=[])
        stored = StoredState(id="wf-1", version=1, state=state)

        storage = InProcessEuphemeralStorage(max_size=100)
        async with storage:
            await storage.put_state(stored)
            result = await storage.get_state("wf-1")
            assert result is stored

    @pytest.mark.asyncio
    async def test_lru_reorder_on_access(self):
        """Accessing a key moves it to the end, preventing eviction."""
        storage = InProcessEuphemeralStorage(max_size=2)
        async with storage:
            s0 = StoredState(id="wf-0", version=1, state=TestState(counter=0, subscriptions=[]))
            s1 = StoredState(id="wf-1", version=1, state=TestState(counter=1, subscriptions=[]))
            await storage.put_state(s0)
            await storage.put_state(s1)

            # Access wf-0 to make it most recently used
            await storage.get_state("wf-0")

            # Insert wf-2 — should evict wf-1 (least recently used), not wf-0
            s2 = StoredState(id="wf-2", version=1, state=TestState(counter=2, subscriptions=[]))
            await storage.put_state(s2)

            assert await storage.get_state("wf-0") is not None
            assert await storage.get_state("wf-1") is None
            assert await storage.get_state("wf-2") is not None

    @pytest.mark.asyncio
    async def test_overwrite_same_key(self):
        """Putting a state with the same id overwrites without growing the cache."""
        storage = InProcessEuphemeralStorage(max_size=2)
        async with storage:
            s1 = StoredState(id="wf-1", version=1, state=TestState(counter=1, subscriptions=[]))
            s1_v2 = StoredState(id="wf-1", version=2, state=TestState(counter=99, subscriptions=[]))
            await storage.put_state(s1)
            await storage.put_state(s1_v2)

            assert len(storage._cache) == 1
            result = await storage.get_state("wf-1")
            assert result.version == 2
            assert result.state.counter == 99

    @pytest.mark.asyncio
    async def test_context_exit_clears_cache(self):
        """Exiting the context manager clears all cached entries."""
        storage = InProcessEuphemeralStorage(max_size=100)
        async with storage:
            for i in range(5):
                s = StoredState(id=f"wf-{i}", version=1, state=TestState(counter=i, subscriptions=[]))
                await storage.put_state(s)
            assert len(storage._cache) == 5

        assert len(storage._cache) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_is_noop(self):
        """Removing a key that doesn't exist should not raise."""
        storage = InProcessEuphemeralStorage(max_size=100)
        async with storage:
            await storage.remove_state("nonexistent")


class TestTieredEuphemeralStorage:
    """Tests for TieredEuphemeralStorage (L1 + L2)."""

    @pytest.mark.asyncio
    async def test_l1_hit(self, nats_client: NATS):
        """L1 hit returns immediately without L2 access."""
        bucket_name = f"test_tiered_{uuid.uuid4().hex[:8]}"
        l1 = InProcessEuphemeralStorage(max_size=100)
        l2 = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)

        async with TieredEuphemeralStorage(l1=l1, l2=l2) as storage:
            state = TestState(counter=10, subscriptions=[])
            stored = StoredState(id="wf-1", version=1, state=state)
            await storage.put_state(stored)

            result = await storage.get_state("wf-1")
            assert result is stored

        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_l2_fallback(self, nats_client: NATS):
        """L1 miss falls back to L2 and populates L1."""
        bucket_name = f"test_tiered_{uuid.uuid4().hex[:8]}"
        l1 = InProcessEuphemeralStorage(max_size=100)
        l2 = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)

        async with TieredEuphemeralStorage(l1=l1, l2=l2) as storage:
            state = TestState(counter=7, subscriptions=[])
            stored = StoredState(id="wf-1", version=1, state=state)
            await l2.put_state(stored)

            result = await storage.get_state("wf-1")
            assert result is not None
            assert result.state.counter == 7

            l1_result = await l1.get_state("wf-1")
            assert l1_result is not None

        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_remove_clears_both(self, nats_client: NATS):
        """remove_state clears both L1 and L2."""
        bucket_name = f"test_tiered_{uuid.uuid4().hex[:8]}"
        l1 = InProcessEuphemeralStorage(max_size=100)
        l2 = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)

        async with TieredEuphemeralStorage(l1=l1, l2=l2) as storage:
            state = TestState(counter=5, subscriptions=[])
            stored = StoredState(id="wf-1", version=1, state=state)
            await storage.put_state(stored)
            await storage.remove_state("wf-1")

            assert await l1.get_state("wf-1") is None
            assert await l2.get_state("wf-1") is None

        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_both_miss_returns_none(self, nats_client: NATS):
        """get_state returns None when key is in neither L1 nor L2."""
        bucket_name = f"test_tiered_{uuid.uuid4().hex[:8]}"
        l1 = InProcessEuphemeralStorage(max_size=100)
        l2 = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)

        async with TieredEuphemeralStorage(l1=l1, l2=l2) as storage:
            result = await storage.get_state("nonexistent")
            assert result is None

        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_put_writes_to_both_tiers(self, nats_client: NATS):
        """put_state writes to both L1 and L2."""
        bucket_name = f"test_tiered_{uuid.uuid4().hex[:8]}"
        l1 = InProcessEuphemeralStorage(max_size=100)
        l2 = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)

        async with TieredEuphemeralStorage(l1=l1, l2=l2) as storage:
            state = TestState(counter=42, subscriptions=[])
            stored = StoredState(id="wf-1", version=1, state=state)
            await storage.put_state(stored)

            l1_result = await l1.get_state("wf-1")
            l2_result = await l2.get_state("wf-1")
            assert l1_result is not None
            assert l2_result is not None
            assert l1_result.state.counter == 42
            assert l2_result.state.counter == 42

        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_l2_fallback_promotes_to_l1(self, nats_client: NATS):
        """After L2 fallback, subsequent get is an L1 hit (same object)."""
        bucket_name = f"test_tiered_{uuid.uuid4().hex[:8]}"
        l1 = InProcessEuphemeralStorage(max_size=100)
        l2 = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)

        async with TieredEuphemeralStorage(l1=l1, l2=l2) as storage:
            state = TestState(counter=7, subscriptions=[])
            stored = StoredState(id="wf-1", version=1, state=state)
            await l2.put_state(stored)

            first = await storage.get_state("wf-1")
            second = await storage.get_state("wf-1")
            # Second call should return from L1 — same object identity
            assert first is second

        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_overwrite_propagates_to_both(self, nats_client: NATS):
        """Overwriting a key updates both L1 and L2."""
        bucket_name = f"test_tiered_{uuid.uuid4().hex[:8]}"
        l1 = InProcessEuphemeralStorage(max_size=100)
        l2 = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)

        async with TieredEuphemeralStorage(l1=l1, l2=l2) as storage:
            v1 = StoredState(id="wf-1", version=1, state=TestState(counter=1, subscriptions=[]))
            v2 = StoredState(id="wf-1", version=2, state=TestState(counter=99, subscriptions=[]))
            await storage.put_state(v1)
            await storage.put_state(v2)

            l1_result = await l1.get_state("wf-1")
            l2_result = await l2.get_state("wf-1")
            assert l1_result is not None
            assert l2_result is not None
            assert l1_result.version == 2
            assert l2_result.version == 2

        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass


class TestEuphStorageNATSPickle:
    """Tests that EuphStorageNATS uses pickle serialization correctly."""

    @pytest.mark.asyncio
    async def test_stored_data_is_pickle_format(self, nats_client: NATS):
        """Verify the raw bytes in NATS KV are pickle, not JSON."""
        import pickle

        bucket_name = f"test_pickle_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)

        async with storage:
            state = TestState(counter=42, subscriptions=[])
            stored = StoredState(id="wf-1", version=1, state=state)
            await storage.put_state(stored)

            # Read raw bytes from the bucket
            assert storage._bucket is not None
            entry = await storage._bucket.get("wf-1")
            raw = entry.value
            assert raw is not None

            # Should be valid pickle, not JSON
            recovered = pickle.loads(raw)
            assert isinstance(recovered, StoredState)
            assert recovered.state.counter == 42

            # Should NOT be valid JSON
            import json
            try:
                json.loads(raw)
                assert False, "Raw bytes should not be valid JSON"
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_roundtrip_preserves_complex_state(self, nats_client: NATS):
        """Pickle round-trip preserves nested structures and types."""
        from fleuve.model import Sub

        bucket_name = f"test_pickle_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)

        async with storage:
            subs = [Sub(
                workflow_id="other-wf",
                event_type="order.placed",
            )]
            state = TestState(counter=99, subscriptions=subs)
            stored = StoredState(id="wf-complex", version=5, state=state)
            await storage.put_state(stored)

            result = await storage.get_state("wf-complex")
            assert result is not None
            assert result.id == "wf-complex"
            assert result.version == 5
            assert result.state.counter == 99
            assert len(result.state.subscriptions) == 1
            assert result.state.subscriptions[0].event_type == "order.placed"

        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_overwrite_with_pickle(self, nats_client: NATS):
        """Overwriting a key with pickle works correctly."""
        bucket_name = f"test_pickle_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)

        async with storage:
            s1 = StoredState(id="wf-1", version=1, state=TestState(counter=1, subscriptions=[]))
            s2 = StoredState(id="wf-1", version=2, state=TestState(counter=100, subscriptions=[]))
            await storage.put_state(s1)
            await storage.put_state(s2)

            result = await storage.get_state("wf-1")
            assert result is not None
            assert result.version == 2
            assert result.state.counter == 100

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
        result = await repo.create_new(
            TestCommand(action="create", value=10), "wf-sync-1"
        )
        assert not isinstance(result, Rejection)
        rows = await test_session.execute(
            select(WorkflowSyncLogModel).where(
                WorkflowSyncLogModel.workflow_id == "wf-sync-1"
            )
        )
        log_rows = rows.scalars().all()
        assert len(log_rows) == 1
        assert log_rows[0].events_count == 1

        # process_command: sync_db runs again, second row in same DB
        await repo.process_command("wf-sync-1", TestCommand(action="update", value=5))
        rows2 = await test_session.execute(
            select(WorkflowSyncLogModel).where(
                WorkflowSyncLogModel.workflow_id == "wf-sync-1"
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
        rows_reject = await test_session.execute(
            select(WorkflowSyncLogModel).where(
                WorkflowSyncLogModel.workflow_id == "wf-reject"
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

        result = await repo.create_new(
            TestCommand(action="create", value=10), "wf-adapter-1"
        )
        assert not isinstance(result, Rejection)
        rows_result = await test_session.execute(
            select(WorkflowSyncLogModel).where(
                WorkflowSyncLogModel.workflow_id == "wf-adapter-1"
            )
        )
        rows = rows_result.scalars().all()
        assert len(rows) == 1
        assert rows[0].events_count == 1

    @pytest.mark.asyncio
    async def test_pause_resume_workflow(
        self,
        test_session_maker,
        ephemeral_storage,
        test_event_model,
        test_subscription_model,
        clean_tables,
    ):
        """Test pause and resume workflow lifecycle."""
        repo = AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
        )
        await repo.create_new(TestCommand(action="create", value=1), "wf-lifecycle-1")
        result = await repo.pause_workflow("wf-lifecycle-1", reason="maintenance")
        assert not isinstance(result, Rejection)
        assert result.state.lifecycle == "paused"

        # process_command on paused workflow should reject
        reject = await repo.process_command(
            "wf-lifecycle-1", TestCommand(action="update", value=5)
        )
        assert isinstance(reject, Rejection)
        assert "paused" in reject.msg.lower()

        result2 = await repo.resume_workflow("wf-lifecycle-1")
        assert not isinstance(result2, Rejection)
        assert result2.state.lifecycle == "active"

        # Now process_command should succeed
        result3 = await repo.process_command(
            "wf-lifecycle-1", TestCommand(action="update", value=5)
        )
        assert not isinstance(result3, Rejection)

    @pytest.mark.asyncio
    async def test_cancel_workflow(
        self,
        test_session_maker,
        ephemeral_storage,
        test_event_model,
        test_subscription_model,
        clean_tables,
    ):
        """Test cancel workflow lifecycle."""
        repo = AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
        )
        await repo.create_new(TestCommand(action="create", value=1), "wf-cancel-1")
        result = await repo.cancel_workflow("wf-cancel-1", reason="user requested")
        assert not isinstance(result, Rejection)
        assert result.state.lifecycle == "cancelled"

        # process_command on cancelled workflow should reject
        reject = await repo.process_command(
            "wf-cancel-1", TestCommand(action="update", value=5)
        )
        assert isinstance(reject, Rejection)
        assert "cancelled" in reject.msg.lower()
