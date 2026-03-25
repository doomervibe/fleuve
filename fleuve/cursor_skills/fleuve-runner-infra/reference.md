# Runner / infra file pointers

| Topic | Location |
|-------|----------|
| Main runner class | `fleuve/runner.py` — `WorkflowsRunner`, `SideEffects`, `TokenBucket`, `InflightTracker` |
| Config factory + TOML | `fleuve/config.py` — `WorkflowConfig`, `make_runner_from_config`, `make_partitioned_runner_from_config`, `load_fleuve_toml` |
| Partition helpers | `fleuve/partitioning.py` |
| Event readers / JetStream glue | `fleuve/stream.py` — `Readers`, `Reader` |
| Repo (persistence) | `fleuve/repo.py` — `AsyncRepo` |
| Actions execution | `fleuve/actions.py` — `ActionExecutor` |
| Delays | `fleuve/delay.py` — `DelayScheduler` |
| External NATS messages | `fleuve/external_messaging.py` |

**WorkflowConfig** (dataclass) holds `nats_bucket`, SQLAlchemy model types, `adapter`, optional `sync_db`, snapshot/truncation fields, `tracer`, external messaging fields, etc.—inspect `fleuve/config.py` when adding options.
