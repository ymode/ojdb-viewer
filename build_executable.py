#!/usr/bin/env python3
"""
Build script for creating a standalone OJDB Viewer executable
"""

import subprocess
import sys
import os
from pathlib import Path

def install_pyinstaller():
    """Install PyInstaller if not already installed"""
    try:
        import PyInstaller
        print("PyInstaller already installed")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

def build_executable():
    """Build the standalone executable"""
    
    # Ensure we have PyInstaller
    install_pyinstaller()
    
    # Get the current directory
    current_dir = Path.cwd()
    
    # PyInstaller command
    cmd = [
        "pyinstaller",
        "--onefile",  # Single file executable
        "--windowed",  # No console window
        "--name=OJDBViewer",
        "--icon=icon.png",
        "--add-data=icon.png:.",  # Include icon in bundle
        "sqlite_browser.py"
    ]
    
    print("Building executable...")
    print(f"Running: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd)
        print("\n✅ Build successful!")
        print(f"Executable created: {current_dir}/dist/OJDBViewer")
        print("\nTo test the executable:")
        print(f"  cd {current_dir}/dist")
        print("  ./OJDBViewer")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    if not os.path.exists("sqlite_browser.py"):
        print("❌ sqlite_browser.py not found in current directory")
        sys.exit(1)
    
    if not os.path.exists("icon.png"):
        print("❌ icon.png not found in current directory")
        sys.exit(1)
    
    success = build_executable()
    sys.exit(0 if success else 1) 