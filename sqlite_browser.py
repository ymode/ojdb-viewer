#!/usr/bin/env python3
"""
OJDB Viewer (Our Jank Database Viewer)
A Python Qt6 application for browsing SQLite database files.
"""

import sys
import os
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTableView, QAbstractItemView,
                             QTreeWidget, QTreeWidgetItem, QSplitter, QFileDialog,
                             QMessageBox, QLineEdit, QLabel, QHeaderView, QTabWidget,
                             QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QStatusBar)
from PyQt6.QtCore import (Qt, QAbstractTableModel, QModelIndex, QSettings, QThread, QTimer,
                          pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut

from ojdb_core import (build_table_queries, connect_readonly, csv_value, export_csv, format_cell,
                       quote_ident, validate_database)


class DatabaseWorker(QThread):
    """Worker thread for database operations to prevent UI freezing"""
    data_ready = pyqtSignal(int, list, list, int)  # request_id, data, column_names, total_rows
    error_occurred = pyqtSignal(int, str)  # request_id, message
    
    def __init__(self, request_id, db_path, query, count_query, params=None):
        super().__init__()
        self.request_id = request_id
        self.db_path = db_path
        self.query = query
        self.count_query = count_query
        self.params = params or []
    
    def run(self):
        conn = None
        try:
            conn = connect_readonly(self.db_path)
            cursor = conn.cursor()
            cursor.execute(self.query, self.params)
            
            data = cursor.fetchall()
            column_names = [description[0] for description in cursor.description] if cursor.description else []
            
            cursor.execute(self.count_query, self.params)
            total_rows = cursor.fetchone()[0]
            
            self.data_ready.emit(self.request_id, data, column_names, total_rows)
        except Exception as e:
            self.error_occurred.emit(self.request_id, str(e))
        finally:
            if conn:
                conn.close()


class QueryWorker(QThread):
    """Worker thread that runs a user-written SQL statement"""
    query_done = pyqtSignal(int, list, list, bool, float)  # request_id, rows, column_names, truncated, seconds
    error_occurred = pyqtSignal(int, str)  # request_id, message
    
    def __init__(self, request_id, db_path, sql, max_rows):
        super().__init__()
        self.request_id = request_id
        self.db_path = db_path
        self.sql = sql
        self.max_rows = max_rows
        self.conn = None
    
    def cancel(self):
        """Abort the running statement; safe to call from the UI thread"""
        conn = self.conn
        if conn:
            try:
                conn.interrupt()
            except Exception:
                pass  # The query finished and closed the connection first
    
    def run(self):
        try:
            started = time.monotonic()
            self.conn = connect_readonly(self.db_path)
            cursor = self.conn.execute(self.sql)
            
            column_names = [description[0] for description in cursor.description] if cursor.description else []
            rows = cursor.fetchmany(self.max_rows + 1) if column_names else []
            truncated = len(rows) > self.max_rows
            
            self.query_done.emit(self.request_id, rows[:self.max_rows], column_names,
                                 truncated, time.monotonic() - started)
        except Exception as e:
            self.error_occurred.emit(self.request_id, str(e))
        finally:
            conn, self.conn = self.conn, None
            if conn:
                conn.close()


class ResultModel(QAbstractTableModel):
    """Read-only table model over a list of result rows"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.columns = []
        self.row_offset = 0
        self.placeholder_font = QFont()
        self.placeholder_font.setItalic(True)
        self.placeholder_color = QColor("#888")
    
    def set_results(self, rows, columns, row_offset=0):
        """Replace the model contents; row_offset numbers rows across pages"""
        self.beginResetModel()
        self.rows = rows
        self.columns = columns
        self.row_offset = row_offset
        self.endResetModel()
    
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)
    
    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = self.rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return format_cell(value)[0]
        # Distinguish NULL/BLOB markers from real text
        if role == Qt.ItemDataRole.FontRole and format_cell(value)[1]:
            return self.placeholder_font
        if role == Qt.ItemDataRole.ForegroundRole and format_cell(value)[1]:
            return self.placeholder_color
        return None
    
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.columns[section]
        return str(self.row_offset + section + 1)
    
    def copy_text(self, index):
        """Clipboard text for a cell: NULL is empty, BLOBs are hex"""
        return str(csv_value(self.rows[index.row()][index.column()]))


def create_result_view(model):
    """Create a read-only table view with Ctrl+C support"""
    view = QTableView()
    view.setModel(model)
    view.setAlternatingRowColors(True)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.verticalHeader().setDefaultSectionSize(25)  # Row height
    copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, view)
    copy_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
    copy_shortcut.activated.connect(lambda: copy_selection(view))
    return view


def copy_selection(view):
    """Copy the selected cells to the clipboard as tab-separated text"""
    indexes = view.selectionModel().selectedIndexes()
    if not indexes:
        return
    model = view.model()
    rows = sorted({index.row() for index in indexes})
    columns = sorted({index.column() for index in indexes})
    selected = {(index.row(), index.column()) for index in indexes}
    lines = []
    for row in rows:
        lines.append("\t".join(
            model.copy_text(model.index(row, col)) if (row, col) in selected else ""
            for col in columns))
    QApplication.clipboard().setText("\n".join(lines))


def size_columns(view, column_names):
    """Fit columns to their content within sensible limits"""
    header = view.horizontalHeader()
    
    # Auto-resize columns to content, but with constraints
    view.resizeColumnsToContents()
    
    # Set reasonable column width limits
    for col in range(len(column_names)):
        current_width = view.columnWidth(col)
        # Set minimum and maximum widths
        min_width = max(80, len(column_names[col]) * 8)  # Based on header text
        max_width = 300  # Maximum column width
        
        if current_width < min_width:
            view.setColumnWidth(col, min_width)
        elif current_width > max_width:
            view.setColumnWidth(col, max_width)
    
    # Set resize modes
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    
    # If we have extra space, distribute it among columns
    total_width = sum(view.columnWidth(col) for col in range(len(column_names)))
    available_width = view.viewport().width()
    
    if total_width < available_width and len(column_names) > 0:
        # Stretch the last column to fill remaining space
        header.setSectionResizeMode(len(column_names) - 1, QHeaderView.ResizeMode.Stretch)


class ExportWorker(QThread):
    """Worker thread that writes the current view to a CSV file"""
    export_done = pyqtSignal(str, int)  # out_path, row_count
    error_occurred = pyqtSignal(str)
    
    def __init__(self, db_path, out_path, **view):
        super().__init__()
        self.db_path = db_path
        self.out_path = out_path
        self.view = view
    
    def run(self):
        try:
            row_count = export_csv(self.db_path, self.out_path, **self.view)
            self.export_done.emit(self.out_path, row_count)
        except Exception as e:
            self.error_occurred.emit(str(e))


MAX_RECENT_FILES = 10
MAX_QUERY_ROWS = 10000  # Cap on rows shown for a user-written query


class SQLiteBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db_path = None
        self.current_table = None
        self.current_offset = 0
        self.rows_per_page = 100
        self.updating_combo = False  # Flag to prevent recursion
        self.current_columns = []
        self.sort_column = None
        self.sort_descending = False
        self.request_id = 0  # Results from older requests are discarded
        self.workers = set()  # Keep running threads referenced until they finish
        self.settings = QSettings()
        self.query_request_id = 0
        self.query_worker = None
        
        # Debounce typing so each keystroke doesn't start a query
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self.apply_filter)
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("OJDB Viewer (Our Jank Database Viewer)")
        self.setGeometry(100, 100, 1400, 900)  # Larger default window
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)  # Smaller margins
        main_layout.setSpacing(5)  # Minimal spacing
        
        # Create splitter for tree and content (no database info bar!)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)  # Prevent collapsing
        main_layout.addWidget(splitter)
        self.splitter = splitter
        
        # Create database tree widget
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("Database Structure")
        self.tree_widget.itemClicked.connect(self.tree_item_clicked)
        self.tree_widget.setMinimumWidth(250)  # Minimum width
        self.tree_widget.setMaximumWidth(400)  # Maximum width
        splitter.addWidget(self.tree_widget)
        
        # Create right panel with tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.setMinimumWidth(600)  # Ensure adequate space for data
        splitter.addWidget(self.tab_widget)
        
        # Data tab
        self.create_data_tab()
        
        # Query tab
        self.create_query_tab()
        
        # Schema tab
        self.create_schema_tab()
        
        # Set splitter proportions (tree: data = 1:3 ratio)
        splitter.setSizes([350, 1050])
        splitter.setStretchFactor(0, 0)  # Tree doesn't stretch
        splitter.setStretchFactor(1, 1)  # Data area stretches
        
        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Initialize status bar
        self.update_status_bar("No database loaded")
        
        # Restore window layout from the last session
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value("splitterState")
        if splitter_state:
            self.splitter.restoreState(splitter_state)
        
    
    def create_menu_bar(self):
        """Create the application menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('&File')
        
        # Open Database action
        open_action = file_menu.addAction('&Open Database...')
        open_action.setShortcut('Ctrl+O')
        open_action.setStatusTip('Open SQLite database file')
        open_action.triggered.connect(self.open_database)
        
        file_menu.addSeparator()
        
        # Recent files submenu
        self.recent_menu = file_menu.addMenu('Open &Recent')
        self.update_recent_menu()
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = file_menu.addAction('E&xit')
        exit_action.setShortcut('Ctrl+Q')
        exit_action.setStatusTip('Exit application')
        exit_action.triggered.connect(self.close)
        
        # Tools menu
        tools_menu = menubar.addMenu('&Tools')
        
        # Refresh action
        refresh_action = tools_menu.addAction('&Refresh')
        refresh_action.setShortcut('F5')
        refresh_action.setStatusTip('Refresh database structure')
        refresh_action.triggered.connect(self.refresh_database)
        
        tools_menu.addSeparator()
        
        # Export data action, enabled once a table is selected
        self.export_action = tools_menu.addAction('&Export Data...')
        self.export_action.setShortcut('Ctrl+E')
        self.export_action.setStatusTip('Export the current table view (all pages) to CSV')
        self.export_action.triggered.connect(self.export_data)
        self.export_action.setEnabled(False)
        
        # View menu
        view_menu = menubar.addMenu('&View')
        
        # Show/hide tree action
        toggle_tree_action = view_menu.addAction('&Toggle Database Tree')
        toggle_tree_action.setShortcut('Ctrl+T')
        toggle_tree_action.setStatusTip('Show/hide database structure tree')
        toggle_tree_action.triggered.connect(self.toggle_tree_visibility)
        
        # Help menu
        help_menu = menubar.addMenu('&Help')
        
        # About action
        about_action = help_menu.addAction('&About')
        about_action.setStatusTip('About OJDB Viewer')
        about_action.triggered.connect(self.show_about)
    
    def recent_files(self):
        """Recently opened database paths, newest first"""
        files = self.settings.value("recentFiles") or []
        if isinstance(files, str):  # QSettings returns a bare string for one entry
            files = [files]
        return list(files)
    
    def add_recent_file(self, db_path):
        """Move db_path to the top of the recent files list"""
        files = [f for f in self.recent_files() if f != db_path]
        files.insert(0, db_path)
        self.settings.setValue("recentFiles", files[:MAX_RECENT_FILES])
        self.update_recent_menu()
    
    def remove_recent_file(self, db_path):
        """Drop db_path from the recent files list"""
        self.settings.setValue("recentFiles", [f for f in self.recent_files() if f != db_path])
        self.update_recent_menu()
    
    def clear_recent_files(self):
        """Empty the recent files list"""
        self.settings.setValue("recentFiles", [])
        self.update_recent_menu()
    
    def update_recent_menu(self):
        """Rebuild the recent files submenu"""
        self.recent_menu.clear()
        files = self.recent_files()
        if not files:
            self.recent_menu.addAction('No recent files').setEnabled(False)
            return
        
        for index, path in enumerate(files, start=1):
            action = self.recent_menu.addAction(f"&{index % 10}  {path.replace('&', '&&')}")
            action.setStatusTip(path)
            action.triggered.connect(lambda checked=False, p=path: self.open_recent_file(p))
        
        self.recent_menu.addSeparator()
        self.recent_menu.addAction('&Clear Recent Files').triggered.connect(self.clear_recent_files)
    
    def open_recent_file(self, db_path):
        """Open a recent file, forgetting it if it can no longer be opened"""
        if not self.load_database(db_path):
            self.remove_recent_file(db_path)
    
    def export_data(self):
        """Export every row of the current view (filter and sort applied) to CSV"""
        if not self.db_path or not self.current_table:
            return
        
        default_dir = self.settings.value("exportDir") or os.path.dirname(self.db_path)
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Export Data", os.path.join(default_dir, f"{self.current_table}.csv"),
            "CSV Files (*.csv);;All Files (*)")
        if not out_path:
            return
        self.settings.setValue("exportDir", os.path.dirname(out_path))
        
        worker = ExportWorker(
            self.db_path, out_path,
            table=self.current_table, columns=self.current_columns,
            search_text=self.search_input.text(),
            selected_column=self.column_combo.currentText(),
            order_by=self.sort_column, descending=self.sort_descending)
        worker.export_done.connect(self.export_finished)
        worker.error_occurred.connect(self.export_failed)
        worker.finished.connect(lambda w=worker: self.worker_finished(w))
        self.workers.add(worker)
        self.export_action.setEnabled(False)  # One export at a time
        self.update_status_bar(f"Exporting '{self.current_table}'...", os.path.basename(self.db_path))
        worker.start()
    
    def export_finished(self, out_path, row_count):
        """Report a completed export"""
        self.export_action.setEnabled(self.current_table is not None)
        db_name = os.path.basename(self.db_path) if self.db_path else None
        self.update_status_bar(f"Exported {row_count} rows to {out_path}", db_name)
    
    def export_failed(self, error_message):
        """Report a failed export"""
        self.export_action.setEnabled(self.current_table is not None)
        QMessageBox.critical(self, "Export Error", f"Failed to export data:\n{error_message}")
    
    def refresh_database(self):
        """Refresh the database structure"""
        if self.db_path:
            db_name = os.path.basename(self.db_path)
            self.populate_tree()
            self.load_schema()
            self.update_status_bar("Database refreshed", db_name)
    
    def toggle_tree_visibility(self):
        """Toggle the visibility of the database tree"""
        self.tree_widget.setVisible(not self.tree_widget.isVisible())
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About OJDB Viewer (Our Jank Database Viewer)", 
                         "OJDB Viewer v1.0\n\n"
                         "A Python Qt6 application for browsing SQLite databases.\n\n"
                         "Features:\n"
                         "• Browse database structure\n"
                         "• View table data with pagination\n"
                         "• Search and filter data\n"
                         "• Run read-only SQL queries\n"
                         "• Export data to CSV\n"
                         "• View database schema\n\n"
                         "Built with Python and PyQt6")
    
    def create_data_tab(self):
        """Create the data viewing tab"""
        data_widget = QWidget()
        layout = QVBoxLayout(data_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Search and filter controls
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)
        
        filter_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term...")
        self.search_input.textChanged.connect(self.search_timer.start)
        self.search_input.setMinimumWidth(200)
        filter_layout.addWidget(self.search_input)
        
        filter_layout.addWidget(QLabel("Column:"))
        self.column_combo = QComboBox()
        self.column_combo.currentTextChanged.connect(self.apply_filter)
        self.column_combo.setMinimumWidth(150)
        filter_layout.addWidget(self.column_combo)
        
        self.clear_filter_button = QPushButton("Clear")
        self.clear_filter_button.clicked.connect(self.clear_filter)
        self.clear_filter_button.setMaximumWidth(80)
        filter_layout.addWidget(self.clear_filter_button)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # Table view
        self.table_model = ResultModel(self)
        self.table_view = create_result_view(self.table_model)
        # Sorting is done in SQL so it covers the whole table, not just this page
        self.table_view.setSortingEnabled(False)
        self.table_view.horizontalHeader().setSectionsClickable(True)
        self.table_view.horizontalHeader().sectionClicked.connect(self.header_clicked)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table_view)
        
        # Pagination controls
        pagination_layout = QHBoxLayout()
        pagination_layout.setSpacing(10)
        
        self.prev_button = QPushButton("◀ Previous")
        self.prev_button.clicked.connect(self.previous_page)
        self.prev_button.setEnabled(False)
        self.prev_button.setMaximumWidth(100)
        pagination_layout.addWidget(self.prev_button)
        
        self.page_label = QLabel("Page 1")
        self.page_label.setMinimumWidth(80)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pagination_layout.addWidget(self.page_label)
        
        self.next_button = QPushButton("Next ▶")
        self.next_button.clicked.connect(self.next_page)
        self.next_button.setEnabled(False)
        self.next_button.setMaximumWidth(100)
        pagination_layout.addWidget(self.next_button)
        
        pagination_layout.addWidget(QLabel("Rows per page:"))
        self.rows_spinbox = QSpinBox()
        self.rows_spinbox.setRange(10, 1000)
        self.rows_spinbox.setValue(100)
        self.rows_spinbox.valueChanged.connect(self.change_rows_per_page)
        self.rows_spinbox.setMaximumWidth(80)
        pagination_layout.addWidget(self.rows_spinbox)
        
        pagination_layout.addStretch()
        
        self.total_rows_label = QLabel("")
        self.total_rows_label.setStyleSheet("font-weight: bold; color: #666;")
        pagination_layout.addWidget(self.total_rows_label)
        
        layout.addLayout(pagination_layout)
        
        self.tab_widget.addTab(data_widget, "Data")
    
    def create_query_tab(self):
        """Create the SQL query tab"""
        query_widget = QWidget()
        layout = QVBoxLayout(query_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        query_splitter = QSplitter(Qt.Orientation.Vertical)
        query_splitter.setChildrenCollapsible(False)
        layout.addWidget(query_splitter)
        
        # Editor with run controls
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        
        self.query_input = QPlainTextEdit()
        self.query_input.setFont(QFont("Courier", 10))
        self.query_input.setPlaceholderText(
            "Write a single SQL statement and press Ctrl+Enter to run it.\n"
            "The database is opened read-only, so statements that modify it will fail.")
        editor_layout.addWidget(self.query_input)
        
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)
        
        self.run_query_button = QPushButton("Run")
        self.run_query_button.setToolTip("Run the statement (Ctrl+Enter)")
        self.run_query_button.clicked.connect(self.run_or_cancel_query)
        self.run_query_button.setMaximumWidth(100)
        controls_layout.addWidget(self.run_query_button)
        
        self.query_status = QLabel("")
        self.query_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.query_status.setWordWrap(True)
        controls_layout.addWidget(self.query_status, 1)
        
        editor_layout.addLayout(controls_layout)
        query_splitter.addWidget(editor_widget)
        
        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            shortcut = QShortcut(QKeySequence(keys), self.query_input)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self.run_query)
        
        # Results
        self.query_model = ResultModel(self)
        self.query_view = create_result_view(self.query_model)
        query_splitter.addWidget(self.query_view)
        
        query_splitter.setSizes([200, 500])
        query_splitter.setStretchFactor(0, 0)
        query_splitter.setStretchFactor(1, 1)
        
        self.tab_widget.addTab(query_widget, "Query")
    
    def set_query_status(self, message, is_error=False):
        """Show a message beside the Run button"""
        self.query_status.setStyleSheet("color: #c0392b;" if is_error else "color: #666;")
        self.query_status.setText(message)
    
    def run_or_cancel_query(self):
        """Run button doubles as Cancel while a query is running"""
        if self.query_worker:
            self.query_worker.cancel()
        else:
            self.run_query()
    
    def run_query(self):
        """Run the statement in the query editor"""
        if self.query_worker:
            return
        if not self.db_path:
            self.set_query_status("No database loaded", is_error=True)
            return
        sql = self.query_input.toPlainText().strip()
        if not sql:
            return
        
        self.query_request_id += 1
        worker = QueryWorker(self.query_request_id, self.db_path, sql, MAX_QUERY_ROWS)
        worker.query_done.connect(self.query_finished)
        worker.error_occurred.connect(self.query_failed)
        worker.finished.connect(lambda w=worker: self.query_worker_finished(w))
        self.workers.add(worker)
        self.query_worker = worker
        self.run_query_button.setText("Cancel")
        self.set_query_status("Running...")
        worker.start()
    
    def query_worker_finished(self, worker):
        """Re-arm the Run button once the query thread has stopped"""
        if self.query_worker is worker:
            self.query_worker = None
            self.run_query_button.setText("Run")
        self.worker_finished(worker)
    
    def query_finished(self, request_id, rows, column_names, truncated, seconds):
        """Show query results unless the database changed underneath them"""
        if request_id != self.query_request_id:
            return
        self.query_model.set_results(rows, column_names)
        size_columns(self.query_view, column_names)
        
        if not column_names:
            message = f"Statement returned no result set ({seconds:.3f}s)"
        elif truncated:
            message = f"Showing first {len(rows)} rows ({seconds:.3f}s) - add a LIMIT to narrow the results"
        else:
            message = f"{len(rows)} rows ({seconds:.3f}s)"
        self.set_query_status(message)
    
    def query_failed(self, request_id, error_message):
        """Show a query error inline rather than in a popup"""
        if request_id == self.query_request_id:
            self.set_query_status(error_message, is_error=True)
    
    def create_schema_tab(self):
        """Create the schema viewing tab"""
        self.schema_text = QTextEdit()
        self.schema_text.setReadOnly(True)
        self.schema_text.setFont(QFont("Courier", 10))
        self.tab_widget.addTab(self.schema_text, "Schema")
    
    def open_database(self):
        """Open file dialog to select database"""
        # Start in the folder of the most recent database
        recent = self.recent_files()
        start_dir = os.path.dirname(recent[0]) if recent else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open SQLite Database", start_dir, "SQLite Files (*.db *.sqlite *.sqlite3);;All Files (*)")
        
        if file_path:
            self.load_database(file_path)
    
    def update_status_bar(self, message, db_name=None):
        """Update status bar with database info and current message"""
        if db_name:
            status_text = f"Database: {db_name} | {message}"
        else:
            status_text = message
        self.status_bar.showMessage(status_text)
    
    def load_database(self, db_path):
        """Load database and populate tree; returns True on success"""
        try:
            validate_database(db_path)
            
            self.db_path = os.path.abspath(db_path)
            self.current_table = None
            self.current_columns = []
            self.request_id += 1  # Drop results still in flight for the old database
            self.table_model.set_results([], [])
            # Results from the previous database no longer apply
            self.query_request_id += 1
            if self.query_worker:
                self.query_worker.cancel()
            self.query_model.set_results([], [])
            self.set_query_status("")
            self.export_action.setEnabled(False)
            self.add_recent_file(self.db_path)
            db_name = os.path.basename(db_path)
            self.populate_tree()
            self.load_schema()
            self.update_status_bar(f"Loaded successfully", db_name)
            return True
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open database:\n{str(e)}")
            return False
    
    def populate_tree(self):
        """Populate tree widget with database structure"""
        if not self.db_path:
            return
        
        self.tree_widget.clear()
        
        try:
            conn = connect_readonly(self.db_path)
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = cursor.fetchall()
            
            # Create root item
            root = QTreeWidgetItem(self.tree_widget)
            root.setText(0, os.path.basename(self.db_path))
            root.setExpanded(True)
            
            # Add tables
            tables_item = QTreeWidgetItem(root)
            tables_item.setText(0, f"Tables ({len(tables)})")
            tables_item.setExpanded(True)
            
            for table_name, in tables:
                table_item = QTreeWidgetItem(tables_item)
                table_item.setText(0, table_name)
                table_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'table', 'name': table_name})
                
                # Get column info
                cursor.execute(f"PRAGMA table_info({quote_ident(table_name)})")
                columns = cursor.fetchall()
                
                for column_info in columns:
                    col_name = column_info[1]
                    col_type = column_info[2]
                    is_pk = " (PK)" if column_info[5] else ""
                    is_nullable = "" if column_info[3] else " (NOT NULL)"
                    
                    column_item = QTreeWidgetItem(table_item)
                    column_item.setText(0, f"{col_name}: {col_type}{is_pk}{is_nullable}")
                    column_item.setData(0, Qt.ItemDataRole.UserRole, {'type': 'column', 'table': table_name, 'name': col_name})
            
            conn.close()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read database structure:\n{str(e)}")
    
    def load_schema(self):
        """Load database schema into schema tab"""
        if not self.db_path:
            return
        
        try:
            conn = connect_readonly(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name")
            schema_statements = cursor.fetchall()
            
            schema_text = "-- Database Schema\n\n"
            for sql, in schema_statements:
                schema_text += sql + ";\n\n"
            
            self.schema_text.setPlainText(schema_text)
            conn.close()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load schema:\n{str(e)}")
    
    def tree_item_clicked(self, item, column):
        """Handle tree item click"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get('type') == 'table':
            self.current_table = data['name']
            self.current_offset = 0
            self.sort_column = None
            self.sort_descending = False
            self.update_column_combo()
            self.export_action.setEnabled(True)
            self.load_table_data()
            self.tab_widget.setCurrentIndex(0)  # Switch to data tab
    
    def load_table_data(self):
        """Load data for current table"""
        if not self.db_path or not self.current_table:
            return
        
        self.search_timer.stop()
        
        query, count_query, params = build_table_queries(
            self.current_table, self.current_columns,
            search_text=self.search_input.text(),
            selected_column=self.column_combo.currentText(),
            order_by=self.sort_column, descending=self.sort_descending,
            limit=self.rows_per_page, offset=self.current_offset)
        
        # Execute query in worker thread
        self.request_id += 1
        worker = DatabaseWorker(self.request_id, self.db_path, query, count_query, params)
        worker.data_ready.connect(self.handle_results)
        worker.error_occurred.connect(self.handle_error)
        worker.finished.connect(lambda w=worker: self.worker_finished(w))
        self.workers.add(worker)
        worker.start()
    
    def worker_finished(self, worker):
        """Release a finished worker thread"""
        self.workers.discard(worker)
        worker.deleteLater()
    
    def handle_results(self, request_id, data, column_names, total_rows):
        """Show query results unless a newer request has superseded them"""
        if request_id != self.request_id:
            return
        self.populate_table(data, column_names)
        self.update_pagination_info(total_rows)
    
    def handle_error(self, request_id, error_message):
        """Show a query error unless a newer request has superseded it"""
        if request_id == self.request_id:
            self.show_error(error_message)
    
    def header_clicked(self, index):
        """Sort by the clicked column, toggling direction on repeat clicks"""
        if not self.current_table or index >= len(self.table_model.columns):
            return
        column = self.table_model.columns[index]
        if column == self.sort_column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = False
        self.current_offset = 0
        self.load_table_data()
    
    def populate_table(self, data, column_names):
        """Show a page of table data"""
        self.table_model.set_results(data, column_names, self.current_offset)
        size_columns(self.table_view, column_names)
        
        # Show which column the query is sorted by
        header = self.table_view.horizontalHeader()
        if self.sort_column in column_names:
            header.setSortIndicator(column_names.index(self.sort_column),
                                    Qt.SortOrder.DescendingOrder if self.sort_descending else Qt.SortOrder.AscendingOrder)
            header.setSortIndicatorShown(True)
        else:
            header.setSortIndicatorShown(False)
        
        # Update status with database info
        db_name = os.path.basename(self.db_path) if self.db_path else "Unknown"
        message = f"Loaded {len(data)} rows from table '{self.current_table}'"
        self.update_status_bar(message, db_name)
    
    def update_column_combo(self):
        """Update column combo box with current table columns"""
        if not self.db_path or not self.current_table:
            return
        
        try:
            # Set flag to prevent recursion
            self.updating_combo = True
            
            conn = connect_readonly(self.db_path)
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({quote_ident(self.current_table)})")
            columns = cursor.fetchall()
            conn.close()
            
            self.current_columns = [column_info[1] for column_info in columns]
            
            self.column_combo.clear()
            self.column_combo.addItem("All Columns")
            self.column_combo.addItems(self.current_columns)
                
        except Exception as e:
            print(f"Error updating column combo: {e}")
        finally:
            # Always reset flag
            self.updating_combo = False
    
    def update_pagination_info(self, total_rows):
        """Update pagination controls with total count"""
        current_page = (self.current_offset // self.rows_per_page) + 1
        total_pages = max(1, (total_rows + self.rows_per_page - 1) // self.rows_per_page)
        
        self.page_label.setText(f"Page {current_page} of {total_pages}")
        self.total_rows_label.setText(f"Total: {total_rows} rows")
        
        self.prev_button.setEnabled(self.current_offset > 0)
        self.next_button.setEnabled(self.current_offset + self.rows_per_page < total_rows)
    
    def previous_page(self):
        """Go to previous page"""
        if self.current_offset > 0:
            self.current_offset = max(0, self.current_offset - self.rows_per_page)
            self.load_table_data()
    
    def next_page(self):
        """Go to next page"""
        self.current_offset += self.rows_per_page
        self.load_table_data()
    
    def change_rows_per_page(self, value):
        """Change number of rows per page"""
        self.rows_per_page = value
        self.current_offset = 0
        if self.current_table:
            self.load_table_data()
    
    def apply_filter(self):
        """Apply search filter"""
        if self.current_table and not self.updating_combo:
            self.current_offset = 0
            self.load_table_data()
    
    def clear_filter(self):
        """Clear search filter"""
        self.updating_combo = True  # Reload once below, not once per widget
        self.search_input.clear()
        self.column_combo.setCurrentIndex(0)
        self.updating_combo = False
        if self.current_table:
            self.current_offset = 0
            self.load_table_data()
    
    def show_error(self, error_message):
        """Show error message"""
        QMessageBox.critical(self, "Database Error", error_message)
    
    def closeEvent(self, event):
        """Let running queries finish so their threads aren't destroyed mid-run"""
        self.search_timer.stop()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitterState", self.splitter.saveState())
        for worker in list(self.workers):
            if hasattr(worker, "cancel"):
                worker.cancel()  # Don't let a runaway query block exit
            worker.wait()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("OJDB Viewer")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("OJDB Viewer")
    
    window = SQLiteBrowser()
    window.show()
    
    # Open a database passed on the command line (e.g. via "Open With")
    args = app.arguments()[1:]
    if args:
        window.load_database(args[0])
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 