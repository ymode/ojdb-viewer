#!/usr/bin/env python3
"""
SQLite Database Browser
A Python Qt5 application for browsing SQLite database files.
"""

import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                             QTreeWidget, QTreeWidgetItem, QSplitter, QFileDialog,
                             QMessageBox, QLineEdit, QLabel, QHeaderView, QTabWidget,
                             QTextEdit, QComboBox, QSpinBox, QStatusBar)
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon

from ojdb_core import (build_table_queries, connect_readonly, format_cell,
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
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)  # Prevent collapsing
        main_layout.addWidget(splitter)
        
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
        
        # Recent files submenu (placeholder for future enhancement)
        recent_menu = file_menu.addMenu('Recent Files')
        recent_menu.addAction('No recent files').setEnabled(False)
        
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
        
        # Export data action (placeholder for future enhancement)
        export_action = tools_menu.addAction('&Export Data...')
        export_action.setStatusTip('Export table data to CSV')
        export_action.setEnabled(False)  # Disabled for now
        
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
        about_action.setStatusTip('About SQLite Browser')
        about_action.triggered.connect(self.show_about)
    
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
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.about(self, "About OJDB Viewer (Our Jank Database Viewer)", 
                         "OJDB Viewer v1.0\n\n"
                         "A Python Qt5 application for browsing SQLite databases.\n\n"
                         "Features:\n"
                         "• Browse database structure\n"
                         "• View table data with pagination\n"
                         "• Search and filter data\n"
                         "• View database schema\n\n"
                         "Built with Python and PyQt5")
    
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
        
        # Table widget
        self.table_widget = QTableWidget()
        # Sorting is done in SQL so it covers the whole table, not just this page
        self.table_widget.setSortingEnabled(False)
        self.table_widget.horizontalHeader().setSectionsClickable(True)
        self.table_widget.horizontalHeader().sectionClicked.connect(self.header_clicked)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.verticalHeader().setDefaultSectionSize(25)  # Row height
        layout.addWidget(self.table_widget)
        
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
        self.page_label.setAlignment(Qt.AlignCenter)
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
    
    def create_schema_tab(self):
        """Create the schema viewing tab"""
        self.schema_text = QTextEdit()
        self.schema_text.setReadOnly(True)
        self.schema_text.setFont(QFont("Courier", 10))
        self.tab_widget.addTab(self.schema_text, "Schema")
    
    def open_database(self):
        """Open file dialog to select database"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open SQLite Database", "", "SQLite Files (*.db *.sqlite *.sqlite3);;All Files (*)")
        
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
        """Load database and populate tree"""
        try:
            validate_database(db_path)
            
            self.db_path = os.path.abspath(db_path)
            self.current_table = None
            self.current_columns = []
            self.request_id += 1  # Drop results still in flight for the old database
            self.table_widget.setRowCount(0)
            self.table_widget.setColumnCount(0)
            db_name = os.path.basename(db_path)
            self.populate_tree()
            self.load_schema()
            self.update_status_bar(f"Loaded successfully", db_name)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open database:\n{str(e)}")
    
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
                table_item.setData(0, Qt.UserRole, {'type': 'table', 'name': table_name})
                
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
                    column_item.setData(0, Qt.UserRole, {'type': 'column', 'table': table_name, 'name': col_name})
            
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
        data = item.data(0, Qt.UserRole)
        if data and data.get('type') == 'table':
            self.current_table = data['name']
            self.current_offset = 0
            self.sort_column = None
            self.sort_descending = False
            self.update_column_combo()
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
        if not self.current_table or index >= self.table_widget.columnCount():
            return
        column = self.table_widget.horizontalHeaderItem(index).text()
        if column == self.sort_column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = False
        self.current_offset = 0
        self.load_table_data()
    
    def populate_table(self, data, column_names):
        """Populate table widget with data"""
        self.table_widget.setRowCount(len(data))
        self.table_widget.setColumnCount(len(column_names))
        self.table_widget.setHorizontalHeaderLabels(column_names)
        
        for row_idx, row_data in enumerate(data):
            for col_idx, value in enumerate(row_data):
                text, is_placeholder = format_cell(value)
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # Make read-only
                if is_placeholder:
                    # Distinguish NULL/BLOB markers from real text
                    font = item.font()
                    font.setItalic(True)
                    item.setFont(font)
                    item.setForeground(QColor("#888"))
                self.table_widget.setItem(row_idx, col_idx, item)
        
        # Improve column sizing
        header = self.table_widget.horizontalHeader()
        
        # Auto-resize columns to content, but with constraints
        self.table_widget.resizeColumnsToContents()
        
        # Set reasonable column width limits
        for col in range(len(column_names)):
            current_width = self.table_widget.columnWidth(col)
            # Set minimum and maximum widths
            min_width = max(80, len(column_names[col]) * 8)  # Based on header text
            max_width = 300  # Maximum column width
            
            if current_width < min_width:
                self.table_widget.setColumnWidth(col, min_width)
            elif current_width > max_width:
                self.table_widget.setColumnWidth(col, max_width)
        
        # Set resize modes
        header.setSectionResizeMode(QHeaderView.Interactive)
        
        # Show which column the query is sorted by
        if self.sort_column in column_names:
            header.setSortIndicator(column_names.index(self.sort_column),
                                    Qt.DescendingOrder if self.sort_descending else Qt.AscendingOrder)
            header.setSortIndicatorShown(True)
        else:
            header.setSortIndicatorShown(False)
        
        # If we have extra space, distribute it among columns
        total_width = sum(self.table_widget.columnWidth(col) for col in range(len(column_names)))
        available_width = self.table_widget.viewport().width()
        
        if total_width < available_width and len(column_names) > 0:
            # Stretch the last column to fill remaining space
            header.setSectionResizeMode(len(column_names) - 1, QHeaderView.Stretch)
        
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
        for worker in list(self.workers):
            worker.wait()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("SQLite Browser")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("SQLite Browser")
    
    window = SQLiteBrowser()
    window.show()
    
    # Open a database passed on the command line (e.g. via "Open With")
    args = app.arguments()[1:]
    if args:
        window.load_database(args[0])
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 