# Core concepts

## Workflow

A **workflow** is a long-running process: commands in, events out, state derived by reducing events. Implement `Workflow[E, C, S, EE]` with `decide`, `_evolve`, `event_to_cmd`, and `is_final_event`.

## Events & commands

- **Commands** are external inputs (API, messages, timers).
- **Events** are immutable facts appended to the log. State changes only by applying events.

## State

Subclass **`StateBase`**. Built-in fields include subscriptions, external subscriptions, lifecycle, and schedules—plus your domain fields.

## Subscriptions & delays

Cross-workflow subscriptions, NATS topics, delays, and cron use **built-in event types** (e.g. `EvSubscriptionAdded`, `EvDelay`, `EvScheduleAdded`) emitted from `decide`; the framework updates persistence and `_evolve_system` where applicable.

## Side effects

Put I/O in an **`Adapter`**: `act_on` is an async generator that may yield commands, checkpoints, or timeouts.

## Schema evolution

Bump **`schema_version`** and implement **`upcast`** on the workflow class when stored event JSON changes.

---

*Deeper detail: [README — Core Concepts](https://github.com/doomervibe/fleuve/blob/main/README.md#core-concepts).*
