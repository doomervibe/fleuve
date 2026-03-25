---
name: fleuve-runner-infra
description: >-
  Guides Fleuve runtime and scaling: WorkflowsRunner, WorkflowConfig, NATS/JetStream
  readers, partitioning, load_fleuve_toml. Use when editing fleuve/runner.py,
  fleuve/config.py, partitioning, deployment, horizontal scaling, or when the user
  mentions Fleuve runner, JetStream, offsets, or partitioned workers.
---

# Fleuve runner and infrastructure

## Entry points

- **`WorkflowsRunner`** (`fleuve/runner.py`): Main loop coordinating readers, dispatch, `SideEffects`, delay scheduling, and optional external messaging. Prefer reading this file in sections rather than all at once (~700 lines).
- **`make_runner_from_config`** (`fleuve/config.py`): Builds a single runner from `WorkflowConfig` + `AsyncRepo` + `session_maker`. Parameters include JetStream (`jetstream_enabled`, `nats_client`, `jetstream_stream_name`), `max_inflight`, `max_events_per_second`, `reader_name`, external messaging, `batch_size`.
- **`make_partitioned_runner_from_config`** (`fleuve/config.py`): One runner per **`PartitionedRunnerConfig`** (partition rule + reader name). Validates workflow type matches.
- **`load_fleuve_toml`** (`fleuve/config.py`): Loads `[fleuve]` TOML; `FLEUVE_*` env overrides. See docstring for keys (`database_url`, `nats_url`, snapshot/truncation, `max_inflight`, etc.).

## Partitioning

- **`fleuve/partitioning.py`**: `make_hash_partition_rule`, `make_reader_name`, `PartitionedRunnerConfig`, `create_partitioned_configs` (see module docstring).
- Human-oriented design notes: **`PARTITIONING.md`** in the Fleuve repository (also shipped in sdist).

## Operational cautions

- **Do not assume** a single process owns all workflows if partitioning or multiple runners are in use—each partition uses `wf_id_rule` / reader names to scope work.
- **JetStream** vs non-JetStream reader behavior differs (`Readers` in `fleuve/stream.py`); check flags passed from `make_runner_from_config`.
- Rate limiting: `TokenBucket` / `max_events_per_second` in runner—changing concurrency affects ordering and load on Postgres/NATS.

## File map

See [reference.md](reference.md) for a compact pointer list.

## Related skills

- Workflow semantics: **fleuve-workflow-authoring** skill (install with `fleuve cursor-skills install`)
- Deployment narrative: `README.md` (Production Deployment, Horizontal Scaling)
