import csv
import os
import sqlite3

import pytest

from ojdb_core import (build_table_queries, build_where, connect_readonly, describe_value,
                       export_csv, format_cell, hex_dump, quote_ident, read_structure,
                       validate_database)


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


def test_export_csv_all_rows(db_path, tmp_path):
    out = tmp_path / "out.csv"
    count = export_csv(db_path, str(out), "order", COLUMNS, order_by="qty")
    assert count == 3
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == COLUMNS
    assert [r[2] for r in rows[1:]] == ["9", "10", "123"]
    # NULL is empty, BLOB is hex
    assert rows[1][4] == "" and rows[2][4] == "0x0001"


def test_export_csv_respects_filter(db_path, tmp_path):
    out = tmp_path / "out.csv"
    assert export_csv(db_path, str(out), "order", COLUMNS, "alpha", "my col") == 1


def test_exact_match(db_path):
    # Substring search for 1 also finds 10 and 123; exact does not
    query, _, params = build_table_queries("order", COLUMNS, "1", "qty")
    assert len(run(db_path, query, params)) == 2
    query, _, params = build_table_queries("order", COLUMNS, "10", "qty", exact=True)
    assert [row[2] for row in run(db_path, query, params)] == [10]
    # Wildcards are literal in exact mode too
    query, _, params = build_table_queries("order", COLUMNS, "%", "my col", exact=True)
    assert run(db_path, query, params) == []


@pytest.fixture
def relational_db(tmp_path):
    path = tmp_path / "rel.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE parent (id INTEGER PRIMARY KEY, code TEXT UNIQUE);
        CREATE TABLE "child table" (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER NOT NULL REFERENCES parent(id),
            implicit_id INTEGER REFERENCES parent,
            label TEXT
        );
        CREATE INDEX idx_child_parent ON "child table"(parent_id, label);
        CREATE INDEX idx_child_expr ON "child table"(lower(label));
        CREATE VIEW child_view AS SELECT id, label FROM "child table";
        CREATE VIEW broken_view AS SELECT * FROM parent;
    """)
    conn.execute("ALTER TABLE parent RENAME TO parent2")  # keeps the view valid in new SQLite
    conn.commit()
    conn.close()
    return str(path)


def test_read_structure(relational_db):
    structure = read_structure(relational_db)
    tables = {table["name"]: table for table in structure["tables"]}
    assert set(tables) == {"parent2", "child table"}

    child = {column["name"]: column for column in tables["child table"]["columns"]}
    assert child["id"]["pk"] and not child["label"]["not_null"]
    assert child["parent_id"]["not_null"]
    assert child["parent_id"]["fk"] == ("parent2", "id")
    # REFERENCES without a column resolves to the primary key
    assert child["implicit_id"]["fk"] == ("parent2", "id")
    assert child["label"]["fk"] is None

    views = {view["name"]: view for view in structure["views"]}
    assert [column["name"] for column in views["child_view"]["columns"]] == ["id", "label"]

    indexes = {index["name"]: index for index in structure["indexes"]}
    assert indexes["idx_child_parent"]["columns"] == ["parent_id", "label"]
    assert indexes["idx_child_parent"]["table"] == "child table"
    assert not indexes["idx_child_parent"]["unique"]
    assert indexes["idx_child_expr"]["columns"] == ["<expression>"]
    assert any(index["unique"] and index["table"] == "parent2" for index in indexes.values())


def test_describe_value():
    assert describe_value(None) == ("NULL", "")
    assert describe_value(7) == ("Integer", "7")
    assert describe_value(1.5) == ("Real", "1.5")
    assert describe_value("plain") == ("Text, 5 characters", "plain")

    summary, text = describe_value('{"b": [1, 2], "a": "é"}')
    assert summary.startswith("JSON text")
    assert text == '{\n  "b": [\n    1,\n    2\n  ],\n  "a": "é"\n}'
    # Looks like JSON but isn't: shown as ordinary text
    assert describe_value("{not json")[0] == "Text, 9 characters"

    summary, text = describe_value(b"\x89PNG\r\n")
    assert summary == "BLOB, 6 B"
    assert text == "00000000  89 50 4e 47 0d 0a" + " " * 32 + ".PNG.."


def test_hex_dump_truncates():
    dump = hex_dump(b"\x00" * 5000, limit=32)
    assert dump.splitlines()[-1] == "... 4.9 KB more not shown"
    assert len(dump.splitlines()) == 3
