"""
Unit tests for les.delay module.
"""
import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleuve.delay import DelayScheduler
from fleuve.model import EvDelay, EvDelayComplete


class TestDelayScheduler:
    """Tests for DelayScheduler class using real database."""

    @pytest.fixture
    def delay_scheduler(
        self,
        test_session_maker,
        test_event_model,
        test_delay_schedule_model,
    ):
        """Create a DelayScheduler instance with real database."""
        return DelayScheduler(
            session_maker=test_session_maker,
            workflow_type="test_workflow",
            db_event_model=test_event_model,
            db_delay_schedule_model=test_delay_schedule_model,
            check_interval=datetime.timedelta(seconds=1),
        )

    def test_delay_scheduler_initialization(self, delay_scheduler):
        """Test delay scheduler initialization."""
        assert delay_scheduler._workflow_type == "test_workflow"
        assert not delay_scheduler._running
        assert delay_scheduler._task is None

    @pytest.mark.asyncio
    async def test_delay_scheduler_start_stop(self, delay_scheduler):
        """Test starting and stopping delay scheduler."""
        await delay_scheduler.start()
        assert delay_scheduler._running
        assert delay_scheduler._task is not None

        await delay_scheduler.stop()
        assert not delay_scheduler._running
        # Task should be cancelled
        assert delay_scheduler._task.cancelled()

    @pytest.mark.asyncio
    async def test_delay_scheduler_context_manager(self, delay_scheduler):
        """Test delay scheduler as async context manager."""
        async with delay_scheduler:
            assert delay_scheduler._running
        assert not delay_scheduler._running

    @pytest.mark.asyncio
    async def test_register_delay(
        self,
        delay_scheduler,
        test_session,
        clean_tables,
    ):
        """Test registering a delay."""
        from fleuve.tests.conftest import TestCommand

        delay_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
        delay_event = EvDelay(
            id="delay-1",
            delay_until=delay_until,
            next_cmd=TestCommand(action="resume", value=10),
        )

        await delay_scheduler.register_delay(
            workflow_id="wf-1",
            delay_event=delay_event,
            event_version=5,
        )

        # Verify delay schedule was created in database
        from sqlalchemy import select
        schedule = await test_session.scalar(
            select(delay_scheduler._db_delay_schedule_model)
            .where(delay_scheduler._db_delay_schedule_model.workflow_id == "wf-1")
        )
        assert schedule is not None
        assert schedule.workflow_id == "wf-1"
        assert schedule.event_version == 5

    @pytest.mark.asyncio
    async def test_check_and_resume_no_schedules(
        self,
        delay_scheduler,
        clean_tables,
    ):
        """Test check_and_resume when no schedules are ready."""
        # Should not raise any exceptions when no schedules exist
        await delay_scheduler._check_and_resume()

    @pytest.mark.asyncio
    async def test_resume_workflow(
        self,
        delay_scheduler,
        test_session,
        clean_tables,
    ):
        """Test resuming a workflow."""
        from fleuve.tests.conftest import TestCommand, TestEvent
        from sqlalchemy import select

        # Create a delay schedule in database
        delay_until = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)  # Past
        schedule = delay_scheduler._db_delay_schedule_model(
            workflow_id="wf-1",
            delay_id="delay-1",
            workflow_type="test_workflow",
            delay_until=delay_until,
            event_version=5,
            next_command=TestCommand(action="resume", value=10),
        )
        test_session.add(schedule)
        
        # Create an event at version 5
        event = delay_scheduler._db_event_model(
            workflow_id="wf-1",
            workflow_version=5,
            event_type="test_event",
            workflow_type="test_workflow",
            body=TestEvent(value=10),
        )
        test_session.add(event)
        await test_session.commit()

        # Resume the workflow
        await delay_scheduler._resume_workflow(test_session, schedule)

        # Verify EvDelayComplete event was created
        # EvDelayComplete is an abstract class, check for the concrete type
        from fleuve.model import EvDelayComplete
        complete_event = await test_session.scalar(
            select(delay_scheduler._db_event_model)
            .where(delay_scheduler._db_event_model.workflow_id == "wf-1")
            .where(delay_scheduler._db_event_model.workflow_version == 6)  # version 5 + 1
        )
        assert complete_event is not None
        # Check that it's a delay_complete type event
        assert "delay" in complete_event.event_type.lower() or complete_event.event_type == "delay_complete"

    @pytest.mark.asyncio
    async def test_resume_workflow_no_events(
        self,
        delay_scheduler,
        test_session,
        clean_tables,
    ):
        """Test resuming workflow when no events exist."""
        from fleuve.tests.conftest import TestCommand

        # Create a delay schedule for a workflow with no events
        delay_until = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)  # Past
        schedule = delay_scheduler._db_delay_schedule_model(
            workflow_id="wf-1",
            delay_id="delay-1",
            workflow_type="test_workflow",
            delay_until=delay_until,
            event_version=5,
            next_command=TestCommand(action="resume", value=10),
        )
        test_session.add(schedule)
        await test_session.commit()

        # Resume the workflow (should clean up since no events exist)
        await delay_scheduler._resume_workflow(test_session, schedule)

        # Verify delay schedule was deleted
        from sqlalchemy import select
        schedule_check = await test_session.scalar(
            select(delay_scheduler._db_delay_schedule_model)
            .where(delay_scheduler._db_delay_schedule_model.workflow_id == "wf-1")
        )
        assert schedule_check is None

    @pytest.mark.asyncio
    async def test_run_loop_stops_when_not_running(
        self,
        delay_scheduler,
    ):
        """Test that run loop stops when _running is False."""
        delay_scheduler._running = True
        delay_scheduler._check_interval = datetime.timedelta(milliseconds=10)

        # Start the loop in background
        task = asyncio.create_task(delay_scheduler._run_loop())

        # Let it run a bit
        await asyncio.sleep(0.05)

        # Stop it
        delay_scheduler._running = False
        await asyncio.sleep(0.05)

        # Should complete without error
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
