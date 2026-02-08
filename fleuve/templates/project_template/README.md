# {{project_title}}

A Fleuve workflow project.

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

4. **Run the workflow:**
   ```bash
   python main.py
   ```

## Project Structure

```
{{project_name}}/
├── {{project_name}}/
│   ├── __init__.py
│   ├── models.py          # Events, Commands, State
│   ├── workflow.py        # Workflow definition
│   ├── adapter.py         # Side effects/adapter
│   └── db_models.py       # SQLAlchemy models
├── main.py                # Entry point
├── pyproject.toml         # Project configuration
└── docker-compose.yml     # PostgreSQL + NATS setup
```

## Development

- Edit `{{project_name}}/models.py` to define your events, commands, and state
- Edit `{{project_name}}/workflow.py` to implement your workflow logic
- Edit `{{project_name}}/adapter.py` to add side effects
- Edit `main.py` to customize how workflows are created and run

## Documentation

See the [Fleuve documentation](https://github.com/doomervibe/fleuve#readme) for more information.
