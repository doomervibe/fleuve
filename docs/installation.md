# Installation

## Requirements

- **Python 3.13+**
- **PostgreSQL 12+** (event storage)
- **NATS Server 2.9+** with **JetStream** (`nats -js`) for ephemeral state

## Install the package

=== "pip"

    ```bash
    pip install fleuve
    ```

=== "Poetry"

    ```bash
    poetry add fleuve
    ```

=== "From source"

    ```bash
    git clone https://github.com/doomervibe/fleuve.git
    cd fleuve
    poetry install
    ```

## Optional: Cursor Agent Skills

If you use [Cursor](https://cursor.com/), install bundled Agent Skills after installing Fleuve:

```bash
fleuve cursor-skills install
```

Run from your **application** project root. Skills are copied to `.cursor/skills/`. See `fleuve cursor-skills --help` for options (e.g. `--user`).

## Runnable example

The repo includes **[examples/minimal](https://github.com/doomervibe/fleuve/tree/main/examples/minimal)** — Docker Compose (Postgres + NATS), `create_workflow_runner`, and a single workflow. Use it as a template.

## Infrastructure quick reference

### PostgreSQL

```bash
docker run -d \
  --name fleuve-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:16
```

Create a database as needed (e.g. `CREATE DATABASE fleuve;`).

### NATS (JetStream)

```bash
docker run -d \
  --name fleuve-nats \
  -p 4222:4222 \
  -p 8222:8222 \
  nats:latest \
  -js
```

## Why Fleuve? (vs Temporal)

| | Fleuve | Temporal |
|---|--------|----------|
| **Architecture** | Event sourcing | Activity-based |
| **Infrastructure** | PostgreSQL + NATS | Dedicated Temporal server or cloud |
| **Deployment** | Python app | Separate workflow service |
| **Data** | Events in your Postgres | Temporal’s store |
| **Typing** | Pydantic-first | SDK types |

Choose Fleuve when you want **event sourcing**, **data in PostgreSQL**, and **no separate workflow server**. Choose Temporal for **multi-language workers** or **managed cloud** where that fits.

---

*More detail: [Full README — Installation](https://github.com/doomervibe/fleuve/blob/main/README.md#installation).*
