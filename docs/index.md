# Fleuve

**Fleuve** (French for “river”) is a type-safe, production-oriented workflow framework for Python: durable execution, event sourcing, PostgreSQL-backed history, NATS for ephemeral state, horizontal scaling, and Pydantic-first APIs.

## Highlights

- **Event sourcing** — Events are the source of truth; replay and auditability come naturally.
- **Your PostgreSQL** — Full event history and SQL access in your own database.
- **Long-running** — Delays, cron, subscriptions, and retries without a dedicated workflow server.
- **`@handles` decorator** — Declare event routing on `Adapter` methods; framework generates `act_on` automatically.
- **`PeriodicTask`** — Recurring tasks as a first-class primitive; no delay-id boilerplate.
- **`TypedCheckpoint`** — Pydantic-native checkpoint API; replaces raw string-keyed dicts in handlers.
- **`WorkflowTestHarness`** — Full workflow tests with no database or NATS; advance simulated time with `advance(hours=)`.
- **`FleuveApp`** — Multi-workflow registry; one engine and one NATS connection shared across all workflow types.
- **`context.logger`** — Structured logger auto-bound to `workflow_id`, `event_number`, and `retry_count`.

## Why Fleuve?

Compared to hosted workflow engines, Fleuve runs **as a Python library** with **PostgreSQL + NATS** you already operate. See the [comparison table](installation.md#why-fleuve-vs-temporal) on the Installation page.

## Where to go next

| Goal | Page |
|------|------|
| Install and prerequisites | [Installation](installation.md) |
| Minimal runnable app | [Quick start](quick-start.md) |
| Workflows, events, `@handles`, `PeriodicTask` | [Core concepts](concepts.md) |
| Testing without a database | [Testing workflows](testing.md) |
| Multiple runners / partitions | [Partitioning & scaling](scaling.md) |
| Everything in one file | [Full README on GitHub](readme.md) |

The [GitHub repository](https://github.com/doomervibe/fleuve) remains the home for issues, releases, and the full long-form README until more content is migrated here.
