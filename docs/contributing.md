# Contributing

See **[CONTRIBUTING.md](https://github.com/doomervibe/fleuve/blob/main/CONTRIBUTING.md)** on GitHub for setup (Poetry, Postgres, NATS, tests, style).

## Documentation locally

```bash
poetry install --with dev
poetry run mkdocs serve
```

Open `http://127.0.0.1:8000` to preview this site. Use `mkdocs build --strict` before pushing doc changes.

## Publishing (maintainers)

CI deploys the built site to the **`gh-pages`** branch on pushes to **`main`**. After the first successful run, set **Settings → Pages** in GitHub to serve from **`gh-pages`** at **`/`** (root).
