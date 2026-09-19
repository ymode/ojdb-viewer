#!/bin/bash
# OJDB Viewer Installation Script

set -e  # Exit on any error

# Configuration
APP_NAME="OJDBViewer"
INSTALL_DIR="/opt/ojdb-viewer"
DESKTOP_FILE="/usr/share/applications/ojdb-viewer.desktop"
LAUNCHER_SCRIPT="/usr/local/bin/ojdb-viewer"

echo "🔧 Installing OJDB Viewer..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (use sudo)"
    exit 1
fi

# Install system dependencies
echo "📦 Installing system dependencies..."
apt update
apt install -y python3 python3-pip python3-venv python3-pyqt5 libqt5gui5t64 qt5-gtk-platformtheme

# Create installation directory
echo "📁 Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy files
echo "📋 Copying application files..."
cp sqlite_browser.py "$INSTALL_DIR/"
cp ojdb_core.py "$INSTALL_DIR/"
cp requirements.txt "$INSTALL_DIR/"
cp icon.png "$INSTALL_DIR/"
cp README.md "$INSTALL_DIR/"

# Create virtual environment and install dependencies
echo "🐍 Setting up Python environment..."
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install PyQt5

# Create launcher script
echo "🚀 Creating launcher script..."
cat > "$LAUNCHER_SCRIPT" << 'EOF'
#!/bin/bash
# No cd: relative database paths must resolve from the caller's directory
exec /opt/ojdb-viewer/venv/bin/python /opt/ojdb-viewer/sqlite_browser.py "$@"
EOF

chmod +x "$LAUNCHER_SCRIPT"

# Create desktop entry
echo "🖥️ Creating desktop entry..."
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=OJDB Viewer
Comment=Our Jank Database Viewer - Browse and explore SQLite database files
Exec=$LAUNCHER_SCRIPT %f
Icon=$INSTALL_DIR/icon.png
Terminal=false
Categories=Development;Database;
MimeType=application/x-sqlite3;application/vnd.sqlite3;
StartupNotify=true
Keywords=sqlite;database;browser;sql;ojdb;jank;
EOF

# Update desktop database
echo "🔄 Updating desktop database..."
update-desktop-database

# Set permissions
echo "🔐 Setting permissions..."
chown -R root:root "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"
chmod +x "$DESKTOP_FILE"

echo ""
echo "✅ Installation complete!"
echo ""
echo "🎯 You can now:"
echo "   • Launch from Applications menu: 'OJDB Viewer'"
echo "   • Run from terminal: ojdb-viewer"
echo "   • Open .db files by right-clicking and selecting 'Open With OJDB Viewer'"
echo ""
echo "📁 Installed to: $INSTALL_DIR"
echo "🖥️ Desktop entry: $DESKTOP_FILE"
echo "🚀 Launcher: $LAUNCHER_SCRIPT" 