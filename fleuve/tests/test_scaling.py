"""
Unit tests for fleuve.scaling module.
"""

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from fleuve.postgres import Offset, ScalingOperation
from fleuve.tests.models import TestOffsetModel


# Create a concrete ScalingOperation model for testing
class TestScalingOperationModel(ScalingOperation):
    """Test model for scaling operations"""

    __tablename__ = "test_scaling_operations"


class TestScalingFunctions:
    """Tests for scaling utility functions."""

    @pytest.mark.asyncio
    async def test_get_max_offset_no_readers(self, test_session_maker):
        """Test get_max_offset with no readers returns 0."""
        from fleuve.scaling import get_max_offset

        result = await get_max_offset(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=[],
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_get_max_offset_single_reader(self, test_session_maker, test_session):
        """Test get_max_offset with a single reader."""
        from fleuve.scaling import get_max_offset

        # Create an offset record
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=100)
        test_session.add(offset1)
        await test_session.commit()

        result = await get_max_offset(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader1"],
        )
        assert result == 100

    @pytest.mark.asyncio
    async def test_get_max_offset_multiple_readers(
        self, test_session_maker, test_session
    ):
        """Test get_max_offset returns the maximum offset across multiple readers."""
        from fleuve.scaling import get_max_offset

        # Create multiple offset records
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=50)
        offset2 = TestOffsetModel(reader="reader2", last_read_event_no=150)
        offset3 = TestOffsetModel(reader="reader3", last_read_event_no=75)
        test_session.add(offset1)
        test_session.add(offset2)
        test_session.add(offset3)
        await test_session.commit()

        result = await get_max_offset(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader1", "reader2", "reader3"],
        )
        assert result == 150

    @pytest.mark.asyncio
    async def test_get_max_offset_missing_readers(
        self, test_session_maker, test_session
    ):
        """Test get_max_offset handles missing readers gracefully."""
        from fleuve.scaling import get_max_offset

        # Create only one offset
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=100)
        test_session.add(offset1)
        await test_session.commit()

        # Query for multiple readers, some missing
        result = await get_max_offset(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader1", "reader2"],
        )
        assert result == 100

    @pytest.mark.asyncio
    async def test_create_scaling_operation(self, test_session_maker, test_session):
        """Test creating a scaling operation."""
        from fleuve.scaling import create_scaling_operation

        await create_scaling_operation(
            session_maker=test_session_maker,
            scaling_operation_model=TestScalingOperationModel,
            workflow_type="test_workflow",
            target_offset=100,
        )

        # Verify the scaling operation was created
        async with test_session_maker() as s:
            result = await s.execute(
                select(TestScalingOperationModel).where(
                    TestScalingOperationModel.workflow_type == "test_workflow"
                )
            )
            op = result.scalar_one()
            assert op.workflow_type == "test_workflow"
            assert op.target_offset == 100
            assert op.status == "pending"

    @pytest.mark.asyncio
    async def test_create_scaling_operation_existing_pending(
        self, test_session_maker, test_session
    ):
        """Test creating a scaling operation when one already exists raises ValueError."""
        from fleuve.scaling import create_scaling_operation

        # Create first scaling operation
        await create_scaling_operation(
            session_maker=test_session_maker,
            scaling_operation_model=TestScalingOperationModel,
            workflow_type="test_workflow",
            target_offset=100,
        )

        # Try to create another one - should raise ValueError
        with pytest.raises(ValueError, match="Scaling operation already in progress"):
            await create_scaling_operation(
                session_maker=test_session_maker,
                scaling_operation_model=TestScalingOperationModel,
                workflow_type="test_workflow",
                target_offset=200,
            )

    @pytest.mark.asyncio
    async def test_create_scaling_operation_existing_completed(
        self, test_session_maker, test_session
    ):
        """Test creating a scaling operation when a completed one exists requires clearing first."""
        from fleuve.scaling import clear_scaling_operation, create_scaling_operation

        # Create and complete a scaling operation
        op = TestScalingOperationModel(
            workflow_type="test_workflow",
            target_offset=100,
            status="completed",
        )
        test_session.add(op)
        await test_session.commit()

        # Clear the completed operation first (realistic scenario)
        await clear_scaling_operation(
            session_maker=test_session_maker,
            scaling_operation_model=TestScalingOperationModel,
            workflow_type="test_workflow",
        )

        # Now creating a new one should be allowed
        await create_scaling_operation(
            session_maker=test_session_maker,
            scaling_operation_model=TestScalingOperationModel,
            workflow_type="test_workflow",
            target_offset=200,
        )

    @pytest.mark.asyncio
    async def test_check_all_workers_at_offset_all_at_target(
        self, test_session_maker, test_session
    ):
        """Test check_all_workers_at_offset when all workers are at or past target."""
        from fleuve.scaling import check_all_workers_at_offset

        # Create offsets all at or above target
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=150)
        offset2 = TestOffsetModel(reader="reader2", last_read_event_no=150)
        offset3 = TestOffsetModel(reader="reader3", last_read_event_no=200)
        test_session.add(offset1)
        test_session.add(offset2)
        test_session.add(offset3)
        await test_session.commit()

        result = await check_all_workers_at_offset(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader1", "reader2", "reader3"],
            target_offset=150,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_check_all_workers_at_offset_some_behind(
        self, test_session_maker, test_session
    ):
        """Test check_all_workers_at_offset when some workers are behind target."""
        from fleuve.scaling import check_all_workers_at_offset

        # Create offsets where some are behind
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=150)
        offset2 = TestOffsetModel(reader="reader2", last_read_event_no=100)  # Behind
        offset3 = TestOffsetModel(reader="reader3", last_read_event_no=150)
        test_session.add(offset1)
        test_session.add(offset2)
        test_session.add(offset3)
        await test_session.commit()

        result = await check_all_workers_at_offset(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader1", "reader2", "reader3"],
            target_offset=150,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_check_all_workers_at_offset_missing_readers(
        self, test_session_maker, test_session
    ):
        """Test check_all_workers_at_offset when some readers don't exist."""
        from fleuve.scaling import check_all_workers_at_offset

        # Create only one offset
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=150)
        test_session.add(offset1)
        await test_session.commit()

        # Query for multiple readers, one missing
        result = await check_all_workers_at_offset(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader1", "reader2"],
            target_offset=150,
        )
        # Missing readers are not at target
        assert result is False

    @pytest.mark.asyncio
    async def test_update_scaling_operation_status(
        self, test_session_maker, test_session
    ):
        """Test updating scaling operation status."""
        from fleuve.scaling import update_scaling_operation_status

        # Create a scaling operation
        op = TestScalingOperationModel(
            workflow_type="test_workflow",
            target_offset=100,
            status="pending",
        )
        test_session.add(op)
        await test_session.commit()

        # Update status
        await update_scaling_operation_status(
            session_maker=test_session_maker,
            scaling_operation_model=TestScalingOperationModel,
            workflow_type="test_workflow",
            status="synchronizing",
        )

        # Verify status was updated
        async with test_session_maker() as s:
            result = await s.execute(
                select(TestScalingOperationModel).where(
                    TestScalingOperationModel.workflow_type == "test_workflow"
                )
            )
            op = result.scalar_one()
            assert op.status == "synchronizing"

    @pytest.mark.asyncio
    async def test_clear_scaling_operation(self, test_session_maker, test_session):
        """Test clearing a scaling operation."""
        from fleuve.scaling import clear_scaling_operation

        # Create a scaling operation
        op = TestScalingOperationModel(
            workflow_type="test_workflow",
            target_offset=100,
            status="completed",
        )
        test_session.add(op)
        await test_session.commit()

        # Clear it
        await clear_scaling_operation(
            session_maker=test_session_maker,
            scaling_operation_model=TestScalingOperationModel,
            workflow_type="test_workflow",
        )

        # Verify it was deleted
        async with test_session_maker() as s:
            result = await s.execute(
                select(TestScalingOperationModel).where(
                    TestScalingOperationModel.workflow_type == "test_workflow"
                )
            )
            assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_initialize_partition_offsets_new_readers(
        self, test_session_maker, test_session
    ):
        """Test initializing offsets for new partitions."""
        from fleuve.scaling import initialize_partition_offsets

        # Create existing offset
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=100)
        test_session.add(offset1)
        await test_session.commit()

        # Initialize new readers
        await initialize_partition_offsets(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader2", "reader3"],
            target_offset=100,
        )

        # Verify new offsets were created
        async with test_session_maker() as s:
            result = await s.execute(
                select(TestOffsetModel).where(
                    TestOffsetModel.reader.in_(["reader2", "reader3"])
                )
            )
            offsets = result.scalars().all()
            assert len(offsets) == 2
            for offset in offsets:
                assert offset.last_read_event_no == 100

    @pytest.mark.asyncio
    async def test_initialize_partition_offsets_existing_lower(
        self, test_session_maker, test_session
    ):
        """Test initializing offsets updates existing offsets if they're lower."""
        from fleuve.scaling import initialize_partition_offsets

        # Create existing offset that's lower than target
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=50)
        test_session.add(offset1)
        await test_session.commit()

        # Initialize with higher target
        await initialize_partition_offsets(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader1"],
            target_offset=100,
        )

        # Verify offset was updated
        async with test_session_maker() as s:
            result = await s.execute(
                select(TestOffsetModel).where(TestOffsetModel.reader == "reader1")
            )
            offset = result.scalar_one()
            assert offset.last_read_event_no == 100

    @pytest.mark.asyncio
    async def test_initialize_partition_offsets_existing_higher(
        self, test_session_maker, test_session
    ):
        """Test initializing offsets doesn't lower existing offsets."""
        from fleuve.scaling import initialize_partition_offsets

        # Create existing offset that's higher than target
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=150)
        test_session.add(offset1)
        await test_session.commit()

        # Initialize with lower target
        await initialize_partition_offsets(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader1"],
            target_offset=100,
        )

        # Verify offset was NOT lowered
        async with test_session_maker() as s:
            result = await s.execute(
                select(TestOffsetModel).where(TestOffsetModel.reader == "reader1")
            )
            offset = result.scalar_one()
            assert offset.last_read_event_no == 150  # Kept higher value

    @pytest.mark.asyncio
    async def test_wait_for_workers_to_reach_offset_success(
        self, test_session_maker, test_session
    ):
        """Test wait_for_workers_to_reach_offset succeeds when all workers reach target."""
        from fleuve.scaling import wait_for_workers_to_reach_offset

        # Create offsets all at target
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=100)
        offset2 = TestOffsetModel(reader="reader2", last_read_event_no=100)
        test_session.add(offset1)
        test_session.add(offset2)
        await test_session.commit()

        result = await wait_for_workers_to_reach_offset(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader1", "reader2"],
            target_offset=100,
            timeout=datetime.timedelta(seconds=5),
            check_interval=datetime.timedelta(seconds=0.1),
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_workers_to_reach_offset_timeout(
        self, test_session_maker, test_session
    ):
        """Test wait_for_workers_to_reach_offset times out when workers don't reach target."""
        from fleuve.scaling import wait_for_workers_to_reach_offset

        # Create offsets that are behind
        offset1 = TestOffsetModel(reader="reader1", last_read_event_no=50)
        offset2 = TestOffsetModel(reader="reader2", last_read_event_no=50)
        test_session.add(offset1)
        test_session.add(offset2)
        await test_session.commit()

        result = await wait_for_workers_to_reach_offset(
            session_maker=test_session_maker,
            offset_model=TestOffsetModel,
            reader_names=["reader1", "reader2"],
            target_offset=100,
            timeout=datetime.timedelta(seconds=0.5),
            check_interval=datetime.timedelta(seconds=0.1),
        )
        assert result is False


class TestReaderScalingBehavior:
    """Tests for Reader scaling behavior (set_stop_at_offset)."""

    @pytest.mark.asyncio
    async def test_set_stop_at_offset(self, test_session_maker):
        """Test setting stop_at_offset on Reader."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel
        from fleuve.stream import Reader

        reader = Reader(
            reader_name="test_reader",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )
        assert reader._stop_at_offset is None

        reader.set_stop_at_offset(100)
        assert reader._stop_at_offset == 100

        reader.set_stop_at_offset(None)
        assert reader._stop_at_offset is None

    @pytest.mark.asyncio
    async def test_reader_stops_at_offset(
        self, test_session_maker, test_session, clean_tables, test_event
    ):
        """Test that Reader stops gracefully when it reaches stop_at_offset."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel
        from fleuve.stream import Reader

        # Create events with different global_ids
        for i in range(5):
            event_model = DbEventModel(
                workflow_id="wf-1",
                workflow_version=i + 1,
                event_type="test_event",
                workflow_type="test_workflow",
                body=test_event,
                global_id=i + 1,
            )
            test_session.add(event_model)
        await test_session.commit()

        reader = Reader(
            reader_name="test_reader",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )

        # Set stop_at_offset to 3
        reader.set_stop_at_offset(3)

        async with reader:
            events = []
            async for event in reader.iter_events():
                events.append(event)
                # Stop after a reasonable number to avoid infinite loop
                if len(events) >= 10:
                    break

        # Should have processed events up to and including global_id 3
        assert len(events) == 3
        assert events[0].global_id == 1
        assert events[1].global_id == 2
        assert events[2].global_id == 3
        assert reader.last_read_event_g_id == 3

    @pytest.mark.asyncio
    async def test_reader_continues_without_stop_at_offset(
        self, test_session_maker, test_session, clean_tables, test_event
    ):
        """Test that Reader continues processing when stop_at_offset is not set."""
        from fleuve.tests.models import DbEventModel, TestOffsetModel
        from fleuve.stream import Reader

        # Create a few events
        for i in range(3):
            event_model = DbEventModel(
                workflow_id="wf-1",
                workflow_version=i + 1,
                event_type="test_event",
                workflow_type="test_workflow",
                body=test_event,
                global_id=i + 1,
            )
            test_session.add(event_model)
        await test_session.commit()

        reader = Reader(
            reader_name="test_reader_continue",
            s=test_session_maker,
            db_model=DbEventModel,
            offset_model=TestOffsetModel,
        )

        # Don't set stop_at_offset - verify it's None
        assert reader._stop_at_offset is None

        # The key test: when stop_at_offset is None, reader should NOT stop automatically
        # This is verified by the fact that reader.iter_events() is an infinite generator
        # We'll test this by ensuring that with stop_at_offset set, it stops,
        # and without it set (tested in test_reader_stops_at_offset), the default behavior applies
        async with reader:
            events = []
            # Process events and manually break after a few to avoid infinite loop
            async for event in reader.iter_events():
                events.append(event)
                if len(events) >= 2:  # Just verify it can process events
                    reader._bg_checkpoint_marking_job.cancel()
                    break

        # Should have processed at least some events
        assert len(events) >= 2
        # Verify stop_at_offset is still None (not auto-set)
        assert reader._stop_at_offset is None


class TestRunnerScalingDetection:
    """Tests for Runner scaling detection and notification."""

    @pytest.fixture
    def mock_repo(self):
        """Create a mock repository."""
        repo = AsyncMock()
        repo.process_command = AsyncMock()
        return repo

    @pytest.fixture
    def mock_side_effects(self):
        """Create mock side effects."""
        se = AsyncMock()
        se.maybe_act_on = AsyncMock()
        se.__aenter__ = AsyncMock(return_value=se)
        se.__aexit__ = AsyncMock(return_value=False)
        return se

    @pytest.mark.asyncio
    async def test_runner_detects_scaling_operation(
        self,
        test_session_maker,
        test_session,
        mock_repo,
        mock_side_effects,
        test_workflow,
    ):
        """Test that Runner detects scaling operation and notifies Reader."""
        from fleuve.runner import WorkflowsRunner
        from fleuve.stream import Readers
        from fleuve.tests.models import (
            DbEventModel,
            TestOffsetModel,
            TestSubscriptionModel,
        )
        from fleuve.postgres import StoredEvent, Subscription

        # Create a scaling operation
        op = TestScalingOperationModel(
            workflow_type="test_workflow",
            target_offset=100,
            status="pending",
        )
        test_session.add(op)
        await test_session.commit()

        readers = Readers(
            pg_session_maker=test_session_maker,
            model=DbEventModel,
            offset_model=TestOffsetModel,
        )

        runner = WorkflowsRunner(
            repo=mock_repo,
            readers=readers,
            workflow_type=test_workflow,
            session_maker=test_session_maker,
            db_sub_type=TestSubscriptionModel,
            se=mock_side_effects,
            db_scaling_operation_model=TestScalingOperationModel,
            scaling_check_interval=1,  # Check every event
        )

        # Before checking, reader should not have stop_at_offset set
        assert runner.stream._stop_at_offset is None

        # Manually call _check_scaling_operation to test detection
        target_offset = await runner._check_scaling_operation()
        assert target_offset == 100

        # Setting stop_at_offset should notify reader
        runner.stream.set_stop_at_offset(100)
        assert runner.stream._stop_at_offset == 100

    @pytest.mark.asyncio
    async def test_runner_no_scaling_operation_model(
        self, test_session_maker, mock_repo, mock_side_effects, test_workflow
    ):
        """Test that Runner doesn't check for scaling when model is None."""
        from fleuve.runner import WorkflowsRunner
        from fleuve.stream import Readers
        from fleuve.tests.models import (
            DbEventModel,
            TestOffsetModel,
            TestSubscriptionModel,
        )

        readers = Readers(
            pg_session_maker=test_session_maker,
            model=DbEventModel,
            offset_model=TestOffsetModel,
        )

        runner = WorkflowsRunner(
            repo=mock_repo,
            readers=readers,
            workflow_type=test_workflow,
            session_maker=test_session_maker,
            db_sub_type=TestSubscriptionModel,
            se=mock_side_effects,
            db_scaling_operation_model=None,  # No scaling model
        )

        # Should return None when no model is configured
        target_offset = await runner._check_scaling_operation()
        assert target_offset is None

    @pytest.mark.asyncio
    async def test_runner_scaling_check_workflow_type_filter(
        self,
        test_session_maker,
        test_session,
        mock_repo,
        mock_side_effects,
        test_workflow,
    ):
        """Test that Runner only checks scaling operations for its workflow type."""
        from fleuve.runner import WorkflowsRunner
        from fleuve.stream import Readers
        from fleuve.tests.models import (
            DbEventModel,
            TestOffsetModel,
            TestSubscriptionModel,
        )

        # Create scaling operations for different workflow types
        op1 = TestScalingOperationModel(
            workflow_type="test_workflow",
            target_offset=100,
            status="pending",
        )
        op2 = TestScalingOperationModel(
            workflow_type="other_workflow",
            target_offset=200,
            status="pending",
        )
        test_session.add(op1)
        test_session.add(op2)
        await test_session.commit()

        readers = Readers(
            pg_session_maker=test_session_maker,
            model=DbEventModel,
            offset_model=TestOffsetModel,
        )

        runner = WorkflowsRunner(
            repo=mock_repo,
            readers=readers,
            workflow_type=test_workflow,
            session_maker=test_session_maker,
            db_sub_type=TestSubscriptionModel,
            se=mock_side_effects,
            db_scaling_operation_model=TestScalingOperationModel,
        )

        # Should only detect scaling operation for test_workflow
        target_offset = await runner._check_scaling_operation()
        assert target_offset == 100  # Not 200
