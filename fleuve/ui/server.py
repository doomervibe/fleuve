"""Standalone server for Fleuve UI."""

import asyncio
import logging
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from fleuve.ui.backend.api import create_app
from fleuve.ui.default_models import (
    DefaultStoredEvent,
    DefaultActivity,
    DefaultDelaySchedule,
    DefaultSubscription,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_frontend_dist_path() -> Path | None:
    """Get path to the bundled frontend dist, if it exists."""
    ui_dir = Path(__file__).parent
    dist = ui_dir / "frontend_dist"
    if (dist / "index.html").exists():
        return dist
    # Fallback: check template location (development)
    template_dist = ui_dir.parent / "templates" / "ui_addon" / "ui" / "frontend" / "dist"
    if (template_dist / "index.html").exists():
        return template_dist
    return None


async def _create_session_maker():
    """Create database session maker from environment variables."""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/fleuve",
    )

    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
    )

    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def run_server(host: str = "0.0.0.0", port: int = 8001) -> None:
    """Run the Fleuve UI server."""
    import uvicorn

    frontend_dist_path = _get_frontend_dist_path()
    if not frontend_dist_path or not (frontend_dist_path / "index.html").exists():
        logger.warning(
            "UI frontend not built. Run 'npm run build' in "
            "fleuve/templates/ui_addon/ui/frontend to enable the web interface. "
            "The API will still work."
        )

    async def _create_app():
        session_maker = await _create_session_maker()
        return create_app(
            session_maker=session_maker,
            event_model=DefaultStoredEvent,
            activity_model=DefaultActivity,
            delay_schedule_model=DefaultDelaySchedule,
            subscription_model=DefaultSubscription,
            frontend_dist_path=frontend_dist_path,
        )

    app = asyncio.run(_create_app())

    logger.info(f"Starting Fleuve UI server on http://{host}:{port}")
    logger.info(f"API available at: http://{host}:{port}/api")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )
