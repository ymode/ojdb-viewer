import csv
import os
import sqlite3
import time

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

import sqlite_browser as sb


@pytest.fixture(scope="session")
def app():
    app = QApplication.instance() or QApplication(["test"])
    app.setApplicationName("OJDB Viewer")
    app.setOrganizationName("OJDB Viewer")
    return app


@pytest.fixture
def errors(monkeypatch):
    """Collect error popups instead of blocking on them"""
    shown = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda parent, title, text, *a: shown.append(text)))
    return shown


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "gui test.db"
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE "order" (id INTEGER PRIMARY KEY, "my col" VARCHAR(50), '
                 'qty INTEGER, data BLOB)')
    conn.executemany('INSERT INTO "order" ("my col", qty, data) VALUES (?, ?, ?)',
                     [(f"name{i}", i, None if i % 2 else b"\x01\x02") for i in range(1, 251)])
    conn.commit()
    conn.close()
    return str(path)


@pytest.fixture
def window(app, errors, tmp_path):
    # Keep settings out of the real user config
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(tmp_path / "config"))
    window = sb.SQLiteBrowser()
    window.show()
    yield window
    window.close()


def pump(app, condition, timeout=10):
    """Process events until condition() is true"""
    deadline = time.time() + timeout
    while time.time() < deadline and not condition():
        app.processEvents()
        time.sleep(0.01)
    assert condition(), "timed out"


def cell(model, row, col):
    return model.data(model.index(row, col))


def open_table(app, window, db_path):
    assert window.load_database(db_path)
    table_item = window.tree_widget.topLevelItem(0).child(0).child(0)
    assert table_item.text(0) == "order"
    window.tree_item_clicked(table_item, 0)
    pump(app, lambda: window.table_model.rowCount() == 100)


def run_query(app, window, sql):
    window.query_input.setPlainText(sql)
    window.run_query()
    pump(app, lambda: window.query_worker is None)
    return window.query_status.text()


def test_browse_table(app, window, db_path, errors):
    open_table(app, window, db_path)
    assert window.page_label.text() == "Page 1 of 3"
    assert cell(window.table_model, 0, 3) == "NULL"
    assert cell(window.table_model, 1, 3) == "<BLOB 2 B>"
    
    window.next_page()
    pump(app, lambda: window.table_model.headerData(0, Qt.Vertical) == "101")
    assert not errors


def test_column_filter_survives_reload(app, window, db_path):
    open_table(app, window, db_path)
    window.column_combo.setCurrentText("qty")
    window.search_input.setText("25")
    pump(app, lambda: window.total_rows_label.text() == "Total: 4 rows")  # 25, 125, 225, 250
    assert window.column_combo.currentText() == "qty"


def test_rapid_typing_shows_only_latest_result(app, window, db_path, errors):
    open_table(app, window, db_path)
    window.column_combo.setCurrentText("my col")
    for text in ["n", "na", "nam", "name2", "name25"]:
        window.search_input.setText(text)
        app.processEvents()
    pump(app, lambda: window.total_rows_label.text() == "Total: 2 rows")  # name25, name250
    assert not errors


def test_header_click_sorts_whole_table_numerically(app, window, db_path):
    open_table(app, window, db_path)
    window.header_clicked(2)
    window.header_clicked(2)
    pump(app, lambda: cell(window.table_model, 0, 2) == "250")
    assert cell(window.table_model, 1, 2) == "249"


def test_bad_files_are_rejected(app, window, tmp_path, errors):
    missing = tmp_path / "missing.db"
    assert not window.load_database(str(missing))
    assert not missing.exists()
    
    bogus = tmp_path / "bogus.db"
    bogus.write_text("not a database " * 50)
    assert not window.load_database(str(bogus))
    assert len(errors) == 2


def test_export_applies_filter_and_sort_to_all_pages(app, window, db_path, tmp_path, monkeypatch):
    open_table(app, window, db_path)
    window.column_combo.setCurrentText("my col")
    window.search_input.setText("name1")
    window.header_clicked(2)
    window.header_clicked(2)
    pump(app, lambda: window.total_rows_label.text() == "Total: 111 rows")
    
    out = tmp_path / "out.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    window.export_data()
    pump(app, lambda: "Exported 111 rows" in window.status_bar.currentMessage())
    
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["id", "my col", "qty", "data"]
    assert len(rows) == 112
    assert rows[1][2] == "199" and rows[1][3] == ""
    assert rows[2][3] == "0x0102"


def test_recent_files(app, window, db_path, tmp_path, errors):
    other = tmp_path / "other.db"
    sqlite3.connect(other).close()
    
    assert window.load_database(db_path)
    assert window.load_database(str(other))
    assert window.load_database(db_path)
    assert window.recent_files() == [db_path, str(other)]
    
    # An entry that can no longer be opened is dropped
    other.unlink()
    window.open_recent_file(str(other))
    assert window.recent_files() == [db_path]
    assert len(errors) == 1
    
    # A single entry survives a round trip through QSettings
    assert sb.SQLiteBrowser().recent_files() == [db_path]


def test_query_tab(app, window, db_path):
    assert run_query(app, window, "SELECT 1") == "No database loaded"
    window.load_database(db_path)
    before = os.stat(db_path).st_mtime_ns
    
    status = run_query(app, window, 'SELECT id, "my col", data FROM "order" WHERE id <= 2')
    assert status.startswith("2 rows")
    assert window.query_model.columns == ["id", "my col", "data"]
    
    window.query_view.selectAll()
    sb.copy_selection(window.query_view)
    assert app.clipboard().text() == "1\tname1\t\n2\tname2\t0x0102"
    
    assert "syntax error" in run_query(app, window, "SELEC nonsense")
    assert window.query_model.rowCount() == 2  # Previous results kept on error
    
    assert "readonly" in run_query(app, window, 'DELETE FROM "order"')
    assert os.stat(db_path).st_mtime_ns == before


def test_runaway_query_can_be_cancelled(app, window, db_path):
    window.load_database(db_path)
    window.query_input.setPlainText(
        "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r) SELECT count(*) FROM r")
    window.run_query()
    assert window.run_query_button.text() == "Cancel"
    pump(app, lambda: window.query_worker is not None and window.query_worker.conn is not None)
    time.sleep(0.2)
    
    window.run_or_cancel_query()
    pump(app, lambda: window.query_worker is None)
    assert "interrupt" in window.query_status.text().lower()
    assert window.run_query_button.text() == "Run"
