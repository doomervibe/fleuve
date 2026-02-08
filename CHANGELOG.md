# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial public release preparation

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
