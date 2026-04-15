# Quick start

This page summarizes the **minimal pattern**; the repository README has extended examples.

## 1. Define events, commands, and state

Use Pydantic models: `EventBase` with a `Literal` `type` field, commands as `BaseModel`, state extending `StateBase`.

## 2. Implement `Workflow`

- `decide(state, cmd)` → events or `Rejection`
- `_evolve(state, event)` → new state
- `event_to_cmd` and `is_final_event` have default implementations (no-op / `False`); override only when needed.

## 3. Wire storage and runner

**Single workflow** — use `fleuve.setup.create_workflow_runner`:

```python
async with create_workflow_runner(
    workflow_type=MyWorkflow,
    state_type=MyState,
    adapter=MyAdapter(),
    db_event_model=MyEvent,
    db_subscription_model=MySub,
    db_activity_model=MyActivity,
    db_delay_schedule_model=MyDelay,
    db_offset_model=MyOffset,
) as resources:
    await resources.runner.run()
```

**Multiple workflows** — use `FleuveApp` to share one engine and one NATS connection:

```python
from fleuve.app import FleuveApp

app = FleuveApp()  # reads DATABASE_URL / NATS_URL from env
app.register("domain", DomainWorkflow, DomainAdapter(), DomainState, ...models...)
app.register("vault",  VaultWorkflow,  VaultAdapter(),  VaultState,  ...models...)

async with app.runners() as runners:
    await asyncio.gather(*(r.run() for r in runners.values()))
```

## 4. Add handler routing with `@handles`

Instead of implementing `act_on` manually, use the decorator:

```python
from fleuve import Adapter, handles, ActionContext

class MyAdapter(Adapter[MyEvent, MyCommand]):

    @handles(EvOrderPlaced)
    async def _on_placed(self, ev: EvOrderPlaced, context: ActionContext):
        await self.send_email(ev.customer_id)
        yield CmdMarkNotified(order_id=ev.order_id)
```

## 5. Run

Create workflows with `AsyncRepo.create_new` (or `repo.upsert` for idempotent create-or-update),
then run `WorkflowsRunner.run()`.

```python
# Idempotent: creates if new, applies command if already exists
await resources.repo.upsert("order-123", CmdPlaceOrder(...))

# Idempotent bootstrap: creates if missing, no-op if already active
await resources.repo.ensure("order-123", init_cmd=CmdActivate(...))
```

## 6. Test with `WorkflowTestHarness`

No database or NATS required for workflow logic tests:

```python
from fleuve.testing import WorkflowTestHarness

harness = WorkflowTestHarness(VaultWorkflow)
await harness.create_new("vault-1", CmdActivate(vault_id="v1"))

await harness.advance(hours=6)
assert len(harness.emitted(EvPsyopCheckRequested)) == 1

# Test adapter side-effects
commands = await harness.run_handler(
    EvPsyopCheckRequested(vault_id="v1"), VaultAdapter(settings),
    workflow_id="vault-1",
)
```

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
