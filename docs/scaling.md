# Partitioning & scaling

Fleuve scales by running **multiple runner processes**, each responsible for **one partition** of workflow IDs (typically hash-based). Each process must run **only** its partition’s workflows.

## Essentials

- Use **`PartitionedRunnerConfig`** and **`make_partitioned_runner_from_config`** (or env-driven wiring) so each process gets a `partition_index` and `total_partitions`.
- Workflow IDs are assigned to partitions with a **stable hash** (see `fleuve.partitioning.make_hash_partition_rule`).
- When changing partition count, use the framework’s **scaling** helpers and follow the full guide so offsets and ownership stay consistent.

## Full guide

The complete partitioning and scaling guide (quick start, env vars, scaling up/down, operations) is maintained in the repo:

**[PARTITIONING.md](https://github.com/doomervibe/fleuve/blob/main/PARTITIONING.md)** (GitHub)

---

*Related README section: [Horizontal Scaling](https://github.com/doomervibe/fleuve/blob/main/README.md#horizontal-scaling).*
