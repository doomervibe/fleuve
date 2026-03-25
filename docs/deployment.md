# Production deployment

High-level topics you should plan for:

- **PostgreSQL**: sizing, backups, migrations (Alembic), connection pools
- **NATS**: JetStream durability, cluster sizing, connectivity from all runners
- **Runners**: one or more `WorkflowsRunner` processes; [partitioning](scaling.md) for horizontal scale
- **Secrets**: `STORAGE_KEY` and DB URLs via env or secret stores
- **Observability**: optional OpenTelemetry (`otel` extra), metrics in `fleuve.metrics`

---

*Detailed notes: [README — Production Deployment](https://github.com/doomervibe/fleuve/blob/main/README.md#production-deployment).*
