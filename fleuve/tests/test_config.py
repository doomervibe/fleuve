"""
Tests for les.config module.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.config import WorkflowConfig, make_runner_from_config
from fleuve.model import Adapter
from fleuve.postgres import Activity, DelaySchedule, StoredEvent, Subscription
from fleuve.repo import AsyncRepo
from fleuve.runner import WorkflowsRunner
from fleuve.tests.conftest import TestCommand, TestEvent, TestState, TestWorkflow


class TestWorkflowConfig:
    """Tests for WorkflowConfig dataclass."""

    def test_workflow_config_creation(self, test_workflow, test_session_maker):
        """Test creating a WorkflowConfig."""
        from fleuve.postgres import Offset

        adapter = MagicMock(spec=Adapter)
        db_sub_type = MagicMock(spec=Subscription)
        db_event_model = MagicMock(spec=StoredEvent)
        db_activity_model = MagicMock(spec=Activity)
        db_delay_schedule_model = MagicMock(spec=DelaySchedule)
        db_offset_model = MagicMock(spec=Offset)

        config = WorkflowConfig(
            nats_bucket="test_bucket",
            workflow_type=TestWorkflow,
            adapter=adapter,
            db_sub_type=db_sub_type,
            db_event_model=db_event_model,
            db_activity_model=db_activity_model,
            db_delay_schedule_model=db_delay_schedule_model,
            db_offset_model=db_offset_model,
        )

        assert config.nats_bucket == "test_bucket"
        assert config.workflow_type == TestWorkflow
        assert config.adapter == adapter
        assert config.db_sub_type == db_sub_type
        assert config.db_event_model == db_event_model
        assert config.db_activity_model == db_activity_model
        assert config.db_delay_schedule_model == db_delay_schedule_model
        assert config.wf_id_rule is None

    def test_workflow_config_with_wf_id_rule(self, test_workflow):
        """Test WorkflowConfig with wf_id_rule."""
        from fleuve.postgres import Offset

        adapter = MagicMock(spec=Adapter)
        db_sub_type = MagicMock(spec=Subscription)
        db_event_model = MagicMock(spec=StoredEvent)
        db_activity_model = MagicMock(spec=Activity)
        db_delay_schedule_model = MagicMock(spec=DelaySchedule)
        db_offset_model = MagicMock(spec=Offset)

        def wf_id_rule(workflow_id: str) -> bool:
            return workflow_id.startswith("test-")

        config = WorkflowConfig(
            nats_bucket="test_bucket",
            workflow_type=TestWorkflow,
            adapter=adapter,
            db_sub_type=db_sub_type,
            db_event_model=db_event_model,
            db_activity_model=db_activity_model,
            db_delay_schedule_model=db_delay_schedule_model,
            db_offset_model=db_offset_model,
            wf_id_rule=wf_id_rule,
        )

        assert config.wf_id_rule is not None
        assert config.wf_id_rule("test-123") is True
        assert config.wf_id_rule("prod-123") is False


class TestMakeRunnerFromConfig:
    """Tests for make_runner_from_config function."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter."""
        return MagicMock(spec=Adapter)

    @pytest.fixture
    def mock_repo(self):
        """Create a mock repository."""
        return MagicMock(spec=AsyncRepo)

    @pytest.fixture
    def mock_session_maker(self, test_session_maker):
        """Create a mock session maker."""
        return test_session_maker

    @pytest.fixture
    def workflow_config(self, test_workflow, mock_adapter):
        """Create a WorkflowConfig for testing."""
        from fleuve.tests.models import (
            DbEventModel,
            TestActivityModel,
            TestDelayScheduleModel,
            TestOffsetModel,
            TestSubscriptionModel,
        )

        return WorkflowConfig(
            nats_bucket="test_bucket",
            workflow_type=TestWorkflow,
            adapter=mock_adapter,
            db_sub_type=TestSubscriptionModel,
            db_event_model=DbEventModel,
            db_activity_model=TestActivityModel,
            db_delay_schedule_model=TestDelayScheduleModel,
            db_offset_model=TestOffsetModel,
        )

    def test_make_runner_from_config_basic(
        self, workflow_config, mock_repo, mock_session_maker
    ):
        """Test creating a runner from config with basic parameters."""
        runner = make_runner_from_config(
            config=workflow_config,
            repo=mock_repo,
            session_maker=mock_session_maker,
        )

        assert isinstance(runner, WorkflowsRunner)
        assert runner.repo == mock_repo
        assert runner.workflow_type == TestWorkflow
        assert runner.wf_id_rule is None

    def test_make_runner_from_config_with_wf_id_rule(
        self, workflow_config, mock_repo, mock_session_maker
    ):
        """Test creating a runner from config with wf_id_rule."""

        def wf_id_rule(workflow_id: str) -> bool:
            return workflow_id.startswith("test-")

        workflow_config.wf_id_rule = wf_id_rule

        runner = make_runner_from_config(
            config=workflow_config,
            repo=mock_repo,
            session_maker=mock_session_maker,
        )

        assert isinstance(runner, WorkflowsRunner)
        assert runner.wf_id_rule == wf_id_rule

    def test_make_runner_from_config_with_action_executor_kwargs(
        self, workflow_config, mock_repo, mock_session_maker
    ):
        """Test creating a runner with action_executor_kwargs."""
        runner = make_runner_from_config(
            config=workflow_config,
            repo=mock_repo,
            session_maker=mock_session_maker,
            action_executor_kwargs={"max_retries": 5},
        )

        assert isinstance(runner, WorkflowsRunner)
        # Verify the action executor was configured correctly
        assert runner.se is not None
        assert runner.se.action_executor is not None

    def test_make_runner_from_config_with_delay_scheduler_kwargs(
        self, workflow_config, mock_repo, mock_session_maker
    ):
        """Test creating a runner with delay_scheduler_kwargs."""
        runner = make_runner_from_config(
            config=workflow_config,
            repo=mock_repo,
            session_maker=mock_session_maker,
            delay_scheduler_kwargs={"check_interval": 2.0},
        )

        assert isinstance(runner, WorkflowsRunner)
        # Verify the delay scheduler was configured correctly
        assert runner.se is not None
        assert runner.se.delay_scheduler is not None

    def test_make_runner_from_config_with_both_kwargs(
        self, workflow_config, mock_repo, mock_session_maker
    ):
        """Test creating a runner with both action_executor and delay_scheduler kwargs."""
        runner = make_runner_from_config(
            config=workflow_config,
            repo=mock_repo,
            session_maker=mock_session_maker,
            action_executor_kwargs={"max_retries": 3},
            delay_scheduler_kwargs={"check_interval": 1.5},
        )

        assert isinstance(runner, WorkflowsRunner)
        assert runner.se is not None
        assert runner.se.action_executor is not None
        assert runner.se.delay_scheduler is not None

    def test_make_runner_from_config_readers_configured(
        self, workflow_config, mock_repo, mock_session_maker
    ):
        """Test that Readers are configured correctly in the runner (via stream)."""
        runner = make_runner_from_config(
            config=workflow_config,
            repo=mock_repo,
            session_maker=mock_session_maker,
        )

        # WorkflowsRunner uses readers to create a stream, not storing readers directly
        assert runner.stream is not None
        assert runner.stream.db_model == workflow_config.db_event_model

    def test_make_runner_from_config_side_effects_configured(
        self, workflow_config, mock_repo, mock_session_maker
    ):
        """Test that SideEffects are configured correctly in the runner."""
        runner = make_runner_from_config(
            config=workflow_config,
            repo=mock_repo,
            session_maker=mock_session_maker,
        )

        assert runner.se is not None
        assert runner.se.action_executor is not None
        assert runner.se.delay_scheduler is not None
