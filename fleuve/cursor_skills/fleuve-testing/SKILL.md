---
name: fleuve-testing
description: >-
  Guides tests using Fleuve WorkflowTestHarness (in-memory decide/evolve, delays,
  subscriptions). Use when writing or reviewing Fleuve workflow tests, pytest
  async tests, or when the user mentions WorkflowTestHarness, harness tests, or
  fast workflow unit tests without Postgres/NATS.
---

# Fleuve testing (WorkflowTestHarness)

## When to use what

- **`WorkflowTestHarness`** (`fleuve/testing.py`): Fast, in-memory **decide → evolve** cycles. No PostgreSQL, no NATS. Use for workflow logic, subscriptions state, and simulated time / delays.
- **Integration tests** (project tests with real `TEST_DATABASE_URL` / `TEST_NATS_URL`): Persistence, repo, JetStream readers, `Adapter.act_on` side effects, and full runner behavior.

## Harness limitations (do not forget)

- **`Adapter.act_on` is not executed**—no real side effects, no action retries. Cover those with integration tests.
- No persistence; state lives until the harness is discarded.

## API sketch

Construct with `WorkflowTestHarness(MyWorkflow)` (see `fleuve/testing.py`).

| Method | Purpose |
|--------|---------|
| `create_new(workflow_id, cmd, tags=None)` | First command; returns `(StoredState, events)` or `Rejection` |
| `send_command(workflow_id, cmd)` | Further commands |
| `advance_time(delta)` | Fire pending delays with `fire_at` ≤ now + delta |
| `assert_subscriptions(workflow_id, expected_subs)` | Assert `Sub` list |
| `simulate(workflow_id, cmd)` | What-if without mutating harness state |
| `get_state(workflow_id)` | Current `StoredState` |

Use async tests; Fleuve uses `pytest-asyncio` with `asyncio_mode = auto` (see upstream `pytest.ini` in the Fleuve repo).

## Checklist for new harness tests

- [ ] Assert both rejection paths and success paths where relevant
- [ ] If testing delays: call `advance_time` and then assert state or follow-up commands
- [ ] If asserting subscriptions: use `Sub(...)` values that match `decide` output
- [ ] Add integration coverage if the change touches `act_on`, repo, or runner

## Related

- Workflow rules: the **fleuve-workflow-authoring** Cursor skill (install with `fleuve cursor-skills install`)
- Fleuve library tests fixtures: see `fleuve/tests/conftest.py` in the Fleuve repository
