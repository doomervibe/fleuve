"""
Unit tests for les.runner module.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleuve.model import EvDelay, EvDelayComplete, EvDirectMessage
from fleuve.runner import SideEffects, WorkflowsRunner
from fleuve.stream import ConsumedEvent


class TestSideEffects:
    """Tests for SideEffects class."""

    @pytest.fixture
    def mock_action_executor(self):
        """Create a mock action executor."""
        executor = AsyncMock()
        executor.to_be_act_on = MagicMock(return_value=False)
        executor.execute_action = AsyncMock()
        executor.__aenter__ = AsyncMock(return_value=executor)
        executor.__aexit__ = AsyncMock(return_value=False)
        return executor

    @pytest.fixture
    def mock_delay_scheduler(self):
        """Create a mock delay scheduler."""
        scheduler = AsyncMock()
        scheduler.register_delay = AsyncMock()
        scheduler.__aenter__ = AsyncMock(return_value=scheduler)
        scheduler.__aexit__ = AsyncMock(return_value=False)
        return scheduler

    @pytest.fixture
    def side_effects(self, mock_action_executor, mock_delay_scheduler):
        """Create a SideEffects instance."""
        return SideEffects(
            action_executor=mock_action_executor,
            delay_scheduler=mock_delay_scheduler,
        )

    @pytest.mark.asyncio
    async def test_context_manager(self, side_effects, mock_action_executor, mock_delay_scheduler):
        """Test SideEffects as async context manager."""
        async with side_effects:
            mock_action_executor.__aenter__.assert_called_once()
            mock_delay_scheduler.__aenter__.assert_called_once()

        mock_action_executor.__aexit__.assert_called_once()
        mock_delay_scheduler.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_maybe_act_on_delay_event(self, side_effects, mock_delay_scheduler):
        """Test handling EvDelay events."""
        from pydantic import BaseModel
        import datetime

        class TestCmd(BaseModel):
            action: str

        delay_event = EvDelay(
            delay_until=datetime.datetime.now(),
            next_cmd=TestCmd(action="test"),
        )

        consumed_event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=delay_event,
            global_id=1,
            at=datetime.datetime.now(),
            workflow_type="test_workflow",
        )

        await side_effects.maybe_act_on(consumed_event)
        mock_delay_scheduler.register_delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_maybe_act_on_regular_event(self, side_effects, mock_action_executor):
        """Test handling regular events."""
        from pydantic import BaseModel
        import datetime

        class TestEvent(BaseModel):
            type: str = "test"

        event = TestEvent()
        consumed_event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=event,
            global_id=1,
            at=datetime.datetime.now(),
            workflow_type="test_workflow",
        )

        mock_action_executor.to_be_act_on.return_value = True
        await side_effects.maybe_act_on(consumed_event)
        mock_action_executor.execute_action.assert_called_once_with(consumed_event)

    @pytest.mark.asyncio
    async def test_maybe_act_on_skips_if_not_to_act(self, side_effects, mock_action_executor):
        """Test that events not to be acted on are skipped."""
        from pydantic import BaseModel
        import datetime

        class TestEvent(BaseModel):
            type: str = "test"

        event = TestEvent()
        consumed_event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=event,
            global_id=1,
            at=datetime.datetime.now(),
            workflow_type="test_workflow",
        )

        mock_action_executor.to_be_act_on.return_value = False
        await side_effects.maybe_act_on(consumed_event)
        mock_action_executor.execute_action.assert_not_called()


class TestWorkflowsRunner:
    """Tests for WorkflowsRunner class."""

    @pytest.fixture
    def mock_repo(self):
        """Create a mock repository."""
        repo = AsyncMock()
        repo.process_command = AsyncMock()
        return repo

    @pytest.fixture
    def mock_readers(self):
        """Create a mock readers."""
        readers = MagicMock()
        reader = AsyncMock()
        reader.iter_events = AsyncMock()
        readers.reader = MagicMock(return_value=reader)
        return readers

    @pytest.fixture
    def mock_workflow_type(self):
        """Create a mock workflow type."""
        from fleuve.tests.conftest import TestWorkflow
        return TestWorkflow

    @pytest.fixture
    def mock_session_maker(self, test_session_maker):
        """Create a session maker using real database."""
        return test_session_maker

    @pytest.fixture
    def mock_db_sub_type(self, test_subscription_model):
        """Create a subscription model using real database."""
        return test_subscription_model

    @pytest.fixture
    def mock_side_effects(self):
        """Create a mock side effects."""
        se = AsyncMock()
        se.maybe_act_on = AsyncMock()
        se.__aenter__ = AsyncMock(return_value=se)
        se.__aexit__ = AsyncMock(return_value=False)
        return se

    @pytest.fixture
    def runner(
        self,
        mock_repo,
        mock_readers,
        mock_workflow_type,
        mock_session_maker,
        mock_db_sub_type,
        mock_side_effects,
    ):
        """Create a WorkflowsRunner instance."""
        return WorkflowsRunner(
            repo=mock_repo,
            readers=mock_readers,
            workflow_type=mock_workflow_type,
            session_maker=mock_session_maker,
            db_sub_type=mock_db_sub_type,
            se=mock_side_effects,
        )

    def test_to_be_act_on_same_workflow_type(self, runner):
        """Test to_be_act_on for same workflow type."""
        import datetime
        from pydantic import BaseModel

        class TestEvent(BaseModel):
            type: str = "test"

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(),
            global_id=1,
            at=datetime.datetime.now(),
            workflow_type="test_workflow",
        )

        assert runner.to_be_act_on(event)

    def test_to_be_act_on_different_workflow_type(self, runner):
        """Test to_be_act_on for different workflow type."""
        import datetime
        from pydantic import BaseModel

        class TestEvent(BaseModel):
            type: str = "test"

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(),
            global_id=1,
            at=datetime.datetime.now(),
            workflow_type="other_workflow",
        )

        assert not runner.to_be_act_on(event)

    def test_to_be_act_on_with_wf_id_rule(self, mock_workflow_type):
        """Test to_be_act_on with workflow ID rule."""
        import datetime
        from pydantic import BaseModel

        class TestEvent(BaseModel):
            type: str = "test"

        mock_repo = AsyncMock()
        mock_readers = MagicMock()
        mock_session_maker = MagicMock()
        mock_db_sub_type = MagicMock()
        mock_side_effects = AsyncMock()

        runner = WorkflowsRunner(
            repo=mock_repo,
            readers=mock_readers,
            workflow_type=mock_workflow_type,
            session_maker=mock_session_maker,
            db_sub_type=mock_db_sub_type,
            se=mock_side_effects,
            wf_id_rule=lambda x: x.startswith("wf-"),
        )

        event1 = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=TestEvent(),
            global_id=1,
            at=datetime.datetime.now(),
            workflow_type="test_workflow",
        )

        event2 = ConsumedEvent(
            workflow_id="other-1",
            event_no=1,
            event=TestEvent(),
            global_id=1,
            at=datetime.datetime.now(),
            workflow_type="test_workflow",
        )

        assert runner.to_be_act_on(event1)
        assert not runner.to_be_act_on(event2)

    @pytest.mark.asyncio
    async def test_workflows_to_notify_direct_message(self, runner, test_session, clean_tables):
        """Test finding workflows to notify for EvDirectMessage."""
        import datetime

        # Create concrete EvDirectMessage subclass
        class ConcreteEvDirectMessage(EvDirectMessage):
            type: str = "direct_message"

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=ConcreteEvDirectMessage(
                target_workflow_id="wf-2",
                target_workflow_type="test_workflow",
            ),
            global_id=1,
            at=datetime.datetime.now(),
            workflow_type="test_workflow",
        )

        workflows = await runner.workflows_to_notify(event)
        assert "wf-2" in workflows

    @pytest.mark.asyncio
    async def test_workflows_to_notify_delay_complete(self, runner):
        """Test finding workflows to notify for EvDelayComplete."""
        import datetime

        # Create concrete EvDelayComplete subclass
        class ConcreteEvDelayComplete(EvDelayComplete):
            type: str = "delay_complete"

        event = ConsumedEvent(
            workflow_id="wf-1",
            event_no=1,
            event=ConcreteEvDelayComplete(at=datetime.datetime.now()),
            global_id=1,
            at=datetime.datetime.now(),
            workflow_type="test_workflow",
        )

        workflows = await runner.workflows_to_notify(event)
        assert "wf-1" in workflows  # Should notify itself

    @pytest.mark.asyncio
    async def test_context_manager(self, runner, mock_side_effects):
        """Test WorkflowsRunner as async context manager."""
        async with runner:
            mock_side_effects.__aenter__.assert_called_once()
        mock_side_effects.__aexit__.assert_called_once()


class TestCachedSubscription:
    """Tests for CachedSubscription class."""
    
    def test_matches_event_basic(self):
        """Test basic event matching without tags."""
        from fleuve.runner import CachedSubscription
        
        sub = CachedSubscription(
            workflow_id="wf-1",
            subscribed_to_workflow="source-wf",
            subscribed_to_event_type="payment.completed",
            tags=[],
            tags_all=[]
        )
        
        # Should match
        assert sub.matches_event("source-wf", "payment.completed", set(), set())
        
        # Should not match - different workflow
        assert not sub.matches_event("other-wf", "payment.completed", set(), set())
        
        # Should not match - different event type
        assert not sub.matches_event("source-wf", "payment.failed", set(), set())
    
    def test_matches_event_wildcard_workflow(self):
        """Test matching with wildcard workflow."""
        from fleuve.runner import CachedSubscription
        
        sub = CachedSubscription(
            workflow_id="wf-1",
            subscribed_to_workflow="*",
            subscribed_to_event_type="payment.completed",
            tags=[],
            tags_all=[]
        )
        
        # Should match any workflow
        assert sub.matches_event("any-wf", "payment.completed", set(), set())
        assert sub.matches_event("other-wf", "payment.completed", set(), set())
        
        # Should not match different event type
        assert not sub.matches_event("any-wf", "payment.failed", set(), set())
    
    def test_matches_event_wildcard_event_type(self):
        """Test matching with wildcard event type."""
        from fleuve.runner import CachedSubscription
        
        sub = CachedSubscription(
            workflow_id="wf-1",
            subscribed_to_workflow="source-wf",
            subscribed_to_event_type="*",
            tags=[],
            tags_all=[]
        )
        
        # Should match any event type from source-wf
        assert sub.matches_event("source-wf", "payment.completed", set(), set())
        assert sub.matches_event("source-wf", "payment.failed", set(), set())
        
        # Should not match different workflow
        assert not sub.matches_event("other-wf", "payment.completed", set(), set())
    
    def test_matches_event_with_tags_any(self):
        """Test matching with tags (OR logic)."""
        from fleuve.runner import CachedSubscription
        
        sub = CachedSubscription(
            workflow_id="wf-1",
            subscribed_to_workflow="*",
            subscribed_to_event_type="*",
            tags=["urgent", "high-priority"],
            tags_all=[]
        )
        
        # Should match if ANY tag matches
        assert sub.matches_event("any-wf", "any-event", {"urgent"}, set())
        assert sub.matches_event("any-wf", "any-event", {"high-priority"}, set())
        assert sub.matches_event("any-wf", "any-event", {"urgent", "other"}, set())
        
        # Should match if tag is in workflow tags
        assert sub.matches_event("any-wf", "any-event", set(), {"urgent"})
        
        # Should not match if no tags match
        assert not sub.matches_event("any-wf", "any-event", {"other"}, set())
        assert not sub.matches_event("any-wf", "any-event", set(), {"other"})
    
    def test_matches_event_with_tags_all(self):
        """Test matching with tags_all (AND logic)."""
        from fleuve.runner import CachedSubscription
        
        sub = CachedSubscription(
            workflow_id="wf-1",
            subscribed_to_workflow="*",
            subscribed_to_event_type="*",
            tags=[],
            tags_all=["production", "us-east"]
        )
        
        # Should match only if ALL tags match
        assert sub.matches_event("any-wf", "any-event", {"production", "us-east"}, set())
        assert sub.matches_event("any-wf", "any-event", {"production", "us-east", "other"}, set())
        
        # Should match if tags spread across event and workflow tags
        assert sub.matches_event("any-wf", "any-event", {"production"}, {"us-east"})
        
        # Should not match if missing any required tag
        assert not sub.matches_event("any-wf", "any-event", {"production"}, set())
        assert not sub.matches_event("any-wf", "any-event", {"us-east"}, set())
        assert not sub.matches_event("any-wf", "any-event", set(), {"production"})
    
    def test_matches_event_combined_tags(self):
        """Test matching with both tags and tags_all."""
        from fleuve.runner import CachedSubscription
        
        sub = CachedSubscription(
            workflow_id="wf-1",
            subscribed_to_workflow="*",
            subscribed_to_event_type="*",
            tags=["urgent", "critical"],
            tags_all=["production"]
        )
        
        # Should match if has ANY tag AND ALL required tags
        assert sub.matches_event("any-wf", "any-event", {"urgent", "production"}, set())
        assert sub.matches_event("any-wf", "any-event", {"critical", "production"}, set())
        
        # Should not match if missing required tag
        assert not sub.matches_event("any-wf", "any-event", {"urgent"}, set())
        
        # Should not match if has required tag but no matching tags
        assert not sub.matches_event("any-wf", "any-event", {"production"}, set())


class TestSubscriptionCache(TestWorkflowsRunner):
    """Tests for subscription cache functionality."""
    
    @pytest.mark.asyncio
    async def test_load_subscription_cache(
        self, 
        mock_repo, 
        mock_readers, 
        mock_workflow_type, 
        mock_session_maker, 
        mock_db_sub_type,
        mock_side_effects,
        test_session,
        clean_tables
    ):
        """Test loading subscriptions into cache on startup."""
        from fleuve.model import Sub
        
        # Insert some test subscriptions into database
        async with mock_session_maker() as s:
            from sqlalchemy import insert
            
            await s.execute(
                insert(mock_db_sub_type).values([
                    {
                        "workflow_id": "wf-1",
                        "workflow_type": "test_workflow",
                        "subscribed_to_workflow": "payment-wf",
                        "subscribed_to_event_type": "payment.completed",
                        "tags": ["urgent"],
                        "tags_all": []
                    },
                    {
                        "workflow_id": "wf-2",
                        "workflow_type": "test_workflow",
                        "subscribed_to_workflow": "*",
                        "subscribed_to_event_type": "order.*",
                        "tags": [],
                        "tags_all": ["production"]
                    }
                ])
            )
            await s.commit()
        
        # Create runner
        runner = WorkflowsRunner(
            repo=mock_repo,
            readers=mock_readers,
            workflow_type=mock_workflow_type,
            session_maker=mock_session_maker,
            db_sub_type=mock_db_sub_type,
            se=mock_side_effects,
        )
        
        # Load cache
        await runner._load_subscription_cache()
        
        # Verify cache was loaded
        assert runner._cache_initialized
        assert "wf-1" in runner._subscription_cache
        assert "wf-2" in runner._subscription_cache
        assert len(runner._subscription_cache["wf-1"]) == 1
        assert len(runner._subscription_cache["wf-2"]) == 1
        
        # Verify cache contents
        wf1_sub = runner._subscription_cache["wf-1"][0]
        assert wf1_sub.subscribed_to_workflow == "payment-wf"
        assert wf1_sub.subscribed_to_event_type == "payment.completed"
        assert wf1_sub.tags == ["urgent"]
    
    @pytest.mark.asyncio
    async def test_update_subscription_cache(
        self,
        mock_repo,
        mock_readers,
        mock_workflow_type,
        mock_session_maker,
        mock_db_sub_type,
        mock_side_effects
    ):
        """Test updating subscription cache."""
        from fleuve.model import Sub
        
        # Create runner with initialized cache
        runner = WorkflowsRunner(
            repo=mock_repo,
            readers=mock_readers,
            workflow_type=mock_workflow_type,
            session_maker=mock_session_maker,
            db_sub_type=mock_db_sub_type,
            se=mock_side_effects,
        )
        runner._cache_initialized = True
        
        # Update cache with new subscriptions
        subs = [
            Sub(
                workflow_id="payment-wf",
                event_type="payment.completed",
                tags=["urgent"],
                tags_all=[]
            ),
            Sub(
                workflow_id="*",
                event_type="order.*",
                tags=[],
                tags_all=["production"]
            )
        ]
        
        await runner._update_subscription_cache("wf-1", subs)
        
        # Verify cache was updated
        assert "wf-1" in runner._subscription_cache
        assert len(runner._subscription_cache["wf-1"]) == 2
        
        # Update with empty subscriptions (should remove from cache)
        await runner._update_subscription_cache("wf-1", [])
        assert "wf-1" not in runner._subscription_cache
    
    @pytest.mark.asyncio
    async def test_find_subscriptions_uses_cache(
        self,
        mock_repo,
        mock_readers,
        mock_workflow_type,
        mock_session_maker,
        mock_db_sub_type,
        mock_side_effects
    ):
        """Test that find_subscriptions uses cache instead of database."""
        import datetime
        from pydantic import BaseModel
        from fleuve.runner import CachedSubscription
        
        class TestEvent(BaseModel):
            type: str = "payment.completed"
        
        # Create runner with cache
        runner = WorkflowsRunner(
            repo=mock_repo,
            readers=mock_readers,
            workflow_type=mock_workflow_type,
            session_maker=mock_session_maker,
            db_sub_type=mock_db_sub_type,
            se=mock_side_effects,
        )
        runner._cache_initialized = True
        
        # Populate cache
        runner._subscription_cache["wf-1"] = [
            CachedSubscription(
                workflow_id="wf-1",
                subscribed_to_workflow="payment-wf",
                subscribed_to_event_type="payment.completed",
                tags=[],
                tags_all=[]
            )
        ]
        
        # Mock repo.get_workflow_tags to return empty list
        mock_repo.get_workflow_tags = AsyncMock(return_value=[])
        
        # Create event
        event = ConsumedEvent(
            workflow_id="payment-wf",
            event_no=1,
            event=TestEvent(),
            global_id=1,
            at=datetime.datetime.now(),
            workflow_type="payment_workflow",
            metadata_={}
        )
        
        # Find subscriptions
        workflows = await runner.find_subscriptions(event)
        
        # Should find wf-1 from cache
        assert "wf-1" in workflows
        
        # Verify database was not queried (no session maker calls)
        # Since we're using cache, session_maker shouldn't be called
