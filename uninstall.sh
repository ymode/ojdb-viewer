#!/bin/bash
# OJDB Viewer Uninstall Script

set -e

# Configuration
INSTALL_DIR="/opt/ojdb-viewer"
DESKTOP_FILE="/usr/share/applications/ojdb-viewer.desktop"
LAUNCHER_SCRIPT="/usr/local/bin/ojdb-viewer"

echo "🗑️ Uninstalling OJDB Viewer..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (use sudo)"
    exit 1
fi

# Remove files
echo "📁 Removing installation directory..."
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "✅ Removed: $INSTALL_DIR"
else
    echo "ℹ️ Directory not found: $INSTALL_DIR"
fi

echo "🖥️ Removing desktop entry..."
if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    echo "✅ Removed: $DESKTOP_FILE"
else
    echo "ℹ️ File not found: $DESKTOP_FILE"
fi

echo "🚀 Removing launcher script..."
if [ -f "$LAUNCHER_SCRIPT" ]; then
    rm -f "$LAUNCHER_SCRIPT"
    echo "✅ Removed: $LAUNCHER_SCRIPT"
else
    echo "ℹ️ File not found: $LAUNCHER_SCRIPT"
fi

# Update desktop database
echo "🔄 Updating desktop database..."
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database
fi

echo ""
echo "✅ OJDB Viewer uninstalled successfully!" 