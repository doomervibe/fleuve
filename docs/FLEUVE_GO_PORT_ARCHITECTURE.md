# Fleuve Go port — architecture and execution plan

**Repository:** `github.com/doomervibe/fleuve` (Python source of truth: `fleuve/*.py`, `fleuve/tests/`).  
**Branch / deadline:** set per team.  
**Out of scope for initial milestones (unless agreed):** Python project scaffolding in `fleuve/cli.py` (Click templates); optional parity of every CLI subcommand before runner/gateway/UI are complete.

This document satisfies deliverable **(1) architecture** and **(4) migration notes / compatibility matrix** from the Go port specification.

---

## 1. Goals and constraints


| Constraint                 | Implication                                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **UI unchanged**           | Do not modify `fleuve/ui/frontend_dist/` or `scripts/build_ui.py`. Go serves the same paths: `/assets`, SPA `index.html`, `{{project_title}}` substitution, catch-all for client routing.                                                                                                                                                                                                     |
| **Wire-compatible HTTP**   | `fleuve/ui/backend/api.py` and `fleuve/gateway.py` define normative routes, status codes, and JSON shapes (`fleuve/ui/backend/models.py`).                                                                                                                                                                                                                                                    |
| **CORS (no static build)** | When static files are absent, allow `http://localhost:3000` and `http://localhost:5173` (mirror `FleuveUIBackend._setup_static_files`).                                                                                                                                                                                                                                                       |
| **Data compatibility**     | Same PostgreSQL tables and JSON payloads: events (`body`, `metadata`), activities (`checkpoint`, `retry_policy`), delays (`next_comman d`), subscriptions, snapshots, offsets, scaling rows, etc. Encrypted columns use **AES-256-CBC** + optional `**zstd:`** prefix per `EncryptedPydanticType` in `fleuve/postgres.py` — Go must implement identical decrypt/decompress before JSON parse. |
| **No silent API changes**  | Additive Go-only types are fine; changing field names or semantics requires an explicit compatibility break policy.                                                                                                                                                                                                                                                                           |


---

## 2. Python → Go module mapping


| Python                                              | Go package (proposed under `go/`)                | Notes                                                                                                                                      |
| --------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `fleuve/model.py`                                   | `internal/model` or `pkg/fleuve`                 | Workflows as user-registered types; `Workflow` interface with `Decide`, `Evolve`, `Name`, …                                                |
| `fleuve/postgres.py`                                | `internal/pgmodel` + `internal/crypto`           | Structs + column tags; encryption/zstd compatibility.                                                                                      |
| `fleuve/repo.py`                                    | `internal/repo`                                  | Transactions, optimistic concurrency, command processing.                                                                                  |
| `fleuve/stream.py`, `jetstream.py`                  | `internal/stream`, `internal/jetstream`          | Readers, offsets, JetStream/KV.                                                                                                            |
| `fleuve/runner.py`, `actions.py`, `action_utils.py` | `internal/runner`, `internal/actions`            | Goroutine pools, action retries, checkpoints.                                                                                              |
| `fleuve/delay.py`                                   | `internal/delay`                                 | **Cron:** match `croniter` + timezone behavior; validate against `fleuve/tests/test_delay.py`.                                             |
| `fleuve/partitioning.py`, `scaling.py`              | `internal/partitioning`, `internal/scaling`      | Same partition and rebalance semantics.                                                                                                    |
| `fleuve/truncation.py`, `reconciliation.py`         | `internal/truncation`, `internal/reconciliation` |                                                                                                                                            |
| `fleuve/external_messaging.py`                      | `internal/externalmsg`                           |                                                                                                                                            |
| `fleuve/config.py`                                  | `internal/fleuveconfig`                          | `fleuve.toml` `[fleuve]` + `FLEUVE_`* overrides (mirror `_apply_env_overrides`).                                                           |
| `fleuve/gateway.py`                                 | `internal/gateway`                               | Router prefix `/commands`.                                                                                                                 |
| `fleuve/ui/backend/api.py`                          | `internal/uiapi` + `internal/uistore`            | Read models + SQL; same query semantics as SQLAlchemy endpoints.                                                                           |
| `fleuve/metrics.py`, `tracing.py`                   | `internal/metrics`, `internal/tracing`           | OTEL optional.                                                                                                                             |
| `fleuve/cli.py`                                     | `cmd/fleuve` (e.g. **cobra**)                    | Policy: v1 may ship `ui`, `gateway`, `runner` subcommands; Python-centric `init`/`new` scaffolding can remain Python-only until revisited. |
| `fleuve/testing.py`                                 | `internal/testing` / `pkg/fleuvetest`            | Test harness for user workflows in Go.                                                                                                     |


**Suggested module path:** `github.com/doomervibe/fleuve/go` (root `go/` directory).

---

## 3. Layered architecture

```
                    ┌─────────────────────────────────────┐
                    │  cmd/fleuve (ui | gateway | runner) │
                    └─────────────────┬───────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
   internal/uiapi              internal/gateway            internal/runner
   (HTTP, JSON shapes)         (/commands)                 (readers, side effects)
          │                           │                           │
          ▼                           ▼                           ▼
   internal/uistore             internal/repo  ◄──────────► internal/stream
   (read-only SQL)              (commands, persistence)      (JetStream, NATS KV)
          │                           │                           │
          └───────────────────────────┼───────────────────────────┘
                                      ▼
                            internal/pgmodel + pgx pool
                                      │
                                      ▼
                               PostgreSQL + NATS
```

- **Concurrency:** One **pgxpool.Pool** per process; bounded worker pools for runner/actions (analogous to asyncio semaphores / inflight limits). Per-workflow ordering guarantees preserved inside the same design as Python `AsyncRepo` + readers.
- **HTTP:** `net/http` + **chi** (or stdlib only) — small surface, explicit middleware for CORS and logging.
- **Validation:** `go-playground/validator` for static structs; user event/command types may remain `json.RawMessage` or generated code; framework types must round-trip with Python JSON.

---

## 4. Implementation order (bottom-up)

1. **Config** — `load_fleuve_toml` parity + `DATABASE_URL` normalization (`postgresql+asyncpg://` → `postgresql://` for pgx).
2. **PostgreSQL types & migrations** — Document or port Alembic SQL; ensure column types match (`JSONB`, `TIMESTAMPTZ`, composite PKs on `activities`, `delay_schedules`, etc.).
3. **Crypto + zstd** — Read path for encrypted blobs (activities `result`, encrypted state columns if used).
4. **Repo** — Command append, idempotency, rejection paths, subscriptions, delays, snapshots, truncation.
5. **Stream / JetStream** — Offsets, consumers, KV cache semantics from `stream.py` / `jetstream.py`.
6. **Runner + actions** — Side effect pipeline, retries, DLQ behavior per README.
7. **HTTP** — UI API and gateway last so contract tests can run against completed layers.

---

## 5. HTTP contract checklist

### UI (`FleuveUIBackend`)

- `GET /health` → `{"status":"ok"}`
- `GET /` → index with `{{project_title}}` or JSON when no dist
- `GET /api/workflow-types` … through batch endpoints — see `api.py`
- `POST /api/workflows/batch/cancel` and `batch/replay` → **501** with same `detail` strings as Python (until wired to gateway/repo)
- Catch-all `GET /{path}` for SPA (after API routes)

### Command gateway (`FleuveCommandGateway`)

- Prefix `/commands`
- Routes: process command, create, pause, resume, cancel, retry — status **404** / **400** / **501** / **200** bodies as in `gateway.py`

---

## 6. Testing strategy

- **Golden / contract tests:** Export example responses from Python (`httpx` against FastAPI) or reuse `fleuve/tests/test_gateway.py` patterns; compare JSON in Go tests.
- **Integration:** Docker Compose: PostgreSQL + NATS; run Python integration tests’ scenarios against Go binaries where applicable.
- **Property tests:** Event ordering, idempotency keys, partition moves (mirror `test_scaling.py`).

---

## 7. Compatibility matrix (initial)


| Component            | Version / note                                                                    |
| -------------------- | --------------------------------------------------------------------------------- |
| **Go**               | 1.22+ (generics, std `slices`/`maps` as needed)                                   |
| **PostgreSQL**       | Same as Python deployments (JSONB, `TIMESTAMPTZ`, arrays, GIN indexes per models) |
| **NATS / JetStream** | Compatible with `nats-py` usage in repo; verify stream names and consumer options |
| **Stored JSON**      | Must remain byte-compatible for mixed Python/Go runners                           |
| **Secrets**          | `STORAGE_KEY` for AES — same derivation as `load_storage_key()` in `postgres.py`  |


---

## 8. Migration notes

1. **Database:** No schema fork — run existing migrations from Python, or ship equivalent SQL. Go binaries expect the same table names; standalone UI defaults: `events`, `activities`, `subscriptions`, `delay_schedules` (override via `FLEUVE_*_TABLE` env vars per `default_models.py`).
2. **Rolling upgrade:** Run Python and Go workers against the same DB only after repo/event compatibility is verified for your workflow types; encrypt any encrypted columns with identical pipelines.
3. **Operational:** Point `FLEUVE_UI_TITLE`, `DATABASE_URL`, and NATS URLs the same way as Python `fleuve.toml` / env.

---

## 9. Current repository layout (`go/`)

Implemented in this repo:

- `go/cmd/fleuve` — CLI: `fleuve ui` (admin API + static assets), `fleuve gateway` (stub `/commands` router until repos are wired).
- `go/internal/fleuveconfig` — `fleuve.toml` `[fleuve]` + `FLEUVE_*` overrides; `NormalizeDatabaseURL` for pgx.
- `go/internal/apimodels` — JSON DTOs aligned with `fleuve/ui/backend/models.py`.
- `go/internal/uiapi` — chi HTTP server: health, `/api/*`, CORS when no dist, `{{project_title}}`, SPA catch-all.
- `go/internal/uistore` — read-only PostgreSQL queries (default table names via `FLEUVE_*_TABLE`).
- `go/internal/gateway` — wire-compatible `/commands/*` routes (no workflow types until integrated with `repo`).

Build: `cd go && go build -o fleuve ./cmd/fleuve`. Run UI: `DATABASE_URL=postgresql://... ./fleuve ui` (optional `FLEUVE_UI_DIST`, `FLEUVE_UI_TITLE`).

Extend with `internal/repo`, `internal/runner`, etc., following the table above.

---

## 10. Cron and timezones

Python uses **croniter** with optional `zoneinfo`. Go should use a vetted cron library and document any syntax differences. **Delay admin UI** exposes `next_fire_times` (5 entries) — acceptance tests must compare Python vs Go for the same `cron_expression` + `timezone`.

---

## 11. References (normative code paths)

- UI routes: `fleuve/ui/backend/api.py`
- UI DTOs: `fleuve/ui/backend/models.py`
- Discovery: `fleuve/ui/backend/discovery.py`
- Gateway: `fleuve/gateway.py`
- ORM / storage: `fleuve/postgres.py`
- Config: `fleuve/config.py`

