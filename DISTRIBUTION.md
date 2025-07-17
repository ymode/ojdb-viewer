# OJDB Viewer (Our Jank Database Viewer) - Distribution Guide

This guide explains how to package and distribute the OJDB Viewer application for end users.

## 🎯 Quick Start for Distribution

### Create Portable Package (Recommended for most users)
```bash
./create_package.sh
```
**Output:** `OJDBViewer-1.0-portable.tar.gz` and `.zip`
**Best for:** Sharing with users who want a simple download-and-run experience

### System Installation Package
```bash
# Users run this on their system:
sudo ./install.sh
```
**Best for:** IT departments, permanent installations, power users

### Standalone Executable
```bash
python3 build_executable.py
```
**Output:** Single executable file in `dist/`
**Best for:** Simple distribution, but larger file size

## 📦 Package Comparison

| Method | File Size | Setup Required | System Integration | Best For |
|--------|-----------|----------------|-------------------|----------|
| Portable Package | Small | Auto-setup on first run | None | General users |
| System Install | N/A | Manual install | Full (menu, file association) | Permanent use |
| Standalone Executable | Large | None | None | Simple sharing |

## 🚀 Distribution Methods

### 1. GitHub Releases
Upload the portable packages to GitHub releases:
```bash
./create_package.sh
# Upload OJDBViewer-1.0-portable.tar.gz and .zip to GitHub
```

### 2. Direct Download
Host the files on a web server and provide download links.

### 3. Package Repositories
- **Ubuntu/Debian:** Create `.deb` package
- **Fedora/RHEL:** Create `.rpm` package  
- **Arch:** Create PKGBUILD
- **Flatpak:** Create Flatpak package

## 📋 What Each Package Contains

### Portable Package
- `sqlite_browser.py` - Main application
- `run_portable.sh` - Linux/Mac launcher
- `run_portable.bat` - Windows launcher
- `requirements.txt` - Dependencies list
- `icon.png` - Application icon
- `README.md` - Documentation
- `INSTALL.txt` - Quick start guide

### System Installation
Installs to:
- `/opt/ojdb-viewer/` - Application files
- `/usr/local/bin/ojdb-viewer` - Command launcher
- `/usr/share/applications/ojdb-viewer.desktop` - Menu entry

## 🔧 Customization

### Branding
Edit these files before packaging:
- `sqlite_browser.py` - Application title, version
- `icon.png` - Application icon
- `README.md` - Documentation
- Desktop files - Application name, description

### Version Updates
Update version numbers in:
- `create_package.sh` - Package version
- `sqlite_browser.py` - Application version
- `README.md` - Version references

## 🛠️ Testing

Before distribution, test on clean systems:

1. **Portable Package Test:**
   ```bash
   # Extract package
   tar -xzf OJDBViewer-1.0-portable.tar.gz
   cd OJDBViewer-1.0-portable
   ./run_portable.sh
   ```

2. **System Install Test:**
   ```bash
   sudo ./install.sh
   ojdb-viewer
   sudo ./uninstall.sh
   ```

3. **Executable Test:**
   ```bash
   python3 build_executable.py
   ./dist/OJDBViewer
   ```

## 📤 Upload Checklist

Before distributing:
- [ ] Test on clean Linux system
- [ ] Test portable package on Windows (if targeting)
- [ ] Verify all files are included
- [ ] Check README is up to date
- [ ] Test database file opening
- [ ] Verify desktop integration works
- [ ] Create release notes
- [ ] Tag version in git

## 🎁 Ready-to-Use Distribution

To create everything at once:
```bash
# Create all distribution formats
./create_package.sh
python3 build_executable.py

# Your distribution files:
ls -la *.tar.gz *.zip dist/
```

Users can then choose their preferred installation method! 