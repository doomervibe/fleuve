# {{project_title}}

A multi-workflow Fleuve project with shared database tables.

## Setup

1. **Install dependencies:**
   ```bash
   pip install -e .
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start infrastructure:**
   ```bash
   docker-compose up -d
   ```

4. **Run the workflows:**
   ```bash
   python main.py
   ```

## Project Structure

```
{{project_name}}/
├── workflows/
│   └── (workflow folders here)
├── db_models.py           # Shared database models for ALL workflows
├── main.py                # Entry point
├── pyproject.toml         # Project configuration
└── docker-compose.yml     # PostgreSQL + NATS setup
```

## Multi-Workflow Architecture

This project uses a **shared database architecture** where all workflows store their events, subscriptions, and activities in the same database tables:

- `events` - Stores events from ALL workflow types
- `subscriptions` - Cross-workflow subscriptions
- `activities` - Action execution tracking
- `delay_schedules` - Delayed operations
- `offsets` - Stream reader positions

The `workflow_type` column in each table distinguishes between different workflows.

## Adding a New Workflow

You can add new workflows using the CLI:

```bash
fleuve addworkflow payment
```

Or manually:

1. **Create workflow folder:**
   ```bash
   mkdir -p workflows/payment
   ```

2. **Add workflow files:**
   - `workflows/payment/__init__.py`
   - `workflows/payment/models.py` - Events, Commands, State
   - `workflows/payment/workflow.py` - Workflow logic
   - `workflows/payment/adapter.py` - Side effects

3. **Update `db_models.py`:**
   ```python
   # Import the new workflow types
   from workflows.payment.models import PaymentEvent, PaymentCommand
   
   # Add to unions
   AllEvents = ExistingEvent | PaymentEvent
   AllCommands = ExistingCommand | PaymentCommand
   ```

4. **Update `main.py`:**
   - Import the new workflow, state, and adapter
   - Create a workflow runner for it
   - Consider running multiple workflows concurrently

## Development

- Each workflow is independent with its own models, logic, and adapter
- Workflows can communicate through cross-workflow subscriptions
- Use the `workflow_type` to filter events by workflow
- All workflows share the same infrastructure (PostgreSQL, NATS)

## Documentation

See the [Fleuve documentation](https://github.com/doomervibe/fleuve#readme) for more information.
