"""Tests for automatic state snapshots and event truncation."""

import datetime
import uuid

import pytest
from nats.aio.client import Client as NATS
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fleuve.model import Rejection
from fleuve.repo import AsyncRepo, EuphStorageNATS, StoredState
from fleuve.truncation import TruncationService

from fleuve.tests.conftest import TestCommand, TestEvent, TestState, TestWorkflow


class TestSnapshotCreation:
    """Tests that snapshots are created at the correct intervals."""

    @pytest.fixture
    async def ephemeral_storage(self, nats_client: NATS):
        bucket_name = f"test_snap_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)
        await storage.__aenter__()
        yield storage
        await storage.__aexit__(None, None, None)
        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

    @pytest.fixture
    def repo_with_snapshots(
        self,
        test_session_maker,
        ephemeral_storage,
        test_event_model,
        test_subscription_model,
        test_snapshot_model,
    ):
        return AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
            db_snapshot_model=test_snapshot_model,
            snapshot_interval=3,
        )

    @pytest.fixture
    def repo_no_snapshots(
        self,
        test_session_maker,
        ephemeral_storage,
        test_event_model,
        test_subscription_model,
    ):
        return AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
        )

    @pytest.mark.asyncio
    async def test_snapshot_created_at_interval(
        self,
        repo_with_snapshots,
        test_session,
        test_snapshot_model,
        clean_tables,
    ):
        """Snapshot is created when version hits the interval (every 3 events)."""
        repo = repo_with_snapshots

        await repo.create_new(TestCommand(action="create", value=1), "wf-1")
        # version=1: no snapshot (1 % 3 != 0)

        await repo.process_command("wf-1", TestCommand(action="update", value=2))
        # version=2: no snapshot

        await repo.process_command("wf-1", TestCommand(action="update", value=3))
        # version=3: snapshot! (3 % 3 == 0)

        snap = await test_session.scalar(
            select(test_snapshot_model).where(test_snapshot_model.workflow_id == "wf-1")
        )
        assert snap is not None
        assert snap.version == 3
        assert snap.state.counter == 6  # 1+2+3
        assert snap.workflow_type == "test_workflow"

    @pytest.mark.asyncio
    async def test_no_snapshot_before_interval(
        self,
        repo_with_snapshots,
        test_session,
        test_snapshot_model,
        clean_tables,
    ):
        """No snapshot before the interval is reached."""
        repo = repo_with_snapshots

        await repo.create_new(TestCommand(action="create", value=1), "wf-1")
        await repo.process_command("wf-1", TestCommand(action="update", value=2))

        snap = await test_session.scalar(
            select(test_snapshot_model).where(test_snapshot_model.workflow_id == "wf-1")
        )
        assert snap is None

    @pytest.mark.asyncio
    async def test_snapshot_upserted_on_second_interval(
        self,
        repo_with_snapshots,
        test_session,
        test_snapshot_model,
        clean_tables,
    ):
        """Snapshot is updated (upserted) when the next interval is reached."""
        repo = repo_with_snapshots

        await repo.create_new(TestCommand(action="create", value=1), "wf-1")
        for i in range(2, 7):
            await repo.process_command("wf-1", TestCommand(action="update", value=i))
        # version 6: second snapshot (6 % 3 == 0)

        snap = await test_session.scalar(
            select(test_snapshot_model).where(test_snapshot_model.workflow_id == "wf-1")
        )
        assert snap is not None
        assert snap.version == 6
        assert snap.state.counter == 21  # 1+2+3+4+5+6

        # Only one row (upsert, not insert)
        count = await test_session.scalar(
            select(func.count()).select_from(test_snapshot_model)
        )
        assert count == 1

    @pytest.mark.asyncio
    async def test_no_snapshot_when_disabled(
        self,
        repo_no_snapshots,
        test_session,
        test_snapshot_model,
        clean_tables,
    ):
        """No snapshots created when snapshot_interval is 0."""
        repo = repo_no_snapshots

        await repo.create_new(TestCommand(action="create", value=1), "wf-1")
        for i in range(2, 10):
            await repo.process_command("wf-1", TestCommand(action="update", value=i))

        count = await test_session.scalar(
            select(func.count()).select_from(test_snapshot_model)
        )
        assert count == 0


class TestSnapshotBasedLoadState:
    """Tests that load_state uses snapshots to skip replaying old events."""

    @pytest.fixture
    async def ephemeral_storage(self, nats_client: NATS):
        bucket_name = f"test_snap_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)
        await storage.__aenter__()
        yield storage
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
        test_snapshot_model,
    ):
        return AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
            db_snapshot_model=test_snapshot_model,
            snapshot_interval=3,
        )

    @pytest.mark.asyncio
    async def test_load_state_uses_snapshot(
        self,
        repo,
        test_session,
        test_event_model,
        clean_tables,
    ):
        """load_state reconstructs correctly when a snapshot exists."""
        await repo.create_new(TestCommand(action="create", value=1), "wf-1")
        for i in range(2, 6):
            await repo.process_command("wf-1", TestCommand(action="update", value=i))
        # version=5, snapshot at version=3

        state = await repo.load_state(test_session, "wf-1")
        assert state is not None
        assert state.version == 5
        assert state.state.counter == 15  # 1+2+3+4+5

    @pytest.mark.asyncio
    async def test_load_state_at_version_uses_snapshot(
        self,
        repo,
        test_session,
        clean_tables,
    ):
        """load_state with at_version uses the snapshot if it's <= at_version."""
        await repo.create_new(TestCommand(action="create", value=1), "wf-1")
        for i in range(2, 6):
            await repo.process_command("wf-1", TestCommand(action="update", value=i))
        # snapshot at v3 (counter=6)

        state = await repo.load_state(test_session, "wf-1", at_version=4)
        assert state is not None
        assert state.version == 4
        assert state.state.counter == 10  # 1+2+3+4

    @pytest.mark.asyncio
    async def test_load_state_at_version_before_snapshot(
        self,
        repo,
        test_session,
        clean_tables,
    ):
        """at_version before the snapshot falls back to full replay."""
        await repo.create_new(TestCommand(action="create", value=1), "wf-1")
        for i in range(2, 6):
            await repo.process_command("wf-1", TestCommand(action="update", value=i))
        # snapshot at v3

        state = await repo.load_state(test_session, "wf-1", at_version=2)
        assert state is not None
        assert state.version == 2
        assert state.state.counter == 3  # 1+2

    @pytest.mark.asyncio
    async def test_load_state_works_after_truncation(
        self,
        repo,
        test_session,
        test_event_model,
        clean_tables,
    ):
        """State is correctly reconstructed even after old events are deleted."""
        await repo.create_new(TestCommand(action="create", value=1), "wf-1")
        for i in range(2, 6):
            await repo.process_command("wf-1", TestCommand(action="update", value=i))
        # snapshot at v3 (counter=6), events v1-v5

        # Simulate truncation: delete events before the snapshot
        from sqlalchemy import delete

        await test_session.execute(
            delete(test_event_model).where(
                test_event_model.workflow_id == "wf-1",
                test_event_model.workflow_version < 3,
            )
        )
        await test_session.commit()

        state = await repo.load_state(test_session, "wf-1")
        assert state is not None
        assert state.version == 5
        assert state.state.counter == 15  # snapshot(6) + 4 + 5


class TestTruncationService:
    """Tests that TruncationService safely deletes old events."""

    @pytest.fixture
    async def ephemeral_storage(self, nats_client: NATS):
        bucket_name = f"test_trunc_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(c=nats_client, bucket=bucket_name, s=TestState)
        await storage.__aenter__()
        yield storage
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
        test_snapshot_model,
    ):
        return AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
            db_snapshot_model=test_snapshot_model,
            snapshot_interval=3,
        )

    async def _setup_workflow_with_events(
        self, repo, n_events: int, wf_id: str = "wf-1"
    ):
        """Helper: create a workflow and add events up to n_events total."""
        await repo.create_new(TestCommand(action="create", value=1), wf_id)
        for i in range(2, n_events + 1):
            await repo.process_command(wf_id, TestCommand(action="update", value=i))

    async def _mark_all_pushed(self, session, event_model):
        await session.execute(update(event_model).values(pushed=True))
        await session.commit()

    async def _set_reader_offset(self, session, offset_model, offset: int):
        await session.execute(
            insert(offset_model).values(reader="test_reader", last_read_event_no=offset)
        )
        await session.commit()

    async def _backdate_events(self, session, event_model, days: int):
        past = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(
            days=days
        )
        await session.execute(update(event_model).values(at=past))
        await session.commit()

    async def _count_events(self, session, event_model, wf_id: str) -> int:
        return await session.scalar(
            select(func.count())
            .select_from(event_model)
            .where(event_model.workflow_id == wf_id)
        )

    @pytest.mark.asyncio
    async def test_truncation_deletes_old_covered_events(
        self,
        repo,
        test_session_maker,
        test_session,
        test_event_model,
        test_snapshot_model,
        clean_tables,
    ):
        """Events before the snapshot version are deleted when all conditions are met."""
        from fleuve.tests.models import TestOffsetModel

        await self._setup_workflow_with_events(repo, 6)
        # snapshot at v3 and v6

        await self._mark_all_pushed(test_session, test_event_model)
        max_gid = await test_session.scalar(
            select(func.max(test_event_model.global_id))
        )
        await self._set_reader_offset(test_session, TestOffsetModel, max_gid + 1)
        await self._backdate_events(test_session, test_event_model, days=10)

        svc = TruncationService(
            session_maker=test_session_maker,
            event_model=test_event_model,
            snapshot_model=test_snapshot_model,
            offset_model=TestOffsetModel,
            workflow_type="test_workflow",
            min_retention=datetime.timedelta(days=7),
            batch_size=1000,
            check_interval=datetime.timedelta(seconds=1),
        )

        deleted = await svc._truncate_events()
        assert deleted > 0

        remaining = await self._count_events(test_session, test_event_model, "wf-1")
        assert remaining < 6

    @pytest.mark.asyncio
    async def test_truncation_preserves_unpushed_events(
        self,
        repo,
        test_session_maker,
        test_session,
        test_event_model,
        test_snapshot_model,
        clean_tables,
    ):
        """Unpushed events are never truncated."""
        from fleuve.tests.models import TestOffsetModel

        await self._setup_workflow_with_events(repo, 6)
        # pushed=False by default -- don't mark as pushed

        max_gid = await test_session.scalar(
            select(func.max(test_event_model.global_id))
        )
        await self._set_reader_offset(test_session, TestOffsetModel, max_gid + 1)
        await self._backdate_events(test_session, test_event_model, days=10)

        svc = TruncationService(
            session_maker=test_session_maker,
            event_model=test_event_model,
            snapshot_model=test_snapshot_model,
            offset_model=TestOffsetModel,
            workflow_type="test_workflow",
            min_retention=datetime.timedelta(days=7),
        )

        deleted = await svc._truncate_events()
        assert deleted == 0

        remaining = await self._count_events(test_session, test_event_model, "wf-1")
        assert remaining == 6

    @pytest.mark.asyncio
    async def test_truncation_respects_reader_offset(
        self,
        repo,
        test_session_maker,
        test_session,
        test_event_model,
        test_snapshot_model,
        clean_tables,
    ):
        """Events are not truncated if a reader hasn't processed them yet."""
        from fleuve.tests.models import TestOffsetModel

        await self._setup_workflow_with_events(repo, 6)
        await self._mark_all_pushed(test_session, test_event_model)
        await self._backdate_events(test_session, test_event_model, days=10)

        # Reader offset at 0 -- hasn't read any events
        await self._set_reader_offset(test_session, TestOffsetModel, 0)

        svc = TruncationService(
            session_maker=test_session_maker,
            event_model=test_event_model,
            snapshot_model=test_snapshot_model,
            offset_model=TestOffsetModel,
            workflow_type="test_workflow",
            min_retention=datetime.timedelta(days=7),
        )

        deleted = await svc._truncate_events()
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_truncation_respects_min_retention(
        self,
        repo,
        test_session_maker,
        test_session,
        test_event_model,
        test_snapshot_model,
        clean_tables,
    ):
        """Events younger than min_retention are not truncated."""
        from fleuve.tests.models import TestOffsetModel

        await self._setup_workflow_with_events(repo, 6)
        await self._mark_all_pushed(test_session, test_event_model)
        # Events are fresh (just created) -- don't backdate

        max_gid = await test_session.scalar(
            select(func.max(test_event_model.global_id))
        )
        await self._set_reader_offset(test_session, TestOffsetModel, max_gid + 1)

        svc = TruncationService(
            session_maker=test_session_maker,
            event_model=test_event_model,
            snapshot_model=test_snapshot_model,
            offset_model=TestOffsetModel,
            workflow_type="test_workflow",
            min_retention=datetime.timedelta(days=7),
        )

        deleted = await svc._truncate_events()
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_no_truncation_without_snapshot(
        self,
        test_session_maker,
        ephemeral_storage,
        test_session,
        test_event_model,
        test_subscription_model,
        test_snapshot_model,
        clean_tables,
    ):
        """Workflows without a snapshot never have events truncated."""
        from fleuve.tests.models import TestOffsetModel

        repo_no_snap = AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
        )

        await repo_no_snap.create_new(TestCommand(action="create", value=1), "wf-1")
        for i in range(2, 7):
            await repo_no_snap.process_command(
                "wf-1", TestCommand(action="update", value=i)
            )

        await self._mark_all_pushed(test_session, test_event_model)
        max_gid = await test_session.scalar(
            select(func.max(test_event_model.global_id))
        )
        await self._set_reader_offset(test_session, TestOffsetModel, max_gid + 1)
        await self._backdate_events(test_session, test_event_model, days=10)

        svc = TruncationService(
            session_maker=test_session_maker,
            event_model=test_event_model,
            snapshot_model=test_snapshot_model,
            offset_model=TestOffsetModel,
            workflow_type="test_workflow",
            min_retention=datetime.timedelta(days=7),
        )

        deleted = await svc._truncate_events()
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_state_intact_after_truncation(
        self,
        repo,
        test_session_maker,
        test_session,
        test_event_model,
        test_snapshot_model,
        clean_tables,
    ):
        """State reconstruction returns correct result after truncation."""
        from fleuve.tests.models import TestOffsetModel

        await self._setup_workflow_with_events(repo, 6)
        await self._mark_all_pushed(test_session, test_event_model)
        max_gid = await test_session.scalar(
            select(func.max(test_event_model.global_id))
        )
        await self._set_reader_offset(test_session, TestOffsetModel, max_gid + 1)
        await self._backdate_events(test_session, test_event_model, days=10)

        svc = TruncationService(
            session_maker=test_session_maker,
            event_model=test_event_model,
            snapshot_model=test_snapshot_model,
            offset_model=TestOffsetModel,
            workflow_type="test_workflow",
            min_retention=datetime.timedelta(days=7),
        )

        await svc._truncate_events()

        state = await repo.load_state(test_session, "wf-1")
        assert state is not None
        assert state.state.counter == 21  # 1+2+3+4+5+6
        assert state.version == 6
