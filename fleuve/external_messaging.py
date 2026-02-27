"""External NATS JetStream messaging for workflows.

Workflows can receive messages from NATS JetStream on a dedicated stream.
The runner listens for messages and routes them to workflows by:
- fanout (all workflows of this type)
- by tag (workflows with a given tag in workflow_metadata)
- by workflow id (single workflow)
- by topic (workflows subscribed to the message topic in the subscription table)
"""

import asyncio
import json
import logging
from typing import Any, Callable, Type, cast

from nats.aio.client import Client as NATS
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    DeliverPolicy,
    StorageType,
    StreamConfig,
)
from pydantic import BaseModel
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleuve.postgres import StoredEvent

logger = logging.getLogger(__name__)

# Subject pattern: messages.{workflow_type}.{routing}.{detail}
EXTERNAL_SUBJECT_PREFIX = "messages."
ROUTING_ALL = "all"
ROUTING_TAG = "tag"
ROUTING_ID = "id"
ROUTING_TOPIC = "topic"


def parse_subject(subject: str, expected_workflow_type: str) -> tuple[str, str] | None:
    """Parse external message subject into routing mode and detail.

    Subject pattern: messages.{workflow_type}.{routing}.{detail}

    Args:
        subject: NATS subject (e.g. messages.orders.topic.order.created)
        expected_workflow_type: Workflow type this runner handles

    Returns:
        (routing, detail) or None if subject does not match.
        routing: 'all' | 'tag' | 'id' | 'topic'
        detail: tag value, workflow_id, or topic depending on routing
    """
    if not subject.startswith(EXTERNAL_SUBJECT_PREFIX):
        return None
    parts = subject[len(EXTERNAL_SUBJECT_PREFIX) :].split(".", 2)
    if len(parts) < 3:
        return None
    workflow_type, routing, detail = (
        parts[0],
        parts[1],
        parts[2] if len(parts) > 2 else "",
    )
    if workflow_type != expected_workflow_type:
        return None
    if routing not in (ROUTING_ALL, ROUTING_TAG, ROUTING_ID, ROUTING_TOPIC):
        return None
    return (routing, detail)


async def resolve_workflow_ids(
    session_maker: async_sessionmaker[AsyncSession],
    routing: str,
    detail: str,
    workflow_type: str,
    db_event_model: Type[StoredEvent],
    db_external_sub_type: Type[Any] | None,
    db_workflow_metadata_model: Type[Any] | None,
    wf_id_rule: Callable[[str], bool] | None,
) -> list[str]:
    """Resolve target workflow IDs from routing mode and detail.

    Args:
        session_maker: Database session maker
        routing: 'all' | 'tag' | 'id' | 'topic'
        detail: Tag value, workflow_id, or topic depending on routing
        workflow_type: Workflow type name
        db_event_model: StoredEvent model (for fanout query)
        db_external_sub_type: ExternalSubscription model (for topic query), optional
        db_workflow_metadata_model: WorkflowMetadata model (for tag query), optional
        wf_id_rule: Optional filter for partitioning; workflow_id must pass this

    Returns:
        List of workflow IDs to deliver the message to.
    """
    workflow_ids: list[str] = []

    async with session_maker() as s:
        if routing == ROUTING_ALL:
            result = await s.execute(
                select(distinct(db_event_model.workflow_id)).where(
                    db_event_model.workflow_type == workflow_type
                )
            )
            workflow_ids = [row[0] for row in result.fetchall()]

        elif routing == ROUTING_TAG:
            if not db_workflow_metadata_model:
                logger.warning(
                    "Tag routing requested but db_workflow_metadata_model not set"
                )
            else:
                result = await s.execute(
                    select(db_workflow_metadata_model.workflow_id).where(
                        db_workflow_metadata_model.workflow_type == workflow_type,
                        db_workflow_metadata_model.tags.contains([detail]),
                    )
                )
                workflow_ids = [row[0] for row in result.fetchall()]

        elif routing == ROUTING_ID:
            workflow_ids = [detail] if detail else []

        elif routing == ROUTING_TOPIC:
            if not db_external_sub_type:
                logger.warning(
                    "Topic routing requested but db_external_sub_type not set"
                )
            else:
                result = await s.execute(
                    select(db_external_sub_type.workflow_id)
                    .where(
                        db_external_sub_type.workflow_type == workflow_type,
                        db_external_sub_type.topic == detail,
                    )
                    .distinct()
                )
                workflow_ids = [row[0] for row in result.fetchall()]

    if wf_id_rule:
        workflow_ids = [wid for wid in workflow_ids if wf_id_rule(wid)]
    return workflow_ids


class ExternalMessageConsumer:
    """Consumes external messages from NATS JetStream and routes them to workflows.

    Subscribes to messages.{workflow_type}.> and for each message:
    parses subject → (routing, detail), resolves workflow_ids, parses payload to EE,
    calls workflow.event_to_cmd(ee) then repo.process_command(workflow_id, cmd).
    """

    def __init__(
        self,
        nats_client: NATS,
        stream_name: str,
        consumer_name: str,
        workflow_type: str,
        workflow_type_class: Type[Any],
        repo: Any,
        session_maker: async_sessionmaker[AsyncSession],
        db_external_sub_type: Type[Any] | None,
        db_event_model: Type[StoredEvent],
        db_workflow_metadata_model: Type[Any] | None = None,
        parse_payload: Callable[[bytes], BaseModel] | Type[BaseModel] | None = None,
        wf_id_rule: Callable[[str], bool] | None = None,
        batch_size: int = 100,
        fetch_timeout: float = 1.0,
    ):
        """Initialize external message consumer.

        Args:
            nats_client: Connected NATS client
            stream_name: JetStream stream name for external messages
            consumer_name: Durable consumer name
            workflow_type: Workflow type name (must match runner)
            workflow_type_class: Workflow class (for event_to_cmd)
            repo: AsyncRepo instance (for process_command)
            session_maker: Database session maker (for resolve_workflow_ids)
            db_external_sub_type: ExternalSubscription model (for topic routing)
            db_event_model: StoredEvent model
            db_workflow_metadata_model: WorkflowMetadata model (optional, for tag routing)
            parse_payload: Callable(bytes -> EE) or Pydantic type; if type, payload is JSON
            wf_id_rule: Optional partition filter
            batch_size: Messages per fetch
            fetch_timeout: Timeout per fetch (seconds)
        """
        self._nc = nats_client
        self._stream_name = stream_name
        self._consumer_name = consumer_name
        self._workflow_type = workflow_type
        self._workflow_type_class = workflow_type_class
        self._repo = repo
        self._session_maker = session_maker
        self._db_external_sub_type = db_external_sub_type
        self._db_event_model = db_event_model
        self._db_workflow_metadata_model = db_workflow_metadata_model
        self._wf_id_rule = wf_id_rule
        self._batch_size = batch_size
        self._fetch_timeout = fetch_timeout

        if parse_payload is None:
            self._parse_payload = cast(
                Callable[[bytes], BaseModel | None], lambda b: None
            )
        elif isinstance(parse_payload, type) and issubclass(parse_payload, BaseModel):
            self._parse_payload = lambda b: parse_payload.model_validate_json(
                b.decode()
            )
        else:
            self._parse_payload = cast(
                Callable[[bytes], BaseModel | None], parse_payload
            )

        self._js = None
        self._subscription = None
        self._running = False
        self._consume_task = None

    async def __aenter__(self):
        """Create stream (if needed), consumer, and pull subscription."""
        self._js = self._nc.jetstream()
        subject_pattern = f"{EXTERNAL_SUBJECT_PREFIX}{self._workflow_type}.>"
        try:
            await self._js.add_stream(
                StreamConfig(
                    name=self._stream_name,
                    subjects=[subject_pattern],
                    max_age=86400,
                    storage=StorageType.FILE,
                    num_replicas=1,
                )
            )
            logger.info(f"Created external message stream: {self._stream_name}")
        except Exception:
            logger.debug(f"External stream already exists: {self._stream_name}")

        try:
            await self._js.add_consumer(
                stream=self._stream_name,
                config=ConsumerConfig(
                    durable_name=self._consumer_name,
                    deliver_policy=DeliverPolicy.ALL,
                    ack_policy=AckPolicy.EXPLICIT,
                    max_deliver=3,
                    ack_wait=30,
                ),
            )
        except Exception:
            logger.debug(f"External consumer already exists: {self._consumer_name}")

        self._subscription = await self._js.pull_subscribe(
            subject=subject_pattern, durable=self._consumer_name
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stop consume task and unsubscribe."""
        await self.stop()
        if self._subscription:
            await self._subscription.unsubscribe()
        return False

    async def start(self):
        """Start the background consume loop."""
        if self._running:
            return
        self._running = True
        self._consume_task = asyncio.create_task(self._consume_loop())
        logger.info(
            f"Started ExternalMessageConsumer for {self._workflow_type} "
            f"(stream={self._stream_name})"
        )

    async def stop(self):
        """Stop the background consume loop."""
        self._running = False
        if self._consume_task:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Stopped ExternalMessageConsumer for {self._workflow_type}")

    async def _consume_loop(self):
        """Fetch messages and process each; ack after successful processing."""
        while self._running:
            try:
                assert self._subscription is not None
                msgs = await self._subscription.fetch(
                    self._batch_size, timeout=self._fetch_timeout
                )
                for msg in msgs:
                    try:
                        await self._process_message(msg)
                        await msg.ack()
                    except Exception as e:
                        logger.exception(f"Failed to process external message: {e}")
                        await msg.nak()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"External message consume loop error: {e}")
                await asyncio.sleep(1.0)

    async def _process_message(self, msg):
        """Parse subject and payload, resolve workflow_ids, process_command for each."""
        subject = msg.subject
        parsed = parse_subject(subject, self._workflow_type)
        if not parsed:
            logger.warning(f"External message subject not matched: {subject}")
            return
        routing, detail = parsed

        workflow_ids = await resolve_workflow_ids(
            self._session_maker,
            routing,
            detail,
            self._workflow_type,
            self._db_event_model,
            self._db_external_sub_type,
            self._db_workflow_metadata_model,
            self._wf_id_rule,
        )
        if not workflow_ids:
            logger.debug(
                f"No target workflows for subject {subject} (routing={routing}, detail={detail})"
            )
            return

        payload = msg.data
        ee = self._parse_payload(payload)
        if ee is None:
            logger.warning(f"External message payload parsed to None: {subject}")
            return

        for workflow_id in workflow_ids:
            try:
                cmd = self._workflow_type_class.event_to_cmd(ee)
                if cmd is None:
                    continue
                await self._repo.process_command(workflow_id, cmd)
            except Exception as e:
                logger.exception(
                    f"process_command failed for workflow_id={workflow_id}: {e}"
                )
                raise
