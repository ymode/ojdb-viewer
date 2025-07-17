#!/bin/bash
# Create Portable OJDB Viewer Package

set -e

APP_NAME="OJDBViewer"
VERSION="1.0"
PACKAGE_NAME="${APP_NAME}-${VERSION}-portable"

echo "📦 Creating portable package: $PACKAGE_NAME"

# Create package directory
mkdir -p "$PACKAGE_NAME"

# Copy essential files
echo "📋 Copying files..."
cp sqlite_browser.py "$PACKAGE_NAME/"
cp requirements.txt "$PACKAGE_NAME/"
cp icon.png "$PACKAGE_NAME/"
cp README.md "$PACKAGE_NAME/"

# Create portable run script
echo "🚀 Creating portable launcher..."
cat > "$PACKAGE_NAME/run_portable.sh" << 'EOF'
#!/bin/bash
# Portable OJDB Viewer Launcher

# Get script directory
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "🔧 First-time setup: Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📦 Installing dependencies..."
    pip install PyQt5
    echo "✅ Setup complete!"
else
    source venv/bin/activate
fi

echo "🚀 Starting OJDB Viewer..."
python sqlite_browser.py "$@"
EOF

chmod +x "$PACKAGE_NAME/run_portable.sh"

# Create Windows batch file
cat > "$PACKAGE_NAME/run_portable.bat" << 'EOF'
@echo off
cd /d "%~dp0"

if not exist "venv" (
    echo First-time setup: Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install PyQt5
    echo Setup complete!
) else (
    call venv\Scripts\activate.bat
)

echo Starting OJDB Viewer...
python sqlite_browser.py %*
pause
EOF

# Create installation instructions
cat > "$PACKAGE_NAME/INSTALL.txt" << EOF
OJDB Viewer (Our Jank Database Viewer) - Portable Version $VERSION
=================================================================

QUICK START:
-----------
Linux/Mac:   ./run_portable.sh
Windows:     run_portable.bat

REQUIREMENTS:
------------
- Python 3.6 or higher
- Internet connection (first run only, to download dependencies)

FIRST RUN:
---------
On first run, the script will automatically:
1. Create a virtual environment
2. Download and install PyQt5
3. Launch the application

This may take a few minutes on the first run.

USAGE:
-----
1. Run the launcher script for your platform
2. Use File → Open Database to load a SQLite file
3. Browse tables and data in the interface

FILES INCLUDED:
--------------
- sqlite_browser.py    : Main application
- run_portable.sh      : Linux/Mac launcher
- run_portable.bat     : Windows launcher
- requirements.txt     : Python dependencies
- icon.png            : Application icon
- README.md           : Detailed documentation
- INSTALL.txt         : This file

For system installation, see README.md for instructions.
EOF

# Create archive
echo "🗜️ Creating archive..."
tar -czf "${PACKAGE_NAME}.tar.gz" "$PACKAGE_NAME"
zip -r "${PACKAGE_NAME}.zip" "$PACKAGE_NAME" > /dev/null

# Cleanup
rm -rf "$PACKAGE_NAME"

echo ""
echo "✅ Portable package created successfully!"
echo ""
echo "📦 Archives created:"
echo "   • ${PACKAGE_NAME}.tar.gz  (Linux/Mac)"
echo "   • ${PACKAGE_NAME}.zip     (Windows/All)"
echo ""
echo "🎯 Users can:"
echo "   1. Download and extract the archive"
echo "   2. Run the launcher script for their platform"
echo "   3. The app will auto-setup on first run" 