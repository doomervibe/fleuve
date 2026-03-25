# Quick start

This page summarizes the **minimal pattern**; the repository README has extended examples.

## 1. Define events, commands, and state

Use Pydantic models: `EventBase` with a `Literal` `type` field, commands as `BaseModel`, state extending `StateBase`.

## 2. Implement `Workflow`

- `decide(state, cmd)` → events or `Rejection`
- `_evolve(state, event)` → new state
- `event_to_cmd`, `is_final_event`

## 3. Wire storage and runner

Use `fleuve.setup.create_workflow_runner` with your SQLAlchemy event/subscription/activity/delay/offset models, adapter, and env vars such as `DATABASE_URL`, `NATS_URL`, and `STORAGE_KEY`.

## 4. Run

Create workflows with `AsyncRepo.create_new`, then run `WorkflowsRunner.run()` (or your process model).

## Example project

Use the **[minimal example](https://github.com/doomervibe/fleuve/tree/main/examples/minimal)**:

```bash
cd examples/minimal
cp .env.example .env
docker compose up -d
poetry install   # fleuve is a path dependency to the repo root
poetry run python -m minimal_example
```

Scaffold a new app with the CLI:

```bash
fleuve startproject myapp
```

---

*Full walkthrough and snippets: [README — Quick Start](https://github.com/doomervibe/fleuve/blob/main/README.md#quick-start).*
