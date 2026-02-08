# Fleuve Framework UI

A comprehensive, generic UI for the LES (Lightweight Event Sourcing) Framework that works with any workflow type.

## Features

- **Dashboard**: Overview statistics, charts, and recent workflows
- **Workflow List**: Browse, search, and filter workflows with pagination
- **Workflow Detail**: View workflow state, event timeline, activities, delays, and time travel
- **Event Explorer**: Browse and filter events across all workflows
- **Activity Monitor**: Monitor action execution, retries, and errors
- **Delay Viewer**: View scheduled delays with live countdown timers
- **Real-time Updates**: Automatic polling for live data updates

## Installation

### Backend

The backend is a Python module that can be integrated into any Fleuve project:

```python
from pathlib import Path
from fleuve_ui.backend.api import create_app
from your_project.db_models import StoredEvent, Activity, DelaySchedule, Subscription
from sqlalchemy.ext.asyncio import async_sessionmaker

# Create the UI app
app = create_app(
    session_maker=session_maker,
    event_model=StoredEvent,
    activity_model=Activity,
    delay_schedule_model=DelaySchedule,
    subscription_model=Subscription,
    frontend_dist_path=Path(__file__).parent / "fleuve_ui" / "frontend" / "dist",
)
```

### Frontend

1. Install dependencies:
```bash
cd fleuve_ui/frontend
npm install
```

2. Build for production:
```bash
npm run build
```

The built files will be in `fleuve_ui/frontend/dist/` and will be served by the FastAPI backend.

## Development

### Frontend Development

```bash
cd fleuve_ui/frontend
npm run dev
```

The frontend will run on `http://localhost:5173` (or another port if 5173 is taken).

### Backend Development

The backend can be mounted in your existing FastAPI app or run standalone:

```python
from fastapi import FastAPI
from fleuve_ui.backend.api import create_app

# Option 1: Mount as sub-application
main_app = FastAPI()
ui_app = create_app(...)
main_app.mount("/ui", ui_app)

# Option 2: Use as main app
app = create_app(...)
```

## Usage

Once the UI is running, access it at the root URL of your FastAPI server. The UI provides:

1. **Dashboard**: Overview of all workflows and statistics
2. **Workflows**: List and search all workflows
3. **Events**: Explore events across workflows
4. **Activities**: Monitor action execution
5. **Delays**: View scheduled delays

## Architecture

- **Backend**: FastAPI with generic endpoints that work with any workflow type
- **Frontend**: React with Vite, Tailwind CSS, and React Router
- **Real-time**: Polling-based updates (can be upgraded to WebSocket)

## API Endpoints

- `GET /api/workflow-types` - List all workflow types
- `GET /api/workflows` - List workflows with filtering
- `GET /api/workflows/{id}` - Get workflow details
- `GET /api/workflows/{id}/events` - Get workflow events
- `GET /api/workflows/{id}/state/{version}` - Get state at version (time travel)
- `GET /api/events` - List events with filtering
- `GET /api/activities` - List activities with filtering
- `GET /api/delays` - List delays with filtering
- `GET /api/stats` - Get dashboard statistics

## License

MIT
