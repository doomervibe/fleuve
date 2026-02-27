"""
Unit tests for fleuve.actions module.
"""

import asyncio
import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nats.aio.client import Client as NATS

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
        await storage.__aenter__()
        yield storage
        await storage.__aexit__(None, None, None)
        try:
            js = nats_client.jetstream()
            await js.delete_key_value(bucket_name)
        except Exception:
            pass

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

    async def _wait_for_executor(self, executor: ActionExecutor) -> None:
        while True:
            tasks = list(executor._running_actions.values())
            if not tasks:
                break
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0)

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
        assert action_executor.to_be_act_on(
            ConsumedEvent(
                workflow_id="wf-1",
                event_no=1,
                event=event,
                global_id=1,
                at=datetime.datetime.now(datetime.timezone.utc),
                workflow_type="test_workflow",
            )
        )

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
        action_executor._running_actions[(event.agg_id, event.event_no)] = (
            asyncio.create_task(asyncio.sleep(1))
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
        await self._wait_for_executor(action_executor)

        # Should not add to running actions
        assert (
            event.workflow_id,
            event.event_no,
        ) not in action_executor._running_actions

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
        await self._wait_for_executor(executor)

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
        await self._wait_for_executor(executor)

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
    async def test_retry_policy_and_checkpoint_updates_on_failure(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Adapter changes to retry policy and checkpoint during failure should affect current retry loop."""
        from sqlalchemy import select

        from fleuve.tests.conftest import TestEvent

        class PolicyAdjustingAdapter(Adapter):
            def __init__(self):
                self.calls = 0

            async def act_on(self, event, context=None):
                self.calls += 1
                context.checkpoint["attempt"] = self.calls
                context.retry_policy = context.retry_policy.model_copy(
                    update={"max_retries": 0}
                )
                if context.retry_count < 0:
                    yield  # pragma: no cover
                raise ValueError("boom")

            def to_be_act_on(self, event):
                return True

        adapter = PolicyAdjustingAdapter()
        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=adapter,
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
            max_retries=3,
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
        await self._wait_for_executor(executor)

        assert adapter.calls == 1

        async with test_session_maker() as s:
            activity = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            assert activity is not None
            assert activity.status == ActionStatus.FAILED
            assert activity.retry_policy.max_retries == 0
            assert activity.checkpoint == {"attempt": 1}

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
        await self._wait_for_executor(executor)

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
        await self._wait_for_executor(executor)

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
        await self._wait_for_executor(executor)

        from sqlalchemy import select

        async with test_session_maker() as s:
            activity = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            assert activity is not None
            assert activity.checkpoint == {"step1": 1, "step2": 2, "step3": 3}

    @pytest.mark.asyncio
    async def test_action_timeout_yield_completes_within_timeout(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test that yielding ActionTimeout applies wait_for to the remainder; action completing within timeout succeeds."""
        from fleuve.model import ActionTimeout
        from fleuve.tests.conftest import TestCommand, TestEvent

        class ActionTimeoutAdapter(Adapter):
            async def act_on(self, event, context=None):
                yield TestCommand(action="before", value=1)
                yield ActionTimeout(seconds=1.0)
                # Remainder completes quickly
                yield TestCommand(action="after", value=2)

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=ActionTimeoutAdapter(),
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
        await self._wait_for_executor(executor)

        assert mock_repo.process_command.call_count == 2
        mock_repo.process_command.assert_any_call(
            "wf-1", TestCommand(action="before", value=1)
        )
        mock_repo.process_command.assert_any_call(
            "wf-1", TestCommand(action="after", value=2)
        )

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
    async def test_action_timeout_yield_times_out(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test that when remainder of action exceeds ActionTimeout.seconds, TimeoutError is raised and action fails after retries."""
        from fleuve.model import ActionTimeout
        from fleuve.tests.conftest import TestEvent

        class SlowAfterTimeoutAdapter(Adapter):
            async def act_on(self, event, context=None):
                yield ActionTimeout(seconds=0.05)
                await asyncio.sleep(1.0)  # Longer than 0.05s timeout

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=SlowAfterTimeoutAdapter(),
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
            max_retries=1,
        )

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(value=10),
            global_id=1,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )

        # Cap total time so test fails fast if it hangs (retries + backoff can take a few seconds)
        await executor.execute_action(event)
        await asyncio.wait_for(self._wait_for_executor(executor), timeout=15.0)

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
    async def test_action_timeout_yield_with_command_after(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test that yielding ActionTimeout then a command processes the command under the timeout."""
        from fleuve.model import ActionTimeout
        from fleuve.tests.conftest import TestCommand, TestEvent

        class TimeoutThenCommandAdapter(Adapter):
            async def act_on(self, event, context=None):
                yield ActionTimeout(seconds=2.0)
                yield TestCommand(action="after_timeout", value=42)

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=TimeoutThenCommandAdapter(),
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
        await self._wait_for_executor(executor)

        mock_repo.process_command.assert_called_once_with(
            "wf-1", TestCommand(action="after_timeout", value=42)
        )

    @pytest.mark.asyncio
    async def test_action_timeout_yield_with_checkpoint_after(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test that ActionTimeout can be followed by CheckpointYield; both are handled under the timeout."""
        from fleuve.model import ActionTimeout, CheckpointYield
        from fleuve.tests.conftest import TestEvent

        class TimeoutThenCheckpointAdapter(Adapter):
            async def act_on(self, event, context=None):
                yield ActionTimeout(seconds=1.0)
                yield CheckpointYield(data={"after_timeout": True}, save_now=True)

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=TimeoutThenCheckpointAdapter(),
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
        await self._wait_for_executor(executor)

        from sqlalchemy import select

        async with test_session_maker() as s:
            activity = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            assert activity is not None
            assert activity.status == ActionStatus.COMPLETED
            assert activity.checkpoint == {"after_timeout": True}

    @pytest.mark.asyncio
    async def test_cancel_workflow_actions_marks_pending_as_cancelled(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test that cancel_workflow_actions marks PENDING activities as CANCELLED."""
        from fleuve.tests.conftest import TestEvent

        adapter = MockAdapter()
        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=adapter,
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
        )

        # Create a PENDING activity in database
        activity = test_activity_model(
            workflow_id="wf-1",
            event_number=1,
            status=ActionStatus.PENDING.value,
            max_retries=3,
        )
        async with test_session_maker() as s:
            s.add(activity)
            await s.commit()

        await executor.cancel_workflow_actions("wf-1")

        from sqlalchemy import select

        async with test_session_maker() as s:
            activity = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            assert activity is not None
            assert activity.status == ActionStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_workflow_actions_cancels_running_task(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test that cancel_workflow_actions cancels a running action task."""
        from fleuve.tests.conftest import TestEvent

        class SlowAdapter(MockAdapter):
            async def act_on(self, event, context=None):
                self.called_events.append((event, context))
                if False:
                    yield  # pragma: no cover
                await asyncio.sleep(10)

        adapter = SlowAdapter()
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

        # Start action in background
        action_task = asyncio.create_task(executor.execute_action(event))

        # Wait for action to start
        await asyncio.sleep(0.3)

        # Cancel
        await executor.cancel_workflow_actions("wf-1")

        # Ensure the outer execute_action task finishes and background tasks are drained
        try:
            await action_task
        except asyncio.CancelledError:
            pass
        await self._wait_for_executor(executor)

        # Verify activity is CANCELLED
        from sqlalchemy import select

        async with test_session_maker() as s:
            activity = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            assert activity is not None
            assert activity.status == ActionStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_workflow_actions_specific_event_numbers(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Test that cancel_workflow_actions with event_numbers cancels only those."""
        adapter = MockAdapter()
        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=adapter,
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
        )

        # Create PENDING activities for events 1 and 2
        async with test_session_maker() as s:
            s.add(
                test_activity_model(
                    workflow_id="wf-1",
                    event_number=1,
                    status=ActionStatus.PENDING.value,
                    max_retries=3,
                )
            )
            s.add(
                test_activity_model(
                    workflow_id="wf-1",
                    event_number=2,
                    status=ActionStatus.PENDING.value,
                    max_retries=3,
                )
            )
            await s.commit()

        # Cancel only event 1
        await executor.cancel_workflow_actions("wf-1", event_numbers=[1])

        from sqlalchemy import select

        async with test_session_maker() as s:
            act1 = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 1)
            )
            act2 = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-1")
                .where(test_activity_model.event_number == 2)
            )
            assert act1.status == ActionStatus.CANCELLED.value
            assert act2.status == ActionStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_retry_failed_action(
        self,
        test_session_maker,
        ephemeral_storage,
        test_event_model,
        test_subscription_model,
        test_activity_model,
        clean_tables,
    ):
        """Test that retry_failed_action resets FAILED activity and re-executes."""
        from fleuve.repo import AsyncRepo
        from fleuve.tests.conftest import TestCommand, TestWorkflow

        adapter = MockAdapter(
            should_fail=False, return_cmd=TestCommand(action="update", value=5)
        )
        repo = AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
        )
        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=adapter,
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=repo,
            max_retries=0,
        )

        await repo.create_new(TestCommand(action="create", value=10), "wf-retry")
        await repo.process_command("wf-retry", TestCommand(action="update", value=5))

        failing_adapter = MockAdapter(should_fail=True)
        failing_executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=failing_adapter,
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=repo,
            max_retries=0,
        )

        from fleuve.stream import ConsumedEvent
        from fleuve.tests.conftest import TestEvent

        event = ConsumedEvent(
            workflow_id="wf-retry",
            event_no=2,
            event=TestEvent(value=5),
            global_id=2,
            at=datetime.datetime.now(datetime.timezone.utc),
            workflow_type="test_workflow",
        )
        await failing_executor.execute_action(event)
        await self._wait_for_executor(failing_executor)

        async with test_session_maker() as s:
            from sqlalchemy import select

            act = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-retry")
                .where(test_activity_model.event_number == 2)
            )
            assert act.status == ActionStatus.FAILED.value

        ok = await executor.retry_failed_action("wf-retry", 2)
        assert ok is True

        await asyncio.sleep(0.5)

        async with test_session_maker() as s:
            act = await s.scalar(
                select(test_activity_model)
                .where(test_activity_model.workflow_id == "wf-retry")
                .where(test_activity_model.event_number == 2)
            )
            assert act.status == ActionStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_retry_failed_action_not_found(
        self,
        test_session_maker,
        ephemeral_storage,
        test_event_model,
        test_subscription_model,
        test_activity_model,
        clean_tables,
    ):
        """Test retry_failed_action returns False when activity is not FAILED."""
        from fleuve.repo import AsyncRepo
        from fleuve.tests.conftest import TestWorkflow

        repo = AsyncRepo(
            session_maker=test_session_maker,
            es=ephemeral_storage,
            model=TestWorkflow,
            db_event_model=test_event_model,
            db_sub_model=test_subscription_model,
        )
        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=MockAdapter(),
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=repo,
        )

        ok = await executor.retry_failed_action("nonexistent", 1)
        assert ok is False


class TestActionConcurrencyLimits:
    """Tests for max_concurrent_actions and max_concurrent_actions_per_workflow."""

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.process_command = AsyncMock(return_value=None)
        return repo

    async def _wait_for_executor(self, executor: ActionExecutor) -> None:
        while True:
            tasks = list(executor._running_actions.values())
            if not tasks:
                break
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_global_concurrency_limit(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Global semaphore caps the number of actions executing at the same time."""
        from fleuve.tests.conftest import TestEvent

        peak = 0
        current = 0
        lock = asyncio.Lock()

        class SlowAdapter(Adapter):
            async def act_on(self, event, context=None):
                nonlocal peak, current
                async with lock:
                    current += 1
                    peak = max(peak, current)
                await asyncio.sleep(0.15)
                async with lock:
                    current -= 1
                if False:
                    yield  # pragma: no cover

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=SlowAdapter(),
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
            max_concurrent_actions=2,
        )

        events = [
            ConsumedEvent(
                workflow_id=f"wf-{i}",
                event_no=1,
                event=TestEvent(value=i),
                global_id=i,
                at=datetime.datetime.now(datetime.timezone.utc),
                workflow_type="test_workflow",
            )
            for i in range(5)
        ]

        for ev in events:
            await executor.execute_action(ev)

        await self._wait_for_executor(executor)

        assert peak <= 2, f"Peak concurrency was {peak}, expected <= 2"
        assert current == 0

    @pytest.mark.asyncio
    async def test_per_workflow_concurrency_limit(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Per-workflow semaphore caps concurrent actions for a single workflow."""
        from fleuve.tests.conftest import TestEvent

        peak_per_wf: dict[str, int] = {}
        current_per_wf: dict[str, int] = {}
        lock = asyncio.Lock()

        class SlowAdapter(Adapter):
            async def act_on(self, event, context=None):
                wf_id = event.workflow_id
                async with lock:
                    current_per_wf[wf_id] = current_per_wf.get(wf_id, 0) + 1
                    peak_per_wf[wf_id] = max(
                        peak_per_wf.get(wf_id, 0), current_per_wf[wf_id]
                    )
                await asyncio.sleep(0.15)
                async with lock:
                    current_per_wf[wf_id] -= 1
                if False:
                    yield  # pragma: no cover

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=SlowAdapter(),
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
            max_concurrent_actions_per_workflow=1,
        )

        events = [
            ConsumedEvent(
                workflow_id="wf-A",
                event_no=i,
                event=TestEvent(value=i),
                global_id=i,
                at=datetime.datetime.now(datetime.timezone.utc),
                workflow_type="test_workflow",
            )
            for i in range(1, 4)
        ]

        for ev in events:
            await executor.execute_action(ev)

        await self._wait_for_executor(executor)

        assert (
            peak_per_wf["wf-A"] <= 1
        ), f"Peak per-workflow concurrency was {peak_per_wf['wf-A']}, expected <= 1"

    @pytest.mark.asyncio
    async def test_per_workflow_allows_cross_workflow_concurrency(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Per-workflow limit does not prevent different workflows from running concurrently."""
        from fleuve.tests.conftest import TestEvent

        peak = 0
        current = 0
        lock = asyncio.Lock()

        class SlowAdapter(Adapter):
            async def act_on(self, event, context=None):
                nonlocal peak, current
                async with lock:
                    current += 1
                    peak = max(peak, current)
                await asyncio.sleep(0.2)
                async with lock:
                    current -= 1
                if False:
                    yield  # pragma: no cover

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=SlowAdapter(),
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
            max_concurrent_actions_per_workflow=1,
        )

        events = [
            ConsumedEvent(
                workflow_id=f"wf-{i}",
                event_no=1,
                event=TestEvent(value=i),
                global_id=i,
                at=datetime.datetime.now(datetime.timezone.utc),
                workflow_type="test_workflow",
            )
            for i in range(3)
        ]

        for ev in events:
            await executor.execute_action(ev)

        await self._wait_for_executor(executor)

        assert peak >= 2, f"Expected cross-workflow concurrency >= 2 but got {peak}"

    @pytest.mark.asyncio
    async def test_both_limits_combined(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """When both limits are set, the stricter one wins."""
        from fleuve.tests.conftest import TestEvent

        peak = 0
        current = 0
        lock = asyncio.Lock()

        class SlowAdapter(Adapter):
            async def act_on(self, event, context=None):
                nonlocal peak, current
                async with lock:
                    current += 1
                    peak = max(peak, current)
                await asyncio.sleep(0.15)
                async with lock:
                    current -= 1
                if False:
                    yield  # pragma: no cover

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=SlowAdapter(),
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
            max_concurrent_actions=2,
            max_concurrent_actions_per_workflow=1,
        )

        events = [
            ConsumedEvent(
                workflow_id=f"wf-{i}",
                event_no=1,
                event=TestEvent(value=i),
                global_id=i,
                at=datetime.datetime.now(datetime.timezone.utc),
                workflow_type="test_workflow",
            )
            for i in range(5)
        ]

        for ev in events:
            await executor.execute_action(ev)

        await self._wait_for_executor(executor)

        assert peak <= 2, f"Peak concurrency was {peak}, expected <= 2 (global limit)"

    @pytest.mark.asyncio
    async def test_no_limits_is_unbounded(
        self,
        test_session_maker,
        test_activity_model,
        test_event_model,
        clean_tables,
        mock_repo,
    ):
        """Default (no limits) allows all actions to run concurrently."""
        from fleuve.tests.conftest import TestEvent

        peak = 0
        current = 0
        lock = asyncio.Lock()

        class SlowAdapter(Adapter):
            async def act_on(self, event, context=None):
                nonlocal peak, current
                async with lock:
                    current += 1
                    peak = max(peak, current)
                await asyncio.sleep(0.15)
                async with lock:
                    current -= 1
                if False:
                    yield  # pragma: no cover

            def to_be_act_on(self, event):
                return True

        executor = ActionExecutor(
            session_maker=test_session_maker,
            adapter=SlowAdapter(),
            db_activity_model=test_activity_model,
            db_event_model=test_event_model,
            repo=mock_repo,
        )

        events = [
            ConsumedEvent(
                workflow_id=f"wf-{i}",
                event_no=1,
                event=TestEvent(value=i),
                global_id=i,
                at=datetime.datetime.now(datetime.timezone.utc),
                workflow_type="test_workflow",
            )
            for i in range(5)
        ]

        for ev in events:
            await executor.execute_action(ev)

        await self._wait_for_executor(executor)

        assert peak >= 4, f"Expected near-full concurrency (>= 4) but got {peak}"
