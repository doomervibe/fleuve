# Testing workflows

`WorkflowTestHarness` runs full decide→evolve cycles in memory with no database or NATS connection.
It is suitable for fast unit and integration tests of complete workflow logic.

## Basic usage

```python
from fleuve.testing import WorkflowTestHarness

harness = WorkflowTestHarness(VaultWorkflow)

# Create a workflow instance
ss, events = await harness.create_new("vault-1", CmdActivate(vault_id="v1"))
assert ss.state.lifecycle == "active"

# Send subsequent commands
ss, events = await harness.send_command("vault-1", CmdPsyopCheckDone(vault_id="v1"))
```

## Simulating time (`advance`)

Pending `EvDelay` events fire when the simulated clock passes their `delay_until`:

```python
# Fires all delays due within the next 6 hours
await harness.advance(hours=6)

# Or with finer granularity
await harness.advance(minutes=30, seconds=15)
```

After `advance`, the harness processes each fired delay through `event_to_cmd` → `send_command`
in chronological order.

## Asserting emitted events

`emitted(EventType)` returns all events of that type produced since harness creation
(across `create_new`, `send_command`, and delay-fired calls):

```python
await harness.create_new("vault-1", CmdActivate(vault_id="v1"))
await harness.advance(hours=6)

assert len(harness.emitted(EvPsyopCheckRequested)) == 1
assert len(harness.emitted(EvEntityReconcileRequested)) == 0  # not due yet
```

Use `clear_event_log()` between assertion phases when you want per-cycle counts:

```python
harness.clear_event_log()
await harness.advance(hours=12)
assert len(harness.emitted(EvEntityReconcileRequested)) == 1
```

## Testing adapter side effects (`run_handler`)

Run an adapter's `act_on` and collect the commands it yields — no database or NATS needed:

```python
commands = await harness.run_handler(
    EvPsyopCheckRequested(vault_id="v1"),
    VaultAdapter(settings),
    workflow_id="vault-1",
)
assert any(isinstance(c, CmdPsyopCheckDone) for c in commands)
```

`CheckpointYield` and `ActionTimeout` values are consumed silently and do not appear in the
returned list.  You can pass an initial `checkpoint` dict and `retry_count`:

```python
commands = await harness.run_handler(
    event,
    adapter,
    workflow_id="vault-1",
    checkpoint={"next_index": 3},
    retry_count=1,
)
```

## What-if simulation (`simulate`)

Apply a command without mutating harness state — useful for validating rejections or
previewing what events *would* be emitted:

```python
result = harness.simulate("vault-1", CmdDisable())
if isinstance(result, Rejection):
    print("rejected:", result.msg)
else:
    ss, events = result
    print("would emit:", events)
```

## Asserting subscriptions

```python
harness.assert_subscriptions("vault-1", [
    Sub(workflow_id="*", event_type="order.*"),
])
```

## Full API reference

| Method / property | Description |
|-------------------|-------------|
| `create_new(id, cmd, tags=None)` | Create a new workflow instance; returns `(StoredState, events)` or `Rejection` |
| `send_command(id, cmd)` | Process a command; returns `(StoredState, events)` or `Rejection` |
| `simulate(id, cmd)` | What-if — no state mutation |
| `advance(hours=, minutes=, seconds=)` | Fire pending delays within the given offset |
| `advance_time(delta)` | Same as `advance` with an explicit `timedelta` |
| `emitted(EventType)` | Events of that type in the log |
| `clear_event_log()` | Reset the event log |
| `run_handler(event, adapter, *, workflow_id, …)` | Run adapter `act_on`, return yielded commands |
| `get_state(id)` | Current `StoredState`; raises `KeyError` if not found |
| `assert_subscriptions(id, expected)` | Assert `Sub` list; raises `AssertionError` on mismatch |
| `workflow_ids` | All tracked workflow IDs |
| `pending_delays` | Read-only list of `_PendingDelay` |
| `event_log` | All emitted events in order |

## Limitations

- No persistence — state is lost when the harness is garbage-collected.
- `act_on` is **not** called by `send_command`; use `run_handler` to test adapters explicitly.
- No real NATS or database connectivity.
- Cron reschedule requires `croniter` to be installed.
