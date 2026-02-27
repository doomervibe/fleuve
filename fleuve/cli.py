"""Command-line interface for Fleuve."""

import asyncio
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

import click


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def validate_project_name(name: str) -> bool:
    """Validate that project name is a valid Python identifier."""
    if not name:
        return False
    pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*$"
    return bool(re.match(pattern, name))


def render_template(content: str, **kwargs) -> str:
    """Render a template string by replacing {{variable}} placeholders."""
    result = content
    for key, value in kwargs.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(value))
    return result


def _get_database_url() -> str:
    url = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/fleuve"
    )
    return url


# ---------------------------------------------------------------------------
# Project scaffolding helpers (kept for backward compat)
# ---------------------------------------------------------------------------


def create_project(
    project_name: str,
    target_dir: Optional[str] = None,
    overwrite: bool = False,
    multi_workflow: bool = False,
    initial_workflow: Optional[str] = None,
    include_ui: bool = False,
) -> None:
    if not validate_project_name(project_name):
        click.echo(f"Error: '{project_name}' is not a valid project name.", err=True)
        click.echo(
            "Project name must be a valid Python identifier (letters, digits, underscores, starting with letter/underscore).",
            err=True,
        )
        sys.exit(1)

    base_dir = Path(target_dir) if target_dir else Path.cwd()
    project_dir = base_dir / project_name

    if project_dir.exists():
        if not overwrite:
            click.echo(f"Error: Directory '{project_dir}' already exists.", err=True)
            click.echo("Use --overwrite to overwrite existing directory.", err=True)
            sys.exit(1)
        else:
            click.echo(f"Warning: Overwriting existing directory '{project_dir}'")
            shutil.rmtree(project_dir)

    template_name = "multi_workflow_template" if multi_workflow else "project_template"
    template_dir = Path(__file__).parent / "templates" / template_name
    if not template_dir.exists():
        click.echo(f"Error: Template directory not found: {template_dir}", err=True)
        sys.exit(1)

    project_dir.mkdir(parents=True, exist_ok=True)

    package_dir = project_dir / project_name
    workflows_dir = project_dir / "workflows"
    if not multi_workflow:
        package_dir.mkdir(exist_ok=True)
    else:
        workflows_dir.mkdir(exist_ok=True)

    project_title = project_name.replace("_", " ").title()

    if multi_workflow:
        if not initial_workflow:
            initial_workflow = "example_workflow"

        workflow_name = initial_workflow
        workflow_title = workflow_name.replace("_", " ").title()
        workflow_class_name = workflow_title.replace(" ", "")

        template_vars = {
            "project_name": project_name,
            "project_title": project_title,
            "workflow_name": workflow_name,
            "workflow_title": workflow_title,
            "workflow_class_name": workflow_class_name,
        }
    else:
        workflow_name = f"{project_name.title().replace('_', '')}Workflow"
        state_name = f"{project_name.title().replace('_', '')}State"
        project_title_no_spaces = project_title.replace(" ", "")

        template_vars = {
            "project_name": project_name,
            "project_title": project_title,
            "project_title_no_spaces": project_title_no_spaces,
            "workflow_name": workflow_name,
            "state_name": state_name,
        }

    for template_file in template_dir.rglob("*"):
        if template_file.is_dir():
            continue

        rel_path = template_file.relative_to(template_dir)

        if "__pycache__" in rel_path.parts or rel_path.suffix == ".pyc":
            continue

        if multi_workflow:
            if (
                rel_path.parts[0] == "workflows"
                and "{{workflow_name}}" in rel_path.parts
            ):
                new_parts = [workflows_dir.name] + [
                    workflow_name if p == "{{workflow_name}}" else p
                    for p in rel_path.parts[1:]
                ]
                target_path = project_dir / Path(*new_parts)
            else:
                target_path = project_dir / rel_path
        else:
            if rel_path.parts[0] == "{{project_name}}":
                target_path = package_dir / Path(*rel_path.parts[1:])
            else:
                target_path = project_dir / rel_path

        target_path.parent.mkdir(parents=True, exist_ok=True)
        content = template_file.read_text(encoding="utf-8")
        rendered = render_template(content, **template_vars)
        target_path.write_text(rendered, encoding="utf-8")

        if target_path.suffix in (".sh", ".py") and "main" in target_path.name:
            target_path.chmod(0o755)

    if include_ui:
        ui_template_dir = Path(__file__).parent / "templates" / "ui_addon"
        if ui_template_dir.exists():
            for ui_file in ui_template_dir.rglob("*"):
                if ui_file.is_dir():
                    continue
                if any(
                    p in ui_file.parts
                    for p in ["node_modules", "dist", "__pycache__", ".git"]
                ):
                    continue
                # Skip ui/backend - project uses fleuve.ui from the package
                if "ui" in ui_file.parts and "backend" in ui_file.parts:
                    continue
                if ui_file.suffix in [".pyc", ".pyo"]:
                    continue

                rel_path = ui_file.relative_to(ui_template_dir)
                target_path = project_dir / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)

                try:
                    content = ui_file.read_text(encoding="utf-8")
                    rendered = render_template(content, **template_vars)
                    target_path.write_text(rendered, encoding="utf-8")
                except (UnicodeDecodeError, ValueError):
                    shutil.copy2(ui_file, target_path)

                if target_path.suffix == ".sh":
                    target_path.chmod(0o755)

            click.echo("✓ UI files added (FastAPI backend + React frontend)")

    if multi_workflow:
        click.echo(
            f"✓ Created multi-workflow Fleuve project '{project_name}' in {project_dir}"
        )
        click.echo(f"✓ Initial workflow '{workflow_name}' created")
        click.echo("\nNext steps:")
        click.echo(f"  1. cd {project_name}")
        click.echo("  2. Update db_models.py to import your workflow types")
        click.echo("  3. Update main.py to set up your workflow runners")
        click.echo("  4. Copy .env.example to .env and configure")
        click.echo("  5. docker-compose up -d  # Start PostgreSQL and NATS")
        click.echo(f"\nAdd more workflows with: fleuve addworkflow <workflow_name>")
    else:
        click.echo(f"✓ Created Fleuve project '{project_name}' in {project_dir}")
        click.echo("\nNext steps:")
        click.echo(f"  1. cd {project_name}")
        click.echo("  2. Copy .env.example to .env and configure")
        click.echo("  3. docker-compose up -d  # Start PostgreSQL and NATS")
        click.echo("  4. pip install -e .  # Install project")
        click.echo("  5. python main.py  # Run your workflow")


def add_workflow(
    workflow_name: str,
    project_dir: Optional[str] = None,
) -> None:
    if not validate_project_name(workflow_name):
        click.echo(f"Error: '{workflow_name}' is not a valid workflow name.", err=True)
        sys.exit(1)

    proj_dir = Path(project_dir) if project_dir else Path.cwd()
    workflows_dir = proj_dir / "workflows"
    if not workflows_dir.exists():
        click.echo(
            f"Error: '{proj_dir}' does not appear to be a multi-workflow Fleuve project.",
            err=True,
        )
        sys.exit(1)

    workflow_dir = workflows_dir / workflow_name
    if workflow_dir.exists():
        click.echo(
            f"Error: Workflow '{workflow_name}' already exists in {workflow_dir}",
            err=True,
        )
        sys.exit(1)

    template_dir = (
        Path(__file__).parent
        / "templates"
        / "multi_workflow_template"
        / "workflows"
        / "{{workflow_name}}"
    )
    if not template_dir.exists():
        click.echo(f"Error: Workflow template not found: {template_dir}", err=True)
        sys.exit(1)

    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_title = workflow_name.replace("_", " ").title()
    workflow_class_name = workflow_title.replace(" ", "")
    template_vars = {
        "workflow_name": workflow_name,
        "workflow_title": workflow_title,
        "workflow_class_name": workflow_class_name,
    }

    for template_file in template_dir.rglob("*"):
        if template_file.is_dir():
            continue
        rel_path = template_file.relative_to(template_dir)
        if "__pycache__" in rel_path.parts or rel_path.suffix == ".pyc":
            continue
        target_path = workflow_dir / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        content = template_file.read_text(encoding="utf-8")
        rendered = render_template(content, **template_vars)
        target_path.write_text(rendered, encoding="utf-8")

    click.echo(f"✓ Added workflow '{workflow_name}' to {proj_dir}")


# ---------------------------------------------------------------------------
# Admin helpers (async, used by admin subcommands)
# ---------------------------------------------------------------------------


async def _make_session_maker(database_url: str):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _inspect_workflow(
    database_url: str, workflow_id: str, workflow_type: str
) -> None:
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    engine = create_async_engine(database_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_maker() as s:
            # Get events
            result = await s.execute(
                text(
                    "SELECT workflow_version, event_type, at "
                    "FROM (SELECT * FROM (SELECT workflow_version, event_type, at, workflow_type, workflow_id "
                    "      FROM events WHERE workflow_id = :wf_id) sub WHERE workflow_type = :wf_type) t "
                    "ORDER BY workflow_version"
                ),
                {"wf_id": workflow_id, "wf_type": workflow_type},
            )
            rows = result.fetchall()
            if not rows:
                # Try without workflow_type filter (detect table name)
                click.echo(
                    f"No events found for workflow '{workflow_id}' of type '{workflow_type}'"
                )
                click.echo("Hint: check --table option or ensure the workflow exists")
                return

            click.echo(f"\nWorkflow: {workflow_id}  type={workflow_type}")
            click.echo(f"{'Version':<10} {'Event Type':<30} {'At'}")
            click.echo("-" * 60)
            for row in rows:
                click.echo(f"{row[0]:<10} {row[1]:<30} {row[2]}")
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Click CLI
# ---------------------------------------------------------------------------


@click.group()
def cli():
    """Fleuve - Workflow Framework for Python"""


# ---- Project scaffolding commands ----------------------------------------


@cli.command("startproject")
@click.argument("name", required=False)
@click.option("-d", "--directory", help="Directory to create project in (default: cwd)")
@click.option("--overwrite", is_flag=True, help="Overwrite existing directory")
@click.option("--multi", is_flag=True, help="Create multi-workflow project structure")
@click.option("-w", "--workflow", help="Name of initial workflow (multi-workflow only)")
@click.option("--ui", is_flag=True, help="Include web UI setup")
def startproject(name, directory, overwrite, multi, workflow, ui):
    """Create a new Fleuve project."""
    if not name:
        while True:
            name = click.prompt("Project name").strip()
            if validate_project_name(name):
                break
            click.echo("Invalid project name. Please use a valid Python identifier.")

    initial_workflow = workflow if multi else None
    create_project(name, directory, overwrite, multi, initial_workflow, ui)


@cli.command("addworkflow")
@click.argument("name", required=False)
@click.option("-d", "--directory", help="Project directory (default: cwd)")
def addworkflow(name, directory):
    """Add a new workflow to an existing multi-workflow project."""
    if not name:
        while True:
            name = click.prompt("Workflow name").strip()
            if validate_project_name(name):
                break
            click.echo("Invalid workflow name. Please use a valid Python identifier.")

    add_workflow(name, directory)


# ---- Admin commands -------------------------------------------------------


@cli.group("admin")
@click.option(
    "--db",
    envvar="DATABASE_URL",
    default="postgresql+asyncpg://postgres:postgres@localhost/fleuve",
    show_default=True,
    help="PostgreSQL connection string",
)
@click.pass_context
def admin(ctx, db):
    """Admin operations for running workflows."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = db


@admin.command("inspect")
@click.argument("workflow_id")
@click.option("--type", "workflow_type", required=True, help="Workflow type name")
@click.option("--table", default="events", show_default=True, help="Events table name")
@click.pass_context
def admin_inspect(ctx, workflow_id, workflow_type, table):
    """Show state, events and activities for a workflow."""
    database_url = ctx.obj["db"]

    async def _run():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

        engine = create_async_engine(database_url, echo=False)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_maker() as s:
                result = await s.execute(
                    text(
                        f"SELECT workflow_version, event_type, at "
                        f"FROM {table} "
                        f"WHERE workflow_id = :wf_id AND workflow_type = :wf_type "
                        f"ORDER BY workflow_version"
                    ),
                    {"wf_id": workflow_id, "wf_type": workflow_type},
                )
                rows = result.fetchall()
                if not rows:
                    click.echo(
                        f"No events found for workflow '{workflow_id}' (type={workflow_type})"
                    )
                    return

                click.echo(
                    f"\nWorkflow: {workflow_id}  type={workflow_type}  events={len(rows)}"
                )
                click.echo(f"\n{'Version':<10} {'Event Type':<35} At")
                click.echo("-" * 70)
                for row in rows:
                    click.echo(f"{row[0]:<10} {row[1]:<35} {row[2]}")
        finally:
            await engine.dispose()

    asyncio.run(_run())


@admin.command("list")
@click.option("--type", "workflow_type", required=True, help="Workflow type name")
@click.option(
    "--status", default=None, help="Filter by lifecycle (active/paused/cancelled)"
)
@click.option("--limit", default=50, show_default=True, help="Max results")
@click.option("--table", default="events", show_default=True, help="Events table name")
@click.pass_context
def admin_list(ctx, workflow_type, status, limit, table):
    """List workflows of a given type."""
    database_url = ctx.obj["db"]

    async def _run():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

        engine = create_async_engine(database_url, echo=False)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_maker() as s:
                result = await s.execute(
                    text(
                        f"SELECT workflow_id, MAX(workflow_version) AS version, MAX(at) AS last_event "
                        f"FROM {table} "
                        f"WHERE workflow_type = :wf_type "
                        f"GROUP BY workflow_id "
                        f"ORDER BY last_event DESC "
                        f"LIMIT :lim"
                    ),
                    {"wf_type": workflow_type, "lim": limit},
                )
                rows = result.fetchall()
                if not rows:
                    click.echo(f"No workflows found for type '{workflow_type}'")
                    return

                click.echo(f"\n{'Workflow ID':<40} {'Version':<10} Last Event")
                click.echo("-" * 80)
                for row in rows:
                    click.echo(f"{row[0]:<40} {row[1]:<10} {row[2]}")
        finally:
            await engine.dispose()

    asyncio.run(_run())


@admin.command("pause")
@click.argument("workflow_id")
@click.option("--type", "workflow_type", required=True, help="Workflow type name")
@click.option("--reason", default="", help="Reason for pausing")
@click.option("--table", default="events", show_default=True, help="Events table name")
@click.pass_context
def admin_pause(ctx, workflow_id, workflow_type, reason, table):
    """Pause a workflow."""
    database_url = ctx.obj["db"]

    async def _run():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

        engine = create_async_engine(database_url, echo=False)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_maker() as s:
                # Get latest version
                row = (
                    await s.execute(
                        text(
                            f"SELECT MAX(workflow_version) FROM {table} "
                            f"WHERE workflow_id = :wf_id AND workflow_type = :wf_type"
                        ),
                        {"wf_id": workflow_id, "wf_type": workflow_type},
                    )
                ).fetchone()
                if row is None or row[0] is None:
                    click.echo(f"Workflow '{workflow_id}' not found.", err=True)
                    return
                version = row[0]
                body = json.dumps({"type": "system_pause", "reason": reason})
                await s.execute(
                    text(
                        f"INSERT INTO {table} (workflow_id, workflow_version, event_type, workflow_type, body, schema_version) "
                        f"VALUES (:wf_id, :ver, 'system_pause', :wf_type, :body::jsonb, 1)"
                    ),
                    {
                        "wf_id": workflow_id,
                        "ver": version + 1,
                        "wf_type": workflow_type,
                        "body": body,
                    },
                )
                await s.commit()
                click.echo(f"✓ Workflow '{workflow_id}' paused.")
        finally:
            await engine.dispose()

    asyncio.run(_run())


@admin.command("resume")
@click.argument("workflow_id")
@click.option("--type", "workflow_type", required=True, help="Workflow type name")
@click.option("--table", default="events", show_default=True, help="Events table name")
@click.pass_context
def admin_resume(ctx, workflow_id, workflow_type, table):
    """Resume a paused workflow."""
    database_url = ctx.obj["db"]

    async def _run():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

        engine = create_async_engine(database_url, echo=False)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_maker() as s:
                row = (
                    await s.execute(
                        text(
                            f"SELECT MAX(workflow_version) FROM {table} "
                            f"WHERE workflow_id = :wf_id AND workflow_type = :wf_type"
                        ),
                        {"wf_id": workflow_id, "wf_type": workflow_type},
                    )
                ).fetchone()
                if row is None or row[0] is None:
                    click.echo(f"Workflow '{workflow_id}' not found.", err=True)
                    return
                version = row[0]
                body = json.dumps({"type": "system_resume"})
                await s.execute(
                    text(
                        f"INSERT INTO {table} (workflow_id, workflow_version, event_type, workflow_type, body, schema_version) "
                        f"VALUES (:wf_id, :ver, 'system_resume', :wf_type, :body::jsonb, 1)"
                    ),
                    {
                        "wf_id": workflow_id,
                        "ver": version + 1,
                        "wf_type": workflow_type,
                        "body": body,
                    },
                )
                await s.commit()
                click.echo(f"✓ Workflow '{workflow_id}' resumed.")
        finally:
            await engine.dispose()

    asyncio.run(_run())


@admin.command("cancel")
@click.argument("workflow_id")
@click.option("--type", "workflow_type", required=True, help="Workflow type name")
@click.option("--reason", default="", help="Reason for cancellation")
@click.option("--table", default="events", show_default=True, help="Events table name")
@click.pass_context
def admin_cancel(ctx, workflow_id, workflow_type, reason, table):
    """Cancel a workflow."""
    database_url = ctx.obj["db"]

    async def _run():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

        engine = create_async_engine(database_url, echo=False)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_maker() as s:
                row = (
                    await s.execute(
                        text(
                            f"SELECT MAX(workflow_version) FROM {table} "
                            f"WHERE workflow_id = :wf_id AND workflow_type = :wf_type"
                        ),
                        {"wf_id": workflow_id, "wf_type": workflow_type},
                    )
                ).fetchone()
                if row is None or row[0] is None:
                    click.echo(f"Workflow '{workflow_id}' not found.", err=True)
                    return
                version = row[0]
                body = json.dumps({"type": "system_cancel", "reason": reason})
                await s.execute(
                    text(
                        f"INSERT INTO {table} (workflow_id, workflow_version, event_type, workflow_type, body, schema_version) "
                        f"VALUES (:wf_id, :ver, 'system_cancel', :wf_type, :body::jsonb, 1)"
                    ),
                    {
                        "wf_id": workflow_id,
                        "ver": version + 1,
                        "wf_type": workflow_type,
                        "body": body,
                    },
                )
                await s.commit()
                click.echo(f"✓ Workflow '{workflow_id}' cancelled.")
        finally:
            await engine.dispose()

    asyncio.run(_run())


@admin.command("replay")
@click.argument("workflow_id")
@click.option("--type", "workflow_type", required=True, help="Workflow type name")
@click.option("--from-version", "from_version", default=1, show_default=True)
@click.pass_context
def admin_replay(ctx, workflow_id, workflow_type, from_version):
    """Replay a workflow from a specific version (re-processes events to rebuild state)."""
    click.echo(
        f"Replay for '{workflow_id}' from version {from_version}: "
        "use repo.replay_workflow() in your application code for full replay support."
    )
    click.echo(
        "The CLI replay command is a placeholder; full replay requires access to your "
        "workflow type definitions."
    )


@admin.command("health")
@click.option(
    "--nats-url", envvar="NATS_URL", default="nats://localhost:4222", show_default=True
)
@click.pass_context
def admin_health(ctx, nats_url):
    """Check database and NATS connectivity."""
    database_url = ctx.obj["db"]

    async def _run():
        errors = []

        # Check DB
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(database_url, echo=False)
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            click.echo("✓ Database: OK")
        except Exception as e:
            click.echo(f"✗ Database: {e}", err=True)
            errors.append("db")

        # Check NATS
        try:
            import nats

            nc = await nats.connect(nats_url, connect_timeout=3)
            await nc.close()
            click.echo("✓ NATS: OK")
        except Exception as e:
            click.echo(f"✗ NATS: {e}", err=True)
            errors.append("nats")

        if errors:
            sys.exit(1)

    asyncio.run(_run())


@admin.command("truncate")
@click.option("--type", "workflow_type", required=True, help="Workflow type name")
@click.option("--table", default="events", show_default=True, help="Events table name")
@click.option("--snapshot-table", default="snapshots", show_default=True)
@click.option(
    "--retention-days", default=7, show_default=True, help="Min retention in days"
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be deleted without deleting"
)
@click.pass_context
def admin_truncate(ctx, workflow_type, table, snapshot_table, retention_days, dry_run):
    """Truncate old events that have been superseded by a snapshot."""
    database_url = ctx.obj["db"]

    async def _run():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

        engine = create_async_engine(database_url, echo=False)
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_maker() as s:
                # Count eligible events (events older than retention that are before a snapshot)
                count_result = await s.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table} e "
                        f"JOIN {snapshot_table} sn ON sn.workflow_id = e.workflow_id "
                        f"WHERE e.workflow_type = :wf_type "
                        f"AND e.workflow_version < sn.version "
                        f"AND e.at < NOW() - INTERVAL '{retention_days} days'"
                    ),
                    {"wf_type": workflow_type},
                )
                count = count_result.scalar() or 0
                if dry_run:
                    click.echo(
                        f"[dry-run] Would delete {count} events for type '{workflow_type}'"
                    )
                    return
                if count == 0:
                    click.echo(
                        f"No events eligible for truncation for type '{workflow_type}'"
                    )
                    return
                await s.execute(
                    text(
                        f"DELETE FROM {table} e "
                        f"USING {snapshot_table} sn "
                        f"WHERE sn.workflow_id = e.workflow_id "
                        f"AND e.workflow_type = :wf_type "
                        f"AND e.workflow_version < sn.version "
                        f"AND e.at < NOW() - INTERVAL '{retention_days} days'"
                    ),
                    {"wf_type": workflow_type},
                )
                await s.commit()
                click.echo(f"✓ Deleted {count} events for type '{workflow_type}'")
        except Exception as e:
            click.echo(f"Truncation failed: {e}", err=True)
            click.echo(
                "Tip: if the snapshot table doesn't exist, enable snapshotting first.",
                err=True,
            )
        finally:
            await engine.dispose()

    asyncio.run(_run())


# ---- Validation command ---------------------------------------------------


@cli.command("ui")
@click.option(
    "--host",
    default="0.0.0.0",
    show_default=True,
    help="Host to bind the UI server",
)
@click.option(
    "--port",
    default=8001,
    show_default=True,
    help="Port for the UI server",
)
def ui(host, port):
    """Start the Fleuve web UI server."""
    from fleuve.ui.server import run_server

    run_server(host=host, port=port)


@cli.command("validate")
@click.argument("module", required=False)
def validate(module):
    """Validate workflow class definitions for common issues.

    MODULE is a dotted Python module path containing Workflow subclasses
    (e.g. myproject.workflows).  When omitted, validates any workflow classes
    imported in the current directory's Python path.
    """
    from fleuve.validation import discover_and_validate

    issues = discover_and_validate(module)
    if not issues:
        click.echo("✓ All workflow definitions look valid.")
    else:
        for wf_name, errors in issues.items():
            for err in errors:
                click.echo(f"  {wf_name}: {err}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Legacy argparse entry point (kept for backward compat)
# ---------------------------------------------------------------------------


def main() -> None:
    """Main CLI entry point (delegates to click)."""
    cli()


if __name__ == "__main__":
    main()
