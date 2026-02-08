# {{project_title}} UI

Web-based dashboard for monitoring and managing your {{project_title}} workflows.

## Features

- **Workflow List**: View all workflow instances across all workflow types
- **Workflow Detail**: Inspect individual workflow states and event history
- **Event Explorer**: Browse and filter all events in the system
- **Activity Monitor**: Track side effect execution and retries
- **Delay Viewer**: Monitor scheduled delayed operations
- **Real-time Stats**: Dashboard with workflow statistics

## Quick Start

### 1. Install Backend Dependencies

The backend requires FastAPI and Uvicorn:

```bash
pip install fastapi uvicorn[standard]
```

### 2. Build the Frontend

```bash
cd ui/frontend
npm install
npm run build
```

###3. Start the UI Server

```bash
# From project root
chmod +x start_ui.sh
./start_ui.sh
```

Or run directly:

```bash
python ui/server.py
```

The UI will be available at `http://localhost:8001`

## Development

### Frontend Development

For frontend development with hot reload:

```bash
cd ui/frontend
npm run dev
```

This starts the Vite dev server on `http://localhost:5173` with CORS configured to connect to the API at `http://localhost:8001`.

### Backend API

The API is available at `http://localhost:8001/api` with the following endpoints:

- `GET /api/workflow-types` - List all workflow types
- `GET /api/workflows` - List workflow instances
- `GET /api/workflows/{workflow_id}` - Get workflow details
- `GET /api/events` - List all events
- `GET /api/activities` - List activities
- `GET /api/delays` - List delay schedules
- `GET /api/stats` - Get system statistics

### Configuration

Set environment variables:

- `DATABASE_URL` - PostgreSQL connection string (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/{{project_name}}`)
- `UI_PORT` - Server port (default: `8001`)
- `UI_HOST` - Server host (default: `0.0.0.0`)

## Architecture

- **Backend**: FastAPI server that queries the shared database tables
- **Frontend**: React + Vite + TailwindCSS single-page application
- **Data Flow**: Frontend → REST API → PostgreSQL

The UI reads from the same database tables that your workflows write to:
- `events` table for all workflow events
- `activities` table for side effect execution
- `delay_schedules` table for scheduled operations
- `subscriptions` table for cross-workflow subscriptions

## Troubleshooting

**Frontend not showing:**
- Make sure you ran `npm run build` in `ui/frontend/`
- Check that `ui/frontend/dist/index.html` exists

**API errors:**
- Verify DATABASE_URL is set correctly
- Ensure PostgreSQL is running
- Check that database tables exist (run your workflow once to create them)

**CORS errors (development):**
- Frontend dev server (port 5173) is configured to connect to API (port 8001)
- If using different ports, update `ui/frontend/vite.config.js`
