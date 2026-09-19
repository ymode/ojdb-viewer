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
if command -v pacman >/dev/null 2>&1; then
    # Arch / Omarchy / Manjaro. qt6-wayland gives native Wayland (Hyprland) support
    pacman -S --needed --noconfirm python python-pyqt6 qt6-wayland desktop-file-utils
elif command -v apt-get >/dev/null 2>&1; then
    # Debian / Ubuntu
    apt-get update
    apt-get install -y python3 python3-venv python3-pyqt6 desktop-file-utils
elif command -v dnf >/dev/null 2>&1; then
    # Fedora
    dnf install -y python3 python3-pyqt6 desktop-file-utils
else
    echo "⚠️ Unknown package manager - skipping system packages."
    echo "   Make sure python3 (with venv) is installed; PyQt6 will be installed with pip."
fi

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
# Reuse the distro's PyQt6 when present; fall back to pip otherwise
python3 -m venv --system-site-packages venv
if ! venv/bin/python -c "import PyQt6.QtWidgets" >/dev/null 2>&1; then
    venv/bin/pip install -r requirements.txt
fi

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
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database
fi

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