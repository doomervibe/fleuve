"""
Unit tests for les.actions module.
"""
import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleuve.actions import ActionExecutor, ActionStatus
from fleuve.model import ActionContext, Adapter, RetryPolicy
from fleuve.stream import ConsumedEvent


class MockAdapter(Adapter):
    """Test adapter implementation."""

    def __init__(self, should_fail=False, return_cmd=None):
        self.should_fail = should_fail
        self.return_cmd = return_cmd
        self.called_events = []

    async def act_on(self, event, context=None):
        self.called_events.append((event, context))
        if self.should_fail:
            raise ValueError("Test failure")
        if self.return_cmd is not None:
            yield self.return_cmd

    def to_be_act_on(self, event):
        return True


class TestActionExecutor:
    """Tests for ActionExecutor class using real database."""

    @pytest.fixture
    def mock_repo(self):
        """Create a mock AsyncRepo for testing."""
        from unittest.mock import AsyncMock
        repo = AsyncMock()
        repo.process_command = AsyncMock(return_value=None)
        return repo

    @pytest.fixture
    def action_executor(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        mock_repo,
    ):
        """Create an ActionExecutor instance with real database."""
        adapter = MockAdapter(should_fail=False)
        return ActionExecutor(
            session_maker=test_session_maker,
            adapter=adapter,
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
            max_retries=3,
        )

    def test_action_executor_initialization(self, action_executor):
        """Test action executor initialization."""
        assert action_executor._max_retries == 3
        assert not action_executor._running
        assert action_executor._running_actions == {}

    def test_to_be_act_on(self, action_executor):
        """Test to_be_act_on method."""
        from pydantic import BaseModel

        class TestEvent(BaseModel):
            type: str = "test"

        event = TestEvent()
        assert action_executor.to_be_act_on(ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=event,
            global_id=1,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        ))

    @pytest.mark.asyncio
    async def test_start_stop(self, action_executor):
        """Test starting and stopping action executor."""
        await action_executor.start()
        assert action_executor._running
        assert action_executor._recovery_task is not None

        await action_executor.stop()
        assert not action_executor._running
        if action_executor._recovery_task:
            assert action_executor._recovery_task.cancelled()

    @pytest.mark.asyncio
    async def test_context_manager(self, action_executor):
        """Test action executor as async context manager."""
        async with action_executor:
            assert action_executor._running
        assert not action_executor._running

    @pytest.mark.asyncio
    async def test_execute_action_already_running(
        self,
        action_executor,
        mock_session_maker,
    ):
        """Test that executing an already running action is ignored."""
        from pydantic import BaseModel

        class TestEvent(BaseModel):
            type: str = "test"

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(),
            global_id=1,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )

        # Mark as running
        action_executor._running_actions[(event.agg_id, event.event_no)] = asyncio.create_task(
            asyncio.sleep(1)
        )

        await action_executor.execute_action(event)

        # Should not create another task
        assert len(action_executor._running_actions) == 1

    @pytest.mark.asyncio
    async def test_execute_action_already_completed(
        self,
        action_executor,
        test_session,
        clean_tables,
    ):
        """Test that already completed actions are skipped."""
        from pydantic import BaseModel
        from fleuve.tests.conftest import TestEvent

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(value=10),
            global_id=1,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )

        # Create a completed activity in database
        activity = action_executor._db_activity_model(
            workflow_id="wf-1",
            event_number=1,
            status=ActionStatus.COMPLETED,
            max_retries=3,
        )
        test_session.add(activity)
        await test_session.commit()

        await action_executor.execute_action(event)

        # Should not add to running actions
        assert (event.workflow_id, event.event_no) not in action_executor._running_actions

    @pytest.mark.asyncio
    async def test_execute_action_success(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test successful action execution."""
        from pydantic import BaseModel
        from fleuve.tests.conftest import TestEvent

        class TestCmd(BaseModel):
            action: str = "test"

        adapter = MockAdapter(return_cmd=TestCmd())
        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=adapter,
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
        )

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(value=10),
            global_id=1,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )

        await executor.execute_action(event)

        # Verify adapter was called
        assert len(adapter.called_events) > 0
        
        # Verify activity was created in database
        from sqlalchemy import select
        async with test_session_maker() as s:
            activity = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            assert activity is not None
            assert activity.status == ActionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_command_processed_before_marking_completed(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test that command is processed before action is marked as completed.
        
        If command processing fails, the action should NOT be marked as completed,
        ensuring that on recovery, the command will be processed again.
        """
        from pydantic import BaseModel
        from fleuve.tests.conftest import TestEvent

        class TestCmd(BaseModel):
            action: str = "test"

        adapter = MockAdapter(return_cmd=TestCmd())
        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=adapter,
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
        )

        # Make process_command fail
        async def failing_process_command(workflow_id: str, cmd):
            raise ValueError("Command processing failed")

        mock_repo.process_command = failing_process_command

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(value=10),
            global_id=1,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )

        # Executor retries then marks as failed; it does not re-raise
        await executor.execute_action(event)

        # Verify activity was NOT marked as completed (so on recovery the command will be processed again)
        from sqlalchemy import select
        async with test_session_maker() as s:
            activity = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            assert activity is not None
            assert activity.status == ActionStatus.FAILED

    @pytest.mark.asyncio
    async def test_action_with_timeout(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test action execution with timeout."""
        from fleuve.tests.conftest import TestEvent

        class SlowAdapter(Adapter):
            async def act_on(self, event, context=None):
                await asyncio.sleep(2)  # Longer than timeout
                if False:
                    yield  # async generator

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=SlowAdapter(),
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
            action_timeout=datetime.timedelta(seconds=0.1),
        )

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(value=10),
            global_id=1,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )

        await executor.execute_action(event)

        # Verify timeout occurred - activity should be in failed/retrying status after timeout
        from sqlalchemy import select
        async with test_session_maker() as s:
            activity = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            assert activity is not None
            # After timeout and retries, should be failed
            assert activity.status in [ActionStatus.FAILED, ActionStatus.RETRYING]

    @pytest.mark.asyncio
    async def test_checkpoint_persistence_during_execution(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test that checkpoints yielded with save_now=True persist immediately."""
        from fleuve.model import CheckpointYield
        from fleuve.tests.conftest import TestEvent

        class CheckpointAdapter(MockAdapter):
            async def act_on(self, event, context=None):
                yield CheckpointYield(data={"step": 1, "progress": 50}, save_now=True)

        adapter = CheckpointAdapter()
        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=adapter,
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
        )

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(value=10),
            global_id=1,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )

        await executor.execute_action(event)

        from sqlalchemy import select
        async with test_session_maker() as s:
            activity = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            assert activity is not None
            assert activity.checkpoint == {"step": 1, "progress": 50}

    @pytest.mark.asyncio
    async def test_act_on_yields_checkpoint_save_now_and_at_end(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test that act_on can yield CheckpointYield with save_now True (persist now) vs False (persist at end)."""
        from fleuve.model import Adapter, CheckpointYield
        from fleuve.tests.conftest import TestEvent

        class CheckpointYieldAdapter(Adapter):
            async def act_on(self, event, context=None):
                yield CheckpointYield(data={"step1": 1}, save_now=False)
                yield CheckpointYield(data={"step2": 2}, save_now=True)
                yield CheckpointYield(data={"step3": 3}, save_now=False)

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=CheckpointYieldAdapter(),
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
        )

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(value=10),
            global_id=1,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )

        await executor.execute_action(event)

        from sqlalchemy import select
        async with test_session_maker() as s:
            activity = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            assert activity is not None
            assert activity.checkpoint == {"step1": 1, "step2": 2, "step3": 3}
