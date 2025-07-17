#!/bin/bash
# SQLite Browser Startup Script

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "Installing dependencies..."
    pip install PyQt5
else
    source venv/bin/activate
fi

echo "Starting SQLite Browser..."
python sqlite_browser.py 