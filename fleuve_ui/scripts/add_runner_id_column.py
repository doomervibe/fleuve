#!/usr/bin/env python3
"""Add runner_id column to activities table if it doesn't exist.

Run this after upgrading fleuve to add runner_id support:
    python -m fleuve_ui.scripts.add_runner_id_column

Or with your project's database URL:
    DATABASE_URL=postgresql+asyncpg://... python -m fleuve_ui.scripts.add_runner_id_column
"""
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))


async def main():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    database_url = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/les"
    )
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        # Check if column exists (PostgreSQL)
        result = await conn.execute(
            text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'activities' AND column_name = 'runner_id'
            """)
        )
        if result.fetchone():
            print("runner_id column already exists")
            return
        await conn.execute(
            text("ALTER TABLE activities ADD COLUMN runner_id VARCHAR(256)")
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_activities_runner_id "
                "ON activities (runner_id)"
            )
        )
        print("Added runner_id column to activities table")


if __name__ == "__main__":
    asyncio.run(main())
