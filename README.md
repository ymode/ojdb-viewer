# OJDB Viewer (Our Jank Database Viewer)

A Python Qt5 application for browsing and exploring SQLite database files.

## Features

- **Open any SQLite database file** - Browse .db, .sqlite, .sqlite3 files
- **Database structure view** - See all tables and columns in a tree view
- **Data browsing** - View table contents with pagination
- **Search and filtering** - Search within specific columns or across all text columns
- **Schema viewer** - View the complete database schema (CREATE statements)
- **Threaded operations** - Non-blocking database operations for better UI responsiveness

## Installation

1. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Linux/Mac
# or
venv\Scripts\activate     # On Windows
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python sqlite_browser.py
```

## Usage

### Opening a Database
- Use File → Open Database menu or the application will automatically load `devices.db` if present
- Select any SQLite database file (.db, .sqlite, .sqlite3)

### Browsing Data
- Click on any table name in the left tree view to load its data
- Use the search box to filter data by entering search terms
- Select a specific column to search within, or leave "All Columns" to search all text fields
- Navigate through large datasets using the Previous/Next pagination buttons
- Adjust rows per page using the spinner control

### Viewing Schema
- Click the "Schema" tab to see all CREATE statements for the database
- This shows the complete structure including indexes, triggers, etc.

### Navigation Tips
- The tree view shows table names with column count
- Expand tables to see individual columns with their types and constraints
- Primary key columns are marked with (PK)
- Non-nullable columns are marked with (NOT NULL)

## Example Database

The application includes support for the provided `devices.db` which contains:
- Device information (models, manufacturers, types)
- NSN (National Stock Number) references
- Device costs and specifications
- Communication capabilities
- Physical characteristics
- Standards references

## Technical Details

- Built with PyQt5 for cross-platform compatibility
- Uses SQLite3 for database operations
- Implements threading to prevent UI freezing during large queries
- Supports pagination for efficient handling of large datasets
- Includes error handling for database connection issues

## System Requirements

- Python 3.6+
- PyQt5
- SQLite3 (included with Python)
- Linux, Windows, or macOS

## Distribution & Packaging

### For End Users

#### Option 1: System Installation (Recommended)
Install system-wide with desktop integration:
```bash
sudo ./install.sh
```
This creates:
- Menu entry: Applications → Development → OJDB Viewer
- Terminal command: `ojdb-viewer`
- File association for .db files

To uninstall:
```bash
sudo ./uninstall.sh
```

#### Option 2: Portable Package
Create a portable version that users can run anywhere:
```bash
./create_package.sh
```
This creates `.tar.gz` and `.zip` files containing:
- Auto-setup launchers for Linux/Mac/Windows
- All necessary files
- No system installation required

#### Option 3: Standalone Executable
Create a single-file executable (requires more disk space):
```bash
python3 build_executable.py
```
The executable will be in the `dist/` directory.

### For Developers

#### Desktop Integration Only
To create just a desktop entry for the current installation:
```bash
cp ojdb-viewer.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/
```

### Distribution Files

- `install.sh` - System-wide installation script
- `uninstall.sh` - Removal script  
- `create_package.sh` - Creates portable packages
- `build_executable.py` - Creates standalone executable
- `ojdb-viewer.desktop` - Desktop entry file 