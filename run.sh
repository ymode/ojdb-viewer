#!/bin/bash
# OJDB Viewer Startup Script

# Resolve the app directory without cd, so relative database paths still work
DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

# Check if virtual environment exists
if [ ! -d "$DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$DIR/venv"
fi

# Check the import rather than the directory, so a venv from an older
# version (e.g. one that only has PyQt5) gets brought up to date
if ! "$DIR/venv/bin/python" -c "import PyQt6.QtWidgets" >/dev/null 2>&1; then
    echo "Installing dependencies..."
    "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt"
fi

echo "Starting OJDB Viewer..."
exec "$DIR/venv/bin/python" "$DIR/sqlite_browser.py" "$@"
