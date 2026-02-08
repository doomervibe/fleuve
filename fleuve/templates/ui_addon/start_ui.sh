#!/bin/bash
# Start the {{project_title}} UI server

echo "Starting {{project_title}} UI server..."
echo "Make sure PostgreSQL is running and DATABASE_URL is set correctly!"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment if it exists
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
elif [ -d "$SCRIPT_DIR/venv" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Run the UI server
python "$SCRIPT_DIR/ui_server.py"
