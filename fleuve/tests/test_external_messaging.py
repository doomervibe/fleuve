"""Tests for external NATS messaging: parse_subject, resolve_workflow_ids, ExternalSub, ExternalSubscription, repo sync, ExternalMessageConsumer."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.external_messaging import (
    EXTERNAL_SUBJECT_PREFIX,
    ROUTING_ALL,
    ROUTING_ID,
    ROUTING_TAG,
    ROUTING_TOPIC,
    ExternalMessageConsumer,
    parse_subject,
    resolve_workflow_ids,
)
from fleuve.model import ExternalSub, Rejection, StateBase, Sub
from fleuve.postgres import ExternalSubscription


class TestParseSubject:
    """Tests for parse_subject."""

    def test_parse_subject_all(self):
        assert parse_subject("messages.orders.all._", "orders") == ("all", "_")

    def test_parse_subject_tag(self):
        assert parse_subject("messages.orders.tag.urgent", "orders") == (
            "tag",
            "urgent",
        )

    def test_parse_subject_id(self):
        assert parse_subject("messages.orders.id.order-123", "orders") == (
            "id",
            "order-123",
        )

    def test_parse_subject_topic(self):
        assert parse_subject("messages.orders.topic.order.created", "orders") == (
            "topic",
            "order.created",
        )

    def test_parse_subject_wrong_workflow_type_returns_none(self):
        assert parse_subject("messages.orders.topic.x", "payments") is None

    def test_parse_subject_no_prefix_returns_none(self):
        assert parse_subject("orders.topic.x", "orders") is None

    def test_parse_subject_invalid_routing_returns_none(self):
        assert parse_subject("messages.orders.unknown.x", "orders") is None

    def test_parse_subject_too_few_parts_returns_none(self):
        assert parse_subject("messages.orders", "orders") is None


class TestExternalSub:
    """Tests for ExternalSub model."""

    def test_external_sub_creation(self):
        sub = ExternalSub(topic="order.created")
        assert sub.topic == "order.created"


class TestStateBaseExternalSubscriptions:
    """Tests for StateBase with external_subscriptions."""

    def test_state_base_external_subscriptions_default(self):
        state = StateBase(subscriptions=[], external_subscriptions=[])
        assert state.external_subscriptions == []

    def test_state_base_external_subscriptions_with_topics(self):
        state = StateBase(
            subscriptions=[],
            external_subscriptions=[
                ExternalSub(topic="order.created"),
                ExternalSub(topic="payment.completed"),
            ],
        )
        assert len(state.external_subscriptions) == 2
        assert state.external_subscriptions[0].topic == "order.created"
        assert state.external_subscriptions[1].topic == "payment.completed"


class TestResolveWorkflowIds:
    """Tests for resolve_workflow_ids with test database."""

    @pytest.mark.asyncio
    async def test_resolve_workflow_ids_all(self, test_session_maker, test_engine):
        from fleuve.tests.conftest import TestEvent
        from fleuve.tests.models import DbEventModel

        ev = TestEvent(value=0)
        async with test_session_maker() as s:
            await s.execute(
                DbEventModel.__table__.insert().values(
                    [
                        {
                            "workflow_id": "w1",
                            "workflow_version": 1,
                            "event_type": "test_event",
                            "workflow_type": "test",
                            "body": ev,
                        },
                        {
                            "workflow_id": "w2",
                            "workflow_version": 1,
                            "event_type": "test_event",
                            "workflow_type": "test",
                            "body": ev,
                        },
                    ]
                )
            )
            await s.commit()

        ids = await resolve_workflow_ids(
            test_session_maker,
            ROUTING_ALL,
            "",
            "test",
            DbEventModel,
            None,
            None,
            None,
        )
        assert set(ids) == {"w1", "w2"}

    @pytest.mark.asyncio
    async def test_resolve_workflow_ids_id(self, test_session_maker):
        from fleuve.tests.models import DbEventModel

        ids = await resolve_workflow_ids(
            test_session_maker,
            ROUTING_ID,
            "target-wf",
            "test",
            DbEventModel,
            None,
            None,
            None,
        )
        assert ids == ["target-wf"]

    @pytest.mark.asyncio
    async def test_resolve_workflow_ids_topic(self, test_session_maker, test_engine):
        from fleuve.tests.models import DbEventModel, TestExternalSubscriptionModel

        async with test_session_maker() as s:
            await s.execute(
                TestExternalSubscriptionModel.__table__.insert().values(
                    [
                        {
                            "workflow_id": "sub1",
                            "workflow_type": "test",
                            "topic": "order.created",
                        },
                        {
                            "workflow_id": "sub2",
                            "workflow_type": "test",
                            "topic": "order.created",
                        },
                        {
                            "workflow_id": "sub3",
                            "workflow_type": "test",
                            "topic": "other.topic",
                        },
                    ]
                )
            )
            await s.commit()

        ids = await resolve_workflow_ids(
            test_session_maker,
            ROUTING_TOPIC,
            "order.created",
            "test",
            DbEventModel,
            TestExternalSubscriptionModel,
            None,
            None,
        )
        assert set(ids) == {"sub1", "sub2"}

    @pytest.mark.asyncio
    async def test_resolve_workflow_ids_topic_no_model_returns_empty(
        self, test_session_maker
    ):
        from fleuve.tests.models import DbEventModel

        ids = await resolve_workflow_ids(
            test_session_maker,
            ROUTING_TOPIC,
            "order.created",
            "test",
            DbEventModel,
            None,
            None,
            None,
        )
        assert ids == []


class TestRepoExternalSubscriptions:
    """Tests for repo _handle_external_subscriptions (via process_command)."""

    @pytest.mark.asyncio
    async def test_repo_persists_external_subscriptions(
        self,
        test_engine,
        test_session_maker,
        nats_client,
    ):
        """When state has external_subscriptions, repo persists them to the external subscription table."""
        import uuid
        from fleuve.model import EvExternalSubscriptionAdded
        from fleuve.tests.conftest import (
            TestCommand,
            TestEvent,
            TestState,
            TestWorkflow,
        )
        from fleuve.tests.models import (
            DbEventModel,
            TestExternalSubscriptionModel,
            TestOffsetModel,
            TestSubscriptionModel,
        )
        from fleuve.repo import AsyncRepo
        from fleuve.repo import EuphStorageNATS

        # Workflow that emits EvExternalSubscriptionAdded from decide
        class WorkflowWithExternalSubs(TestWorkflow):
            @staticmethod
            def decide(state, cmd):
                if state is None:
                    return [
                        TestEvent(value=1),
                        EvExternalSubscriptionAdded(sub=ExternalSub(topic="order.created")),
                        EvExternalSubscriptionAdded(sub=ExternalSub(topic="payment.done")),
                    ]
                return [Rejection()]

            @staticmethod
            def is_final_event(e):
                return isinstance(e, TestEvent) and e.value >= 100

            @staticmethod
            def _evolve(state, event):
                if state is None:
                    return TestState(
                        counter=1,
                        subscriptions=[],
                        external_subscriptions=[],
                    )
                return TestState(
                    counter=state.counter + event.value,
                    subscriptions=state.subscriptions,
                    external_subscriptions=state.external_subscriptions,
                )

        bucket_name = f"test_states_ext_{uuid.uuid4().hex[:8]}"
        storage = EuphStorageNATS(nats_client, bucket_name, TestState)
        await storage.__aenter__()
        try:
            repo = AsyncRepo(
                session_maker=test_session_maker,
                es=storage,
                model=WorkflowWithExternalSubs,
                db_event_model=DbEventModel,
                db_sub_model=TestSubscriptionModel,
                db_external_sub_model=TestExternalSubscriptionModel,
            )
            result = await repo.create_new(
                TestCommand(action="start", value=1), "wf-ext-1"
            )
            assert not isinstance(result, Rejection)

            async with test_session_maker() as s:
                rows = (
                    (await s.execute(select(TestExternalSubscriptionModel)))
                    .scalars()
                    .all()
                )
                assert len(rows) == 2
                topics = {r.topic for r in rows}
                assert topics == {"order.created", "payment.done"}
                assert all(r.workflow_id == "wf-ext-1" for r in rows)
        finally:
            await storage.__aexit__(None, None, None)


class TestExternalMessageConsumer:
    """Tests for ExternalMessageConsumer (init and with mocks)."""

    def test_external_message_consumer_init(self):
        """ExternalMessageConsumer can be constructed with required args."""
        nc = MagicMock()
        repo = MagicMock()
        consumer = ExternalMessageConsumer(
            nats_client=nc,
            stream_name="external_test",
            consumer_name="test_consumer",
            workflow_type="test",
            workflow_type_class=MagicMock(),
            repo=repo,
            session_maker=MagicMock(),
            db_external_sub_type=MagicMock(),
            db_event_model=MagicMock(),
        )
        assert consumer._workflow_type == "test"
        assert consumer._stream_name == "external_test"
