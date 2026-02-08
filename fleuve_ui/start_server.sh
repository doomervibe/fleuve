#!/bin/bash
# Start the Fleuve Framework UI server

echo "Starting Fleuve Framework UI server..."
echo "Make sure PostgreSQL is running and DATABASE_URL is set correctly!"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Get the project root (parent of fleuve_ui directory)
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Activate virtual environment if it exists
if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Change to the project root
cd "$PROJECT_ROOT"

# Add project root to PYTHONPATH and run the server
PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH" python "$SCRIPT_DIR/server.py"
