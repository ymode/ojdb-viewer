# OJDB Viewer (Our Jank Database Viewer)

A Python Qt5 application for browsing and exploring SQLite database files.

## Features

- **Open any SQLite database file** - Browse .db, .sqlite, .sqlite3 files
- **Database structure view** - See all tables and columns in a tree view
- **Data browsing** - View table contents with pagination
- **Search and filtering** - Search within specific columns or across all text columns
- **SQL query tab** - Run your own read-only SQL and browse the results
- **Copy to clipboard** - Ctrl+C copies the selected rows or cells as tab-separated text
- **CSV export** - Export the current table view, with filter and sort applied, to CSV
- **Recent files** - Reopen databases from File → Open Recent; window layout is remembered between sessions
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
- Use File → Open Database menu, or pass a file on the command line: `python sqlite_browser.py path/to/file.db`
- Databases are opened read-only; the viewer never creates or modifies files
- Select any SQLite database file (.db, .sqlite, .sqlite3)

### Browsing Data
- Click on any table name in the left tree view to load its data
- Use the search box to filter data by entering search terms
- Select a specific column to search within, or leave "All Columns" to search every column
- Click a column header to sort the whole table by that column (click again to reverse)
- NULL values and BLOBs are shown as grey italic `NULL` / `<BLOB size>` markers
- Navigate through large datasets using the Previous/Next pagination buttons
- Adjust rows per page using the spinner control

### Running Queries
- Open the "Query" tab, write a single SQL statement and press Ctrl+Enter (or click Run)
- The database is opened read-only, so `INSERT`, `UPDATE`, `DELETE` and similar statements fail with an error instead of changing the file
- Results are capped at 10,000 rows; add a `LIMIT` or `WHERE` to narrow them
- While a query is running the Run button becomes Cancel

### Exporting Data
- Tools → Export Data (Ctrl+E) writes every row of the current view to a CSV file, not just the visible page
- The active search filter and sort order are applied to the export
- NULL values are written as empty fields and BLOBs as `0x` hex strings

### Viewing Schema
- Click the "Schema" tab to see all CREATE statements for the database
- This shows the complete structure including indexes, triggers, etc.

### Navigation Tips
- The tree view shows table names with column count
- Expand tables to see individual columns with their types and constraints
- Primary key columns are marked with (PK)
- Non-nullable columns are marked with (NOT NULL)

## Running the Tests

```bash
pip install -e ".[test]"
pytest
```

The GUI tests run headless (Qt's `offscreen` platform), so no display is needed. They are skipped if PyQt5 isn't installed. The suite also runs on every push via GitHub Actions.

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

#### Option 1: Install as a Python Tool (no root needed)
```bash
uv tool install git+https://github.com/ymode/ojdb-viewer
# or
pipx install git+https://github.com/ymode/ojdb-viewer
```
This puts an `ojdb-viewer` command on your PATH: `ojdb-viewer path/to/file.db`. It does not add a menu entry or file association; use the system installation below for those.

#### Option 2: System Installation
Install system-wide with desktop integration:
```bash
sudo ./install.sh
```
Supported: Arch-based distros (Arch, Omarchy, Manjaro) via `pacman`, Debian/Ubuntu via `apt`, and Fedora via `dnf`. On anything else the script skips system packages and installs PyQt5 with pip.
This creates:
- Menu entry: Applications → Development → OJDB Viewer
- Terminal command: `ojdb-viewer`
- File association for .db files

To uninstall:
```bash
sudo ./uninstall.sh
```

#### Option 3: Portable Package
Create a portable version that users can run anywhere:
```bash
./create_package.sh
```
This creates `.tar.gz` and `.zip` files containing:
- Auto-setup launchers for Linux/Mac/Windows
- All necessary files
- No system installation required

#### Option 4: Standalone Executable
Create a single-file executable (requires more disk space):
```bash
python3 build_executable.py
```
The executable will be in the `dist/` directory.

### For Developers

#### Desktop Integration Only
To create just a desktop entry (expects an `ojdb-viewer` command on your PATH, as created by `install.sh`):
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