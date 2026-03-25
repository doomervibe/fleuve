---
name: fleuve-workflow-authoring
description: >-
  Guides implementation and review of Fleuve workflows (EventBase, StateBase,
  Workflow.decide/_evolve, subscriptions, delays, Adapter). Use when adding or
  changing workflow definitions, events, commands, state, schema_version/upcast,
  or Fleuve event sourcing in a project using Fleuve.
---

# Fleuve workflow authoring

## Core invariants

- **Commands** enter through `Workflow.decide(state, cmd)` → returns `list[E] | Rejection`. No domain state mutation inside `decide` except by returning events.
- **State** updates by applying events: `Workflow.evolve` runs `_evolve_system` first (built-in subscription/lifecycle/schedule events), then user `_evolve` for domain events. See `fleuve/model.py` (`Workflow.evolve`, `_evolve_system`, `_evolve`).
- **Persisted state** is the reduction of the event log; keep `_evolve` deterministic and free of I/O.
- **`event_to_cmd`** maps external events (type `EE`) to commands for this workflow; **`is_final_event`** marks terminal domain events.

## StateBase

- Subclass `StateBase` and add domain fields. Required: **`subscriptions`** (list of `Sub`). Also inherited: `external_subscriptions`, `lifecycle`, `schedules`.
- Initialize subscriptions in `_evolve` when creating state from `None` (see README examples). Framework sync events (`EvSubscriptionAdded`, etc.) update subscription-related fields via `_evolve_system`—do not duplicate that logic in `_evolve` unless you have a deliberate reason.

## Events

- Concrete events must declare **`type: Literal["..."] = "..."`** (validated in `EventBase.__init_subclass__`).
- Optional: **`metadata_`** on events is injected by the repo; exclude from schema (`exclude=True` on `EventBase`).
- **Schema evolution:** bump `Workflow.schema_version` and implement `upcast(event_type, schema_version, raw_data) -> dict` when stored JSON shape changes.

## Subscriptions, delays, schedules

- Emit **`EvSubscriptionAdded` / `EvSubscriptionRemoved`**, **`EvExternalSubscriptionAdded` / `EvExternalSubscriptionRemoved`** from `decide` to change subscription tables and state consistently.
- Delays: subclass **`EvDelay`** with `next_cmd`; recurring use `cron_expression` / **`EvScheduleAdded`** / **`EvCancelSchedule`** as appropriate. **`EvDelayComplete`** is emitted by the system when a delay fires.
- Built-in event roles and emitters: see [reference.md](reference.md).

## Side effects (Adapter)

- Implement **`Adapter.act_on`** as an **async generator** yielding `Command`, `CheckpointYield`, or `ActionTimeout`. Commands are processed via `process_command` for the workflow. Implement **`to_be_act_on`** to select which events run actions.
- Optional **`Adapter.sync_db`** for denormalized data in the same transaction as event insert (must not commit).

## Anti-patterns

- Non-deterministic or I/O in `_evolve` or `decide`.
- Manually editing `state.subscriptions` for cases the framework handles via sync events (see `_evolve_system`).
- Forgetting `Rejection` / empty event list rules on create paths (`WorkflowTestHarness` rejects create with no events).

## File map

| Area | Location |
|------|----------|
| Core model | `fleuve/model.py` |
| Repository API | `fleuve/repo.py` |
| Runner loop / side effects | `fleuve/runner.py` (see fleuve-runner-infra skill) |
| High-level architecture | `README.md` |

## Checklists

**New workflow type**

- [ ] `name()`, event/command/state types wired as `Workflow[E, C, S, EE]`
- [ ] `decide`, `_evolve`, `event_to_cmd`, `is_final_event`
- [ ] State extends `StateBase`; initial state handles `state is None`
- [ ] Registration / runner wiring if applicable (app code or template)

**New domain event**

- [ ] Literal `type` field; Pydantic model consistent with persistence
- [ ] Handled in `_evolve`; system events delegated to super path only if needed
- [ ] If stored shape changes: `schema_version` + `upcast`

**Breaking persisted schema**

- [ ] `upcast` for old `raw_data`
- [ ] Consider snapshots / truncation policies (`WorkflowConfig` in `fleuve/config.py`) for large histories

## Additional resources

- Built-in event reference: [reference.md](reference.md)
- Continue-as-new / log reset: `EvContinueAsNew` in `fleuve/model.py` and repo `continue_as_new` usage
