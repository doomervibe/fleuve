"""Run the minimal Fleuve example: create one workflow and process events."""
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

# Encrypted columns require STORAGE_KEY before importing DB models.
os.environ.setdefault("STORAGE_KEY", "test-storage-key-32-characters-long!")

# Register SQLAlchemy models on Base.metadata before create_workflow_runner runs create_all.
from minimal_example.db_models import (  # noqa: E402
    Activity,
    DelaySchedule,
    Offset,
    StoredEvent,
    Subscription,
)

from fleuve.setup import create_workflow_runner  # noqa: E402

from minimal_example.adapter import MinimalAdapter  # noqa: E402
from minimal_example.models import CmdStartMinimal, MinimalState  # noqa: E402
from minimal_example.workflow import MinimalWorkflow  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Starting minimal Fleuve example...")

    async with create_workflow_runner(
        workflow_type=MinimalWorkflow,
        state_type=MinimalState,
        adapter=MinimalAdapter(),
        db_event_model=StoredEvent,
        db_subscription_model=Subscription,
        db_activity_model=Activity,
        db_delay_schedule_model=DelaySchedule,
        db_offset_model=Offset,
    ) as resources:
        repo = resources.repo
        runner = resources.runner

        workflow_id = "minimal-demo-1"
        result = await repo.create_new(
            cmd=CmdStartMinimal(),
            id=workflow_id,
        )

        if hasattr(result, "state"):
            logger.info("Workflow created: %s state=%s", workflow_id, result.state)
        else:
            logger.error("Failed to create workflow: %s", result)
            return

        logger.info("Runner started (Ctrl+C to stop).")
        try:
            await runner.run()
        except KeyboardInterrupt:
            logger.info("Stopping runner.")


if __name__ == "__main__":
    asyncio.run(main())
