"""Standalone server for Fleuve Framework UI."""
import asyncio
import logging
import os
import sys
from pathlib import Path

import uvicorn
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Add the project root to the path so we can import fleuve modules
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fleuve.postgres import StoredEvent, Activity, DelaySchedule, Subscription
from fleuve_ui.backend.api import create_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_session_maker():
    """Create database session maker from environment variables."""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/les"
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


def main():
    """Run the Fleuve UI server."""
    # Get port from environment or use default
    port = int(os.getenv("LES_UI_PORT", "8001"))
    host = os.getenv("LES_UI_HOST", "0.0.0.0")
    
    # Get frontend path
    frontend_dist_path = Path(__file__).parent / "frontend" / "dist"
    
    if not frontend_dist_path.exists() or not (frontend_dist_path / "index.html").exists():
        logger.warning(
            f"Fleuve UI frontend not built. Run 'npm run build' in {frontend_dist_path.parent} "
            "to enable the UI. The API will still work, but the web interface won't be available."
        )
    
    async def create_app_with_db():
        """Create the app with database connection."""
        session_maker = await create_session_maker()
        
        app = create_app(
            session_maker=session_maker,
            event_model=StoredEvent,
            activity_model=Activity,
            delay_schedule_model=DelaySchedule,
            subscription_model=Subscription,
            frontend_dist_path=frontend_dist_path if frontend_dist_path.exists() else None,
        )
        return app
    
    # Create the app
    app = asyncio.run(create_app_with_db())
    
    logger.info(f"Starting Fleuve Framework UI server on http://{host}:{port}")
    logger.info(f"Frontend path: {frontend_dist_path}")
    logger.info(f"Frontend available: {frontend_dist_path.exists() and (frontend_dist_path / 'index.html').exists()}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
