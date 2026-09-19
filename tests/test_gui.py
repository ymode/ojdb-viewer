import csv
import os
import sqlite3
import time

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QMimeData, QPointF, QSettings, Qt, QUrl
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

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
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "config"))
    window = sb.SQLiteBrowser()
    window.show()
    yield window
    window.close()


SAMPLE_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test.db")


def tree_labels(item):
    return [item.child(i).text(0) for i in range(item.childCount())]


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
    pump(app, lambda: window.table_model.headerData(0, Qt.Orientation.Vertical) == "101")
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


def test_sample_database_is_current(tmp_path):
    """test.db must match what tools/make_test_db.py generates"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "make_test_db", os.path.join(os.path.dirname(SAMPLE_DB), "tools", "make_test_db.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fresh = tmp_path / "fresh.db"
    module.build(str(fresh))
    
    def dump(path):
        conn = sqlite3.connect(path)
        try:
            return list(conn.iterdump())
        finally:
            conn.close()
    
    assert dump(SAMPLE_DB) == dump(str(fresh))


def test_tree_shows_views_indexes_and_foreign_keys(app, window):
    assert window.load_database(SAMPLE_DB)
    root = window.tree_widget.topLevelItem(0)
    assert tree_labels(root) == ["Tables (4)", "Views (2)", "Indexes (7)"]
    
    tables, views, indexes = (root.child(i) for i in range(3))
    assert tree_labels(tables) == ["customers", "order", "order_items", "products"]
    assert "customer_id: INTEGER (NOT NULL) (FK → customers.id)" in tree_labels(tables.child(1))
    assert "order_id: INTEGER (NOT NULL) (FK → order.id)" in tree_labels(tables.child(2))
    assert tree_labels(views) == ["customer_summary", "order_totals"]
    assert "idx_customers_email on customers (UNIQUE)" in tree_labels(indexes)
    
    # Views browse like tables
    window.tree_item_clicked(views.child(1), 0)
    pump(app, lambda: window.table_model.rowCount() == 100)
    assert window.table_model.columns[:2] == ["order_id", "customer"]
    assert window.total_rows_label.text() == "Total: 400 rows"


def test_follow_foreign_key(app, window, errors):
    assert window.load_database(SAMPLE_DB)
    window.select_table("order_items")
    pump(app, lambda: window.table_model.rowCount() == 100)
    
    model = window.table_model
    order_id_column = model.columns.index("order_id")
    # Find a row whose order id is a prefix of other ids, so a substring match would be wrong
    row = next(r for r in range(model.rowCount()) if model.rows[r][order_id_column] == 4)
    index = model.index(row, order_id_column)
    assert window.reference_for(window.table_view, index) == ("order", "id", 4)
    assert window.reference_for(window.table_view, model.index(row, 0)) is None  # id is not an FK
    
    window.follow_reference("order", "id", 4)
    pump(app, lambda: window.total_rows_label.text() == "Total: 1 rows")
    assert window.current_table == "order"
    assert window.table_model.rows[0][0] == 4
    assert window.column_combo.currentText() == "id" and window.exact_checkbox.isChecked()
    assert window.tree_widget.currentItem().text(0) == "order"
    
    # Unticking Exact falls back to a substring match
    window.exact_checkbox.setChecked(False)
    pump(app, lambda: window.total_rows_label.text() != "Total: 1 rows")
    assert int(window.total_rows_label.text().split()[1]) > 1
    
    window.clear_filter()
    pump(app, lambda: window.total_rows_label.text() == "Total: 400 rows")
    assert not errors


def test_cell_details(app, window):
    assert window.load_database(SAMPLE_DB)
    window.select_table("products")
    pump(app, lambda: window.table_model.rowCount() == 25)
    model = window.table_model
    assert not window.detail_dock.isVisible()
    
    image_column = model.columns.index("image")
    window.open_details(window.table_view, model.index(0, image_column))
    assert window.detail_dock.isVisible()
    assert window.detail_summary.text().startswith("image: BLOB, ")
    assert "16x16 image" in window.detail_summary.text()
    assert window.detail_image.isVisible()
    assert window.detail_text.toPlainText().startswith("00000000  89 50 4e 47")
    
    # Selecting another cell updates the pane; row 7 has no image
    window.table_view.setCurrentIndex(model.index(6, image_column))
    assert window.detail_summary.text() == "image: NULL"
    assert not window.detail_image.isVisible()
    
    window.select_table("customers")
    pump(app, lambda: window.table_model.columns[:1] == ["id"] and window.table_model.rowCount() == 60)
    assert window.detail_summary.text() == "Select a cell to see its full contents"
    prefs = window.table_model.columns.index("preferences")
    row = next(r for r in range(60) if window.table_model.rows[r][prefs])
    window.table_view.setCurrentIndex(window.table_model.index(row, prefs))
    assert "JSON text" in window.detail_summary.text()
    assert window.detail_text.toPlainText().startswith("{\n  ")


def test_drop_file_opens_database(app, window, db_path):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(db_path)])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(event)
    assert window.db_path == db_path
    assert window.tree_widget.topLevelItem(0).text(0) == "gui test.db"
