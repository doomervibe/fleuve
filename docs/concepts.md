# Core concepts

## Workflow

A **workflow** is a long-running process: commands in, events out, state derived by reducing events. Implement `Workflow[E, C, S, EE]` with `decide` and `_evolve`. `event_to_cmd` and `is_final_event` have sensible defaults (no-op / `False`) and only need overriding when used.

## Events & commands

- **Commands** are external inputs (API, messages, timers).
- **Events** are immutable facts appended to the log. State changes only by applying events.

## State

Subclass **`StateBase`**. Built-in fields include subscriptions, external subscriptions, lifecycle, and schedules — plus your domain fields.

Use **`state.apply(**kwargs)`** as a shorthand for `state.model_copy(update={...})` in `_evolve`:

```python
def _evolve(state, event):
    if isinstance(event, EvChecked):
        return state.apply(last_checked_at=event.at)
```

## Subscriptions & delays

Cross-workflow subscriptions, NATS topics, delays, and cron use **built-in event types** (e.g. `EvSubscriptionAdded`, `EvDelay`, `EvScheduleAdded`) emitted from `decide`; the framework updates persistence and `_evolve_system` where applicable.

## Side effects

Put I/O in an **`Adapter`**: `act_on` is an async generator that may yield commands, checkpoints, or timeouts.

Use **`@handles`** to declare event-type routing declaratively instead of a manual dispatch dict:

```python
from fleuve import Adapter, handles, ActionContext

class MyAdapter(Adapter[MyEvent, MyCommand]):

    @handles(EvOrderPlaced)
    async def _on_placed(self, ev: EvOrderPlaced, context: ActionContext):
        await self.email.send(ev.customer_id)
        yield CmdMarkNotified(order_id=ev.order_id)
```

The framework generates `act_on` and `to_be_act_on` from the decorator registry. Each handler receives the **unwrapped domain event**, already typed.

## Typed Checkpoint

`context.checkpoint` is a `TypedCheckpoint` — a Pydantic-native `dict` subclass. Use `.load()` / `.save()` instead of raw string keys:

```python
class ScrapeProgress(BaseModel):
    urls: list[str]
    next_index: int = 0

@handles(EvScrapeRequested)
async def _scrape(self, ev, context: ActionContext):
    cp = context.checkpoint.load(ScrapeProgress) or ScrapeProgress(urls=ev.urls)
    async for i, url in context.checkpoint.iter(cp.urls, start=cp.next_index):
        await self._fetch(url)
        yield context.checkpoint.save(cp.model_copy(update={"next_index": i + 1}))
```

## Periodic tasks

Declare recurring tasks at the class level with **`PeriodicTask`** — no delay-id constants or manual rescheduling branches:

```python
from fleuve import Workflow, PeriodicTask
from datetime import timedelta

class VaultWorkflow(Workflow[...], periodic_tasks=[
    PeriodicTask(id="psyop_check",   interval=timedelta(hours=6),
                 first_run_after=timedelta(minutes=1)),
    PeriodicTask(id="daily_brief",   interval=timedelta(hours=24),
                 jitter=timedelta(minutes=10)),
]):
    ...
```

Use the injected classmethods in `decide`:

```python
if isinstance(cmd, CmdActivate):
    return [EvActivated(), *VaultWorkflow.schedule_periodic_tasks(state)]

if isinstance(cmd, CmdPeriodicTaskDue):
    return [EvWorkDue(), *VaultWorkflow.reschedule_periodic_task(cmd.task_id)]
```

Set `interval=timedelta(0)` to disable a task without removing it from the list.

## Structured logging

`context.logger` is a `ContextLogger` that auto-binds `workflow_id`, `event_number`, and `retry_count` to every record:

```python
context.logger.info("check done", alerts=3)
# log extra: {workflow_id: "vault:v1", event_number: 7, retry_count: 0, alerts: 3}
```

## Schema evolution

Bump **`schema_version`** and implement **`upcast`** on the workflow class when stored event JSON changes.

---

*Deeper detail: [README — Core Concepts](https://github.com/doomervibe/fleuve/blob/main/README.md#core-concepts).*
