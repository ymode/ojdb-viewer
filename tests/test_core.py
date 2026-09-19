import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ojdb_core import (build_table_queries, build_where, connect_readonly,
                       format_cell, quote_ident, validate_database)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE "order" (id INTEGER PRIMARY KEY, "my col" VARCHAR(255), '
                 'qty INTEGER, untyped, data BLOB)')
    conn.executemany('INSERT INTO "order" ("my col", qty, untyped, data) VALUES (?, ?, ?, ?)', [
        ("alpha", 10, "x", b"\x00\x01"),
        ("beta", 9, "y", None),
        ("100% real", 123, "alpha", None),
    ])
    conn.commit()
    conn.close()
    return str(path)


COLUMNS = ["id", "my col", "qty", "untyped", "data"]


def run(db_path, query, params):
    conn = connect_readonly(db_path)
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def test_quote_ident():
    assert quote_ident("order") == '"order"'
    assert quote_ident('we"ird') == '"we""ird"'


def test_keyword_table_and_spaced_column(db_path):
    query, count_query, params = build_table_queries("order", COLUMNS, "beta", "my col")
    assert [row[1] for row in run(db_path, query, params)] == ["beta"]
    assert run(db_path, count_query, params) == [(1,)]


def test_all_columns_searches_every_type(db_path):
    # "alpha" is in a VARCHAR(255) column and an untyped column
    query, _, params = build_table_queries("order", COLUMNS, "alpha", "All Columns")
    assert len(run(db_path, query, params)) == 2
    # numeric columns are searched too
    query, _, params = build_table_queries("order", COLUMNS, "123")
    assert len(run(db_path, query, params)) == 1


def test_like_wildcards_are_literal(db_path):
    query, _, params = build_table_queries("order", COLUMNS, "%", "my col")
    assert [row[1] for row in run(db_path, query, params)] == ["100% real"]


def test_empty_search_has_no_where():
    assert build_where(COLUMNS, "   ") == ("", [])


def test_order_by_is_numeric_and_validated(db_path):
    query, _, params = build_table_queries("order", COLUMNS, order_by="qty", descending=True)
    assert [row[2] for row in run(db_path, query, params)] == [123, 10, 9]
    query, _, _ = build_table_queries("order", COLUMNS, order_by="qty; DROP TABLE x")
    assert "ORDER BY" not in query


def test_pagination(db_path):
    query, count_query, params = build_table_queries("order", COLUMNS, limit=2, offset=2)
    assert len(run(db_path, query, params)) == 1
    assert run(db_path, count_query, params) == [(3,)]


def test_validate_rejects_missing_file_without_creating_it(tmp_path):
    missing = tmp_path / "nope.db"
    with pytest.raises(FileNotFoundError):
        validate_database(str(missing))
    assert not missing.exists()


def test_validate_rejects_non_sqlite_file(tmp_path):
    bogus = tmp_path / "bogus.db"
    bogus.write_text("this is not a database, it just has the extension" * 10)
    with pytest.raises(sqlite3.DatabaseError):
        validate_database(str(bogus))


def test_connection_is_readonly(db_path):
    conn = connect_readonly(db_path)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute('DELETE FROM "order"')
    conn.close()


def test_path_with_special_characters(tmp_path):
    path = tmp_path / "odd name #1?.db"
    sqlite3.connect(path).close()
    validate_database(str(path))


def test_format_cell():
    assert format_cell(None) == ("NULL", True)
    assert format_cell("") == ("", False)
    assert format_cell(42) == ("42", False)
    assert format_cell(b"\x00" * 2048) == ("<BLOB 2.0 KB>", True)
    assert format_cell(b"ab") == ("<BLOB 2 B>", True)
