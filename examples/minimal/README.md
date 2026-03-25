# Minimal Fleuve example

End-to-end demo: one workflow, PostgreSQL persistence, NATS ephemeral state, and a long-running runner.

## Prerequisites

- Python 3.13+
- [Poetry](https://python-poetry.org/)
- Docker (for Postgres + NATS)

## Quick start

From this directory (`examples/minimal`):

```bash
cp .env.example .env
docker compose up -d
poetry install
poetry run python -m minimal_example
```

The app creates workflow id `minimal-demo-1`, applies the start command, then runs `runner.run()` until you press Ctrl+C.

`fleuve` is installed from the repository root via a path dependency in `pyproject.toml`. If you only have Fleuve from PyPI, change that dependency to:

```toml
fleuve = "^0.1.0"
```

## Environment

| Variable        | Purpose |
|----------------|---------|
| `DATABASE_URL` | Async SQLAlchemy URL for Postgres |
| `NATS_URL`     | NATS server (JetStream not required for this example’s default runner config) |
| `STORAGE_KEY`  | Secret for encrypted columns (required; see `.env.example`) |

## Cursor Agent Skills

If you use Cursor:

```bash
fleuve cursor-skills install
```

(run from your app project root after installing `fleuve`)
