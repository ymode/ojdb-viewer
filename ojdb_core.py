"""
OJDB Viewer core helpers
Database access and query building, kept free of Qt so it can be tested.
"""

import os
import sqlite3
from urllib.parse import quote


def quote_ident(name):
    """Quote an SQL identifier so keywords, spaces and quotes are safe"""
    return '"' + name.replace('"', '""') + '"'


def connect_readonly(db_path):
    """Open a database read-only; never creates or modifies the file"""
    uri = "file:" + quote(os.path.abspath(db_path)) + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def validate_database(db_path):
    """Raise if db_path is missing or is not an SQLite database"""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"No such file: {db_path}")
    conn = connect_readonly(db_path)
    try:
        # connect() succeeds on any file; this forces the header to be read
        conn.execute("PRAGMA schema_version").fetchone()
    finally:
        conn.close()


def escape_like(text):
    """Escape LIKE wildcards so the search term is matched literally"""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_where(columns, search_text, selected_column=None):
    """Build the WHERE clause for a search.

    columns is every column name in the table; selected_column limits the
    search to one of them. Returns (clause, params), clause being "" when
    there is nothing to filter on.
    """
    search_text = search_text.strip()
    if not search_text:
        return "", []

    if selected_column in columns:
        search_columns = [selected_column]
    else:
        search_columns = list(columns)
    if not search_columns:
        return "", []

    # CAST so numeric, untyped and VARCHAR(n) columns are searched too
    conditions = [f"CAST({quote_ident(col)} AS TEXT) LIKE ? ESCAPE '\\'"
                  for col in search_columns]
    pattern = f"%{escape_like(search_text)}%"
    return " WHERE " + " OR ".join(conditions), [pattern] * len(search_columns)


def build_table_queries(table, columns, search_text="", selected_column=None,
                        order_by=None, descending=False, limit=100, offset=0):
    """Return (data_query, count_query, params) for one page of a table"""
    where, params = build_where(columns, search_text, selected_column)
    base = f"FROM {quote_ident(table)}{where}"

    data_query = f"SELECT * {base}"
    if order_by in columns:
        direction = "DESC" if descending else "ASC"
        data_query += f" ORDER BY {quote_ident(order_by)} {direction}"
    data_query += f" LIMIT {int(limit)} OFFSET {int(offset)}"

    return data_query, f"SELECT COUNT(*) {base}", params


def format_size(num_bytes):
    """Human readable byte count"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def format_cell(value):
    """Return (display_text, is_placeholder) for a cell value"""
    if value is None:
        return "NULL", True
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<BLOB {format_size(len(value))}>", True
    return str(value), False
