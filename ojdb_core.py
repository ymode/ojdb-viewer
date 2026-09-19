"""
OJDB Viewer core helpers
Database access and query building, kept free of Qt so it can be tested.
"""

import csv
import json
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


def build_where(columns, search_text, selected_column=None, exact=False):
    """Build the WHERE clause for a search.

    columns is every column name in the table; selected_column limits the
    search to one of them. exact matches the whole value instead of a
    substring. Returns (clause, params), clause being "" when there is
    nothing to filter on.
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
    if exact:
        conditions = [f"CAST({quote_ident(col)} AS TEXT) = ?" for col in search_columns]
        pattern = search_text
    else:
        conditions = [f"CAST({quote_ident(col)} AS TEXT) LIKE ? ESCAPE '\\'"
                      for col in search_columns]
        pattern = f"%{escape_like(search_text)}%"
    return " WHERE " + " OR ".join(conditions), [pattern] * len(search_columns)


def build_table_queries(table, columns, search_text="", selected_column=None,
                        order_by=None, descending=False, limit=100, offset=0,
                        exact=False):
    """Return (data_query, count_query, params) for one page of a table.

    limit=None returns every matching row.
    """
    where, params = build_where(columns, search_text, selected_column, exact)
    base = f"FROM {quote_ident(table)}{where}"

    data_query = f"SELECT * {base}"
    if order_by in columns:
        direction = "DESC" if descending else "ASC"
        data_query += f" ORDER BY {quote_ident(order_by)} {direction}"
    if limit is not None:
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


def csv_value(value):
    """CSV representation of a cell: NULL is empty, BLOBs are hex"""
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "0x" + bytes(value).hex()
    return value


def export_csv(db_path, out_path, table, columns, search_text="",
               selected_column=None, order_by=None, descending=False, exact=False):
    """Write every row matching the current view to out_path; returns row count"""
    query, _, params = build_table_queries(
        table, columns, search_text, selected_column, order_by, descending, limit=None,
        exact=exact)

    conn = connect_readonly(db_path)
    try:
        cursor = conn.execute(query, params)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([description[0] for description in cursor.description])
            row_count = 0
            # Stream in chunks so large tables aren't held in memory
            while True:
                rows = cursor.fetchmany(1000)
                if not rows:
                    break
                writer.writerows([csv_value(v) for v in row] for row in rows)
                row_count += len(rows)
        return row_count
    finally:
        conn.close()


def read_structure(db_path):
    """Describe the tables, views and indexes in a database.

    Returns {"tables": [...], "views": [...], "indexes": [...]}. Tables and
    views carry their columns; table columns that are foreign keys carry
    "fk": (referenced_table, referenced_column).
    """
    conn = connect_readonly(db_path)
    try:
        def names(object_type):
            rows = conn.execute(
                "SELECT name, tbl_name FROM sqlite_master WHERE type = ? ORDER BY name",
                (object_type,)).fetchall()
            return rows

        def columns_of(name):
            info = conn.execute(f"PRAGMA table_info({quote_ident(name)})").fetchall()
            return [{"name": col[1], "type": col[2], "not_null": bool(col[3]),
                     "pk": bool(col[5]), "fk": None} for col in info]

        def primary_key(name):
            pk_columns = [col["name"] for col in columns_of(name) if col["pk"]]
            return pk_columns[0] if len(pk_columns) == 1 else None

        tables = []
        for name, _ in names("table"):
            columns = columns_of(name)
            by_name = {col["name"]: col for col in columns}
            for fk in conn.execute(f"PRAGMA foreign_key_list({quote_ident(name)})").fetchall():
                ref_table, from_column, to_column = fk[2], fk[3], fk[4]
                # "REFERENCES other" without a column means other's primary key
                to_column = to_column or primary_key(ref_table)
                if from_column in by_name and to_column:
                    by_name[from_column]["fk"] = (ref_table, to_column)
            tables.append({"name": name, "columns": columns})

        views = []
        for name, _ in names("view"):
            try:
                columns = columns_of(name)
            except sqlite3.Error:
                columns = []  # A view over a dropped table can't be described
            views.append({"name": name, "columns": columns})

        indexes = []
        for name, table in names("index"):
            info = conn.execute(f"PRAGMA index_info({quote_ident(name)})").fetchall()
            unique = any(row[1] == name and row[2]
                         for row in conn.execute(f"PRAGMA index_list({quote_ident(table)})"))
            # Expression columns have no name
            indexes.append({"name": name, "table": table, "unique": bool(unique),
                            "columns": [row[2] or "<expression>" for row in info]})

        return {"tables": tables, "views": views, "indexes": indexes}
    finally:
        conn.close()


HEX_DUMP_LIMIT = 4096


def hex_dump(data, limit=HEX_DUMP_LIMIT):
    """Classic offset / hex / ASCII dump of the first limit bytes"""
    data = bytes(data)
    lines = []
    for offset in range(0, min(len(data), limit), 16):
        chunk = data[offset:offset + 16]
        hex_part = " ".join(f"{byte:02x}" for byte in chunk)
        ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:08x}  {hex_part:<47}  {ascii_part}")
    if len(data) > limit:
        lines.append(f"... {format_size(len(data) - limit)} more not shown")
    return "\n".join(lines)


def describe_value(value):
    """Return (summary, detail_text) for the cell detail pane"""
    if value is None:
        return "NULL", ""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"BLOB, {format_size(len(value))}", hex_dump(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in ("{", "["):
            try:
                pretty = json.dumps(json.loads(stripped), indent=2, ensure_ascii=False)
                return f"JSON text, {len(value)} characters", pretty
            except ValueError:
                pass
        return f"Text, {len(value)} characters", value
    type_name = "Integer" if isinstance(value, int) else "Real"
    return type_name, str(value)
