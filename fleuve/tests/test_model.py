"""
Unit tests for les.model module.
"""
import datetime
from abc import ABC
from typing import Literal

import pytest
from pydantic import ValidationError

from fleuve.model import (
    ActionContext,
    EventBase,
    EvDelay,
    EvDelayComplete,
    EvDirectMessage,
    Rejection,
    RetryPolicy,
    StateBase,
    Workflow,
)


class TestEventBase:
    """Tests for EventBase abstract class."""

    def test_event_base_requires_type_override(self):
        """Test that subclasses must override the type field."""
        with pytest.raises(TypeError, match="must override `type` with a Literal"):
            class InvalidEvent(EventBase):
                pass

    def test_valid_event_subclass(self):
        """Test creating a valid event subclass."""
        class ValidEvent(EventBase):
            type: Literal["valid_event"] = "valid_event"
            data: str

        event = ValidEvent(data="test")
        assert event.type == "valid_event"
        assert event.data == "test"

    def test_event_serialization(self):
        """Test event can be serialized to JSON."""
        class TestEvent(EventBase):
            type: Literal["test"] = "test"
            value: int

        event = TestEvent(value=42)
        json_data = event.model_dump_json()
        assert '"value":42' in json_data
        assert '"type":"test"' in json_data


class TestBuiltInEvents:
    """Tests for built-in abstract event types that are meant to be subclassed."""

    def test_ev_direct_message_is_abstract(self):
        """Test that EvDirectMessage is an ABC and can be subclassed."""
        from typing import Literal

        # Verify it's an ABC
        assert ABC in EvDirectMessage.__bases__

        # Create a concrete subclass
        class ConcreteDirectMessage(EvDirectMessage):
            type: Literal["concrete_direct"] = "concrete_direct"

        event = ConcreteDirectMessage(
            target_workflow_id="wf-123",
            target_workflow_type="test_workflow"
        )
        # Subclass should use its own type field
        assert event.type == "concrete_direct"
        assert event.target_workflow_id == "wf-123"
        assert event.target_workflow_type == "test_workflow"

    def test_ev_delay_complete_is_concrete(self):
        """Test that EvDelayComplete is a concrete class (not ABC), emitted by the system."""
        # EvDelayComplete is not an ABC - workflows receive it, don't subclass it
        assert ABC not in EvDelayComplete.__bases__

        from fleuve.tests.conftest import TestCommand

        now = datetime.datetime.now(datetime.timezone.utc)
        cmd = TestCommand(action="resume", value=42)
        event = EvDelayComplete(delay_id="reminder-1", at=now, next_cmd=cmd)
        assert event.type == "delay_complete"
        assert event.delay_id == "reminder-1"
        assert event.at == now
        assert event.next_cmd == cmd

    def test_ev_delay_is_abstract(self):
        """Test that EvDelay is an ABC and can be subclassed."""
        from pydantic import BaseModel
        from typing import Literal

        class TestCmd(BaseModel):
            action: str

        # Verify it's an ABC
        assert ABC in EvDelay.__bases__

        # Create a concrete subclass
        class ConcreteDelay(EvDelay[TestCmd]):
            type: Literal["concrete_delay"] = "concrete_delay"

        delay_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
        next_cmd = TestCmd(action="resume")
        event = ConcreteDelay(id="delay-1", delay_until=delay_until, next_cmd=next_cmd)
        assert event.type == "concrete_delay"
        assert event.delay_until == delay_until
        assert event.next_cmd == next_cmd


class TestRetryPolicy:
    """Tests for RetryPolicy."""

    def test_default_retry_policy(self):
        """Test default retry policy values."""
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.backoff_strategy == "exponential"
        assert policy.backoff_factor == 2
        assert policy.backoff_max == datetime.timedelta(seconds=60)
        assert policy.backoff_min == datetime.timedelta(seconds=1)
        assert policy.backoff_jitter == 0.5

    def test_custom_retry_policy(self):
        """Test custom retry policy."""
        policy = RetryPolicy(
            max_retries=5,
            backoff_strategy="linear",
            backoff_factor=1.5,
            backoff_max=datetime.timedelta(seconds=120),
            backoff_min=datetime.timedelta(seconds=2),
        )
        assert policy.max_retries == 5
        assert policy.backoff_strategy == "linear"
        assert policy.backoff_factor == 1.5

    def test_retry_policy_validation(self):
        """Test retry policy validation."""
        # max_retries must be >= 0
        with pytest.raises(ValidationError):
            RetryPolicy(max_retries=-1)


class TestActionContext:
    """Tests for ActionContext."""

    def test_action_context_creation(self, retry_policy: RetryPolicy):
        """Test creating an action context."""
        context = ActionContext(
            workflow_id="wf-1",
            event_number=5,
            checkpoint={"step": 2},
            retry_count=1,
            retry_policy=retry_policy,
        )
        assert context.workflow_id == "wf-1"
        assert context.event_number == 5
        assert context.checkpoint == {"step": 2}
        assert context.retry_count == 1
        assert context.retry_policy == retry_policy

class TestWorkflow:
    """Tests for Workflow abstract class."""

    def test_workflow_decide_and_evolve(self, test_workflow, test_command):
        """Test decide_and_evolve method."""
        # Test with None state (new workflow)
        result = test_workflow.decide_and_evolve(None, test_command)
        assert not isinstance(result, Rejection)
        state, events = result
        assert state is not None
        assert len(events) == 1
        assert events[0].value == test_command.value

    def test_workflow_decide_rejection(self, test_workflow):
        """Test rejection in decide_and_evolve."""
        from pydantic import BaseModel

        class TestCommand(BaseModel):
            action: str
            value: int = 0

        negative_cmd = TestCommand(action="test", value=-10)
        result = test_workflow.decide_and_evolve(None, negative_cmd)
        assert isinstance(result, Rejection)

    def test_workflow_evolve_chain(self, test_workflow):
        """Test evolving state through multiple events."""
        from pydantic import BaseModel
        from typing import Literal

        class TestEvent(EventBase):
            type: Literal["test_event"] = "test_event"
            value: int = 0

        state = None
        events = [
            TestEvent(value=10),
            TestEvent(value=20),
            TestEvent(value=30),
        ]
        state = test_workflow.evolve_(state, events)
        assert state.counter == 60

    def test_workflow_evolve_single_event(self, test_workflow):
        """Test evolving state with a single event."""
        from pydantic import BaseModel
        from typing import Literal

        class TestEvent(EventBase):
            type: Literal["test_event"] = "test_event"
            value: int = 0

        class TestState(StateBase):
            counter: int = 0
            subscriptions: list = []

        state = TestState(counter=10, subscriptions=[])
        event = TestEvent(value=5)
        new_state = test_workflow.evolve(state, event)
        assert new_state.counter == 15

    def test_workflow_is_final_event(self, test_workflow):
        """Test final event detection."""
        from pydantic import BaseModel
        from typing import Literal

        class TestEvent(EventBase):
            type: Literal["test_event"] = "test_event"
            value: int = 0

        assert not test_workflow.is_final_event(TestEvent(value=50))
        assert test_workflow.is_final_event(TestEvent(value=100))
        assert test_workflow.is_final_event(TestEvent(value=200))

    def test_workflow_event_to_cmd(self, test_workflow, test_event):
        """Test converting event to command."""
        # Import from conftest using sys.path or direct import
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent))
        from conftest import TestCommand

        cmd = test_workflow.event_to_cmd(test_event)
        assert cmd is not None
        # Check that it has the expected attributes rather than exact type
        assert hasattr(cmd, "action")
        assert hasattr(cmd, "value")
        assert cmd.value == 42

        # Event with value <= 0 should return None
        from pydantic import BaseModel
        from typing import Literal

        class ZeroEvent(EventBase):
            type: Literal["zero_event"] = "zero_event"
            value: int = 0

        cmd = test_workflow.event_to_cmd(ZeroEvent(value=0))
        assert cmd is None


class TestStateBase:
    """Tests for StateBase."""

    def test_state_base_with_subscriptions(self):
        """Test StateBase with subscriptions."""
        from fleuve.model import Sub

        subs = [Sub(event_type="test_event", workflow_id="wf-1")]
        state = StateBase(subscriptions=subs, external_subscriptions=[])
        assert len(state.subscriptions) == 1
        assert state.subscriptions[0].event_type == "test_event"


class TestRejection:
    """Tests for Rejection."""

    def test_rejection_creation(self):
        """Test creating a rejection."""
        rejection = Rejection()
        assert isinstance(rejection, Rejection)
