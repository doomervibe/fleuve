"""Main entry point for Sf2 workflows."""
import asyncio
import logging

from fleuve.setup import create_workflow_runner

# TODO: Import your workflows, models, and adapters
# Example:
# from workflows.order_processing.workflow import OrderProcessingWorkflow
# from workflows.order_processing.models import OrderProcessingState, CmdStartOrderProcessing
# from workflows.order_processing.adapter import OrderProcessingAdapter

from db_models import (
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
    """Run the Sf2 workflows."""
    logger.info("Starting Sf2 workflows...")

    # TODO: Set up workflow runners for each workflow
    # Example for a single workflow:
    """
    async with create_workflow_runner(
        workflow_type=OrderProcessingWorkflow,
        state_type=OrderProcessingState,
        adapter=OrderProcessingAdapter(),
        db_event_model=StoredEvent,
        db_subscription_model=Subscription,
        db_activity_model=Activity,
        db_delay_schedule_model=DelaySchedule,
        db_offset_model=Offset,
    ) as resources:
        repo = resources.repo
        runner = resources.runner

        # Create a workflow instance
        workflow_id = "order-1"
        result = await repo.create_new(
            cmd=CmdStartOrderProcessing(),
            workflow_id=workflow_id,
        )

        if hasattr(result, "state"):
            logger.info(f"✓ Workflow created: {workflow_id}")
            logger.info(f"  State: {result.state}")
        else:
            logger.error(f"✗ Failed to create workflow: {result}")
            return

        # Run the workflow runner
        logger.info("Running workflow runner... Press Ctrl+C to stop.")
        try:
            await runner.run()
        except KeyboardInterrupt:
            logger.info("Stopping workflow runner...")
    """
    
    # For multiple workflows, consider:
    # - Running them in separate tasks with asyncio.gather()
    # - Using a shared database session maker
    # - Managing lifecycle with asyncio.TaskGroup (Python 3.11+)
    
    logger.info("TODO: Implement your workflow runners")


if __name__ == "__main__":
    asyncio.run(main())
