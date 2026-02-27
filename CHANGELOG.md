# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Cron scheduling**: Recurring delays via `EvDelay.cron_expression` and `EvDelay.timezone`. Use croniter-compatible expressions (e.g. `0 9 * * *` for daily at 9am). The DelayScheduler automatically re-inserts the next occurrence after each fire. Fleuve UI displays next 5 cron fire times.
- **Fleuve UI in main package**: Run `fleuve ui` from the CLI to start the web UI. Built-in default models allow connecting to any Fleuve database. Use `python scripts/build_ui.py` to build frontend assets.
- **Command Gateway** (`FleuveCommandGateway`): HTTP API for workflow commands (create, process, pause, resume, cancel, retry failed action)
- **Lifecycle Management**: `EvSystemPause`, `EvSystemResume`, `EvSystemCancel`; `StateBase.lifecycle`; `AsyncRepo.pause_workflow`, `resume_workflow`, `cancel_workflow`
- **Workflow Versioning**: `schema_version` on StoredEvent, `Workflow.upcast()` for schema evolution
- **Dead Letter Queue**: `ActionExecutor.retry_failed_action`, POST retry endpoint, `on_action_failed` callback
- **OpenTelemetry Tracing**: `FleuveTracer`, optional instrumentation for process_command, load_state, execute_action, Readers
- **Snapshots & Event Truncation**: Automatic state snapshots at configurable intervals; `TruncationService` for safe event deletion
- **Event Replay & Simulate**: State reconstruction in UI API; POST `/api/workflows/{id}/replay` and `/simulate` endpoints
- **Fleuve UI Command Gateway**: Mount command gateway in UI backend via `repos` and `command_parsers` in `create_app`

### Changed
- **NATS JetStream required**: Ephemeral state caching and delay scheduling require NATS with JetStream enabled. Use `nats -js` when starting NATS.
- **zstandard**: Now an explicit dependency (used for encrypted event compression).
- **httpx**: Added to dev dependencies for FastAPI TestClient in gateway tests.

## [0.1.0] - 2026-01-19

### Added
- Initial release of Fleuve event sourcing framework
- Core workflow pattern implementation with `Workflow`, `EventBase`, `StateBase`
- Event sourcing with PostgreSQL backend
- Ephemeral state caching with NATS Key-Value store
- Side effects handling via `Adapter` pattern
- Action executor with automatic retry logic and exponential backoff
- Checkpoint/resume functionality for long-running actions
- Delay scheduling with `EvDelay` and `EvDelayComplete` events
- Cross-workflow communication via subscriptions
- Direct message support for inter-workflow events
- Horizontal scaling with hash-based partitioning
- Partition rebalancing utilities for scaling operations
- Type-safe implementation using Pydantic
- Comprehensive test suite (131 tests)
- Traffic fine workflow example demonstrating full framework capabilities
- Fleuve UI for monitoring and debugging workflows
- Complete documentation with step-by-step tutorial

### Technical Details
- Python 3.13+ support
- Async/await throughout
- Full type hints with mypy support
- SQLAlchemy 2.0+ async support
- Pydantic 2.x for validation
- Event encryption support
- Activity tracking for side effects
- Offset tracking for event stream readers
- Recovery mechanisms for interrupted actions

[Unreleased]: https://github.com/doomervibe/fleuve/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/doomervibe/fleuve/releases/tag/v0.1.0
