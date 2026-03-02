"""Standalone server for Fleuve UI."""

import asyncio
import importlib
import logging
import os
from pathlib import Path
from typing import Any

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
    template_dist = (
        ui_dir.parent / "templates" / "ui_addon" / "ui" / "frontend" / "dist"
    )
    if (template_dist / "index.html").exists():
        return template_dist
    return None


def _resolve_model(
    models_module: str | None,
    class_name: str | None,
    default: Any,
) -> Any:
    """Return a model class from a dotted module path, or fall back to *default*.

    Parameters
    ----------
    models_module:
        Dotted Python import path, e.g. ``myproject.db.db_fleuve``.
        When ``None`` the *default* is returned immediately.
    class_name:
        The class attribute to retrieve from the imported module.
        When ``None`` the *default* is returned.
    default:
        Fallback class used when either argument is ``None``.
    """
    if not models_module or not class_name:
        return default
    try:
        module = importlib.import_module(models_module)
    except ImportError as exc:
        raise ImportError(
            f"Could not import models module '{models_module}': {exc}"
        ) from exc
    try:
        return getattr(module, class_name)
    except AttributeError:
        raise AttributeError(
            f"Module '{models_module}' has no attribute '{class_name}'"
        )


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


def run_server(
    host: str = "0.0.0.0",
    port: int = 8001,
    models_module: str | None = None,
    event_model_name: str | None = None,
    activity_model_name: str | None = None,
    delay_schedule_model_name: str | None = None,
    subscription_model_name: str | None = None,
) -> None:
    """Run the Fleuve UI server.

    Parameters
    ----------
    host:
        Network interface to bind to.
    port:
        TCP port for the HTTP server.
    models_module:
        Optional dotted Python import path of a module that contains your
        custom Fleuve ORM model classes (e.g. ``myproject.db.db_fleuve``).
        When provided together with the ``*_model_name`` parameters the UI
        will use those classes instead of the built-in defaults, so you can
        point it at tables with non-standard names or custom body types.
    event_model_name:
        Name of the ``StoredEvent`` subclass inside *models_module*.
    activity_model_name:
        Name of the ``Activity`` subclass inside *models_module*.
    delay_schedule_model_name:
        Name of the ``DelaySchedule`` subclass inside *models_module*.
    subscription_model_name:
        Name of the ``Subscription`` subclass inside *models_module*.
    """
    import uvicorn

    frontend_dist_path = _get_frontend_dist_path()
    if not frontend_dist_path or not (frontend_dist_path / "index.html").exists():
        logger.warning(
            "UI frontend not built. Run 'npm run build' in "
            "fleuve/templates/ui_addon/ui/frontend to enable the web interface. "
            "The API will still work."
        )

    event_model = _resolve_model(models_module, event_model_name, DefaultStoredEvent)
    activity_model = _resolve_model(models_module, activity_model_name, DefaultActivity)
    delay_schedule_model = _resolve_model(
        models_module, delay_schedule_model_name, DefaultDelaySchedule
    )
    subscription_model = _resolve_model(
        models_module, subscription_model_name, DefaultSubscription
    )

    if models_module:
        logger.info(f"Using custom models from module '{models_module}'")

    async def _create_app():
        session_maker = await _create_session_maker()
        return create_app(
            session_maker=session_maker,
            event_model=event_model,
            activity_model=activity_model,
            delay_schedule_model=delay_schedule_model,
            subscription_model=subscription_model,
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
