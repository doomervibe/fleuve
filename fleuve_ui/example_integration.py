"""Example integration of Fleuve UI into an existing Fleuve project.

This shows how to integrate the Fleuve UI into your existing FastAPI application.
"""
from pathlib import Path
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

# Import your database models
# from your_project.db_models import StoredEvent, Activity, DelaySchedule, Subscription

# Import the Fleuve UI
from fleuve_ui.backend.api import create_app


def integrate_ui(
    main_app: FastAPI,
    session_maker: async_sessionmaker,
    event_model,
    activity_model,
    delay_schedule_model,
    subscription_model,
    ui_path: str = "/ui",
    frontend_dist_path: Path | None = None,
):
    """
    Integrate Fleuve UI into your existing FastAPI application.
    
    Args:
        main_app: Your main FastAPI application
        session_maker: Database session maker
        event_model: Your StoredEvent model class
        activity_model: Your Activity model class
        delay_schedule_model: Your DelaySchedule model class
        subscription_model: Your Subscription model class
        ui_path: Path prefix for the UI (default: "/ui")
        frontend_dist_path: Path to frontend dist directory (optional, will use default if not provided)
    """
    if frontend_dist_path is None:
        # Default to the fleuve_ui frontend dist directory
        frontend_dist_path = Path(__file__).parent / "frontend" / "dist"
    
    # Create the UI app
    ui_app = create_app(
        session_maker=session_maker,
        event_model=event_model,
        activity_model=activity_model,
        delay_schedule_model=delay_schedule_model,
        subscription_model=subscription_model,
        frontend_dist_path=frontend_dist_path,
    )
    
    # Mount the UI app
    main_app.mount(ui_path, ui_app)
    
    return ui_app


# Example usage:
# 
# from fastapi import FastAPI
# from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
# from your_project.db_models import StoredEvent, Activity, DelaySchedule, Subscription
# 
# app = FastAPI()
# 
# # Your database setup
# engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
# session_maker = async_sessionmaker(engine)
# 
# # Integrate the UI
# integrate_ui(
#     main_app=app,
#     session_maker=session_maker,
#     event_model=StoredEvent,
#     activity_model=Activity,
#     delay_schedule_model=DelaySchedule,
#     subscription_model=Subscription,
#     ui_path="/ui",  # Access UI at http://localhost:8000/ui
# )
# 
# # Your other routes...
# @app.get("/api/my-endpoint")
# async def my_endpoint():
#     return {"message": "Hello"}
# 
# # Run with: uvicorn main:app --reload
