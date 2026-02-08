"""Main entry point for {{project_title}} workflow."""
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from fleuve.setup import create_workflow_runner

from {{project_name}}.workflow import {{workflow_name}}
from {{project_name}}.models import {{state_name}}, CmdStart{{project_title_no_spaces}}
from {{project_name}}.adapter import {{project_title_no_spaces}}Adapter
from {{project_name}}.db_models import (
    StoredEvent,
    Subscription,
    Activity,
    DelaySchedule,
    Offset,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Run the {{project_title}} workflow."""
    logger.info("Starting {{project_title}} workflow...")

    async with create_workflow_runner(
        workflow_type={{workflow_name}},
        state_type={{state_name}},
        adapter={{project_title_no_spaces}}Adapter(),
        db_event_model=StoredEvent,
        db_subscription_model=Subscription,
        db_activity_model=Activity,
        db_delay_schedule_model=DelaySchedule,
        db_offset_model=Offset,
    ) as resources:
        repo = resources.repo
        runner = resources.runner

        # Create a workflow instance
        workflow_id = "{{project_name}}-1"
        result = await repo.create_new(
            cmd=CmdStart{{project_title_no_spaces}}(),
            id=workflow_id,
            # Optional: Add tags for tag-based event subscriptions
            # tags=["production", "high-priority"],
        )

        if hasattr(result, "state"):
            logger.info(f"✓ Workflow created: {workflow_id}")
            logger.info(f"  State: {result.state}")
        else:
            logger.error(f"✗ Failed to create workflow: {result}")
            return

        # Run the workflow runner to process events
        logger.info("Running workflow runner... Press Ctrl+C to stop.")
        try:
            await runner.run()
        except KeyboardInterrupt:
            logger.info("Stopping workflow runner...")


if __name__ == "__main__":
    asyncio.run(main())
