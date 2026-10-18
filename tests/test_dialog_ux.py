"""Sorting, multi-row copy, CSV export, re-checking Java, and closing on a
conversation that is still running."""

import csv

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from opsin_name_to_structure import engine
from opsin_name_to_structure.main_dialog import (
    _ORDER_COLUMN,
    OpsinDialog,
)

from .fakes import FakeContext

BENZENE = engine.Conversion(
    name="benzene",
    smiles="c1ccccc1",
    formula="C6H6",
    inchi="InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H",
    inchikey="UHOVQNZJYSORNB-UHFFFAOYSA-N",
)
ETHANOL = engine.Conversion(
    name="ethanol",
    smiles="CCO",
    formula="C2H6O",
    inchi="InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3",
    inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
)
BAD = engine.Conversion(name="nonsense", error="is unparsable due to nonsense")


@pytest.fixture
def dialog(qapp, monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    win = OpsinDialog(FakeContext())
    yield win
    win.close()
    win.deleteLater()


def convert_returns(monkeypatch, results):
    monkeypatch.setattr(engine, "convert", lambda names, options=None, **kw: results)


def run_sync(dialog):
    dialog.run_conversion()
    if dialog.worker is not None:
        dialog.worker.wait(30000)
    QApplication.processEvents()


def filled(dialog, monkeypatch, results):
    convert_returns(monkeypatch, results)
    dialog.input.setPlainText("\n".join(r.name for r in results))
    run_sync(dialog)


# --- ordering ---


def test_a_fresh_batch_reads_in_the_order_it_was_typed(dialog, monkeypatch):
    # Enabling sorting used to reorder the table the moment it was filled.
    filled(dialog, monkeypatch, [ETHANOL, BENZENE, BAD])
    assert [dialog.result_at_row(r).name for r in range(3)] == [
        "ethanol",
        "benzene",
        "nonsense",
    ]


def test_sorting_by_name_reorders_the_rows(dialog, monkeypatch):
    filled(dialog, monkeypatch, [ETHANOL, BENZENE])
    dialog.table.sortItems(1, Qt.SortOrder.AscendingOrder)
    assert dialog.result_at_row(0).name == "benzene"


def test_sorting_does_not_desync_the_selection(dialog, monkeypatch):
    """The row number stops meaning anything once the table is sorted."""
    filled(dialog, monkeypatch, [ETHANOL, BENZENE])
    dialog.table.sortItems(1, Qt.SortOrder.AscendingOrder)
    dialog.table.selectRow(0)

    result = dialog.selected_result()

    assert result is not None and result.name == "benzene"
    assert result.smiles == "c1ccccc1"  # not ethanol's, read off a stale index


def test_input_position_sorts_as_a_number_not_as_text(dialog, monkeypatch):
    many = [ETHANOL._replace(name=f"name{i}") for i in range(12)]
    filled(dialog, monkeypatch, many)
    dialog.table.sortItems(_ORDER_COLUMN, Qt.SortOrder.AscendingOrder)
    # Lexical order would put "10" before "2".
    assert dialog.result_at_row(1).name == "name1"
    assert dialog.result_at_row(9).name == "name9"


def test_a_row_with_no_items_yields_nothing(dialog):
    assert dialog.result_at_row(0) is None
    assert dialog.selected_result() is None


# --- copying ---


def test_copying_takes_every_selected_row(dialog, monkeypatch):
    filled(dialog, monkeypatch, [BENZENE, ETHANOL])
    dialog.table.selectAll()

    dialog.copy_field("smiles")

    assert QApplication.clipboard().text() == "c1ccccc1\nCCO"
    assert "2 smiles" in dialog.status.text()


def test_copying_one_row_still_names_it(dialog, monkeypatch):
    filled(dialog, monkeypatch, [BENZENE])
    dialog.table.selectRow(0)
    dialog.copy_field("inchikey")
    assert QApplication.clipboard().text() == BENZENE.inchikey
    assert "'benzene'" in dialog.status.text()


def test_copying_a_field_a_failed_row_has_not_got_says_so(dialog, monkeypatch):
    filled(dialog, monkeypatch, [BAD])
    dialog.table.selectRow(0)
    dialog.copy_field("smiles")
    assert "No smiles" in dialog.status.text()


def test_copying_with_nothing_selected_asks_for_a_row(dialog):
    dialog.copy_field("smiles")
    assert "Select a row" in dialog.status.text()


# --- export ---


def test_export_writes_every_row_including_failures(dialog, monkeypatch, tmp_path):
    filled(dialog, monkeypatch, [BENZENE, BAD])
    target = tmp_path / "out.csv"
    monkeypatch.setattr(
        "opsin_name_to_structure.main_dialog.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target), ""),
    )

    dialog.export_csv()

    with open(target, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["Name", "Formula", "SMILES", "InChIKey", "InChI", "Status"]
    assert rows[1][0] == "benzene" and rows[1][5] == "OK"
    assert rows[2][0] == "nonsense" and "unparsable" in rows[2][5]
    assert "Exported 2 row(s)" in dialog.status.text()


def test_export_with_no_results_says_so(dialog):
    dialog.export_csv()
    assert "Nothing to export" in dialog.status.text()


def test_a_cancelled_save_dialog_writes_nothing(dialog, monkeypatch, tmp_path):
    filled(dialog, monkeypatch, [BENZENE])
    monkeypatch.setattr(
        "opsin_name_to_structure.main_dialog.QFileDialog.getSaveFileName",
        lambda *a, **k: ("", ""),
    )
    dialog.export_csv()
    assert list(tmp_path.iterdir()) == []


def test_an_unwritable_path_is_reported_not_raised(dialog, monkeypatch, tmp_path):
    filled(dialog, monkeypatch, [BENZENE])
    monkeypatch.setattr(
        "opsin_name_to_structure.main_dialog.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(tmp_path), ""),  # a directory, not a file
    )
    warned = []
    monkeypatch.setattr(
        "opsin_name_to_structure.main_dialog.QMessageBox.warning",
        lambda *a, **k: warned.append(a),
    )
    dialog.export_csv()
    assert warned


# --- clearing ---


def test_clear_empties_both_the_box_and_the_table(dialog, monkeypatch):
    filled(dialog, monkeypatch, [BENZENE])
    dialog.clear_all()
    assert dialog.input.toPlainText() == ""
    assert dialog.table.rowCount() == 0
    assert dialog.results == []


# --- availability ---


def test_installing_java_later_re_enables_convert(qapp, monkeypatch):
    """The window is a singleton, so it has to look again, not just once."""
    state = {"usable": False}
    monkeypatch.setattr(
        engine,
        "availability",
        lambda: (True, "") if state["usable"] else (False, engine.JAVA_MISSING),
    )
    win = OpsinDialog(FakeContext())
    try:
        assert not win.convert_button.isEnabled()

        state["usable"] = True
        win.show()
        QApplication.processEvents()

        assert win.convert_button.isEnabled()
        assert win.notice.isHidden()
    finally:
        win.close()


def test_convert_does_nothing_while_opsin_is_unavailable(qapp, monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (False, engine.JAVA_MISSING))
    win = OpsinDialog(FakeContext())
    try:
        win.input.setPlainText("benzene")
        win.run_conversion()
        assert win.worker is None
    finally:
        win.close()


# --- busy state ---


def test_the_window_shows_it_is_working(dialog, monkeypatch):
    dialog._set_busy(True)
    assert not dialog.convert_button.isEnabled()
    assert dialog.input.isReadOnly()

    dialog._set_busy(False)
    assert dialog.convert_button.isEnabled()
    assert not dialog.input.isReadOnly()
    assert dialog.progress.isHidden()


# --- teardown ---


def test_teardown_runs_once(qapp, monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    context = FakeContext()
    win = OpsinDialog(context)

    win.reject()
    win.close()  # a second teardown must not re-enter anything

    assert context.windows["main_panel"] is None
    assert win.worker is None


def test_a_conversion_that_outlives_the_window_is_not_delivered_to_it(
    qapp, monkeypatch
):
    """Closing mid-batch must not push results into a dying dialog."""
    import time

    monkeypatch.setattr(engine, "availability", lambda: (True, ""))

    def slow(names, options=None, **kw):
        time.sleep(0.4)
        return [BENZENE]

    monkeypatch.setattr(engine, "convert", slow)
    win = OpsinDialog(FakeContext())
    win.input.setPlainText("benzene")
    win.run_conversion()
    worker = win.worker
    assert worker is not None

    win.close()  # while the worker is still running

    assert win.worker is None
    worker.wait(30000)
    QApplication.processEvents()
    assert win.results == []  # the late result never landed
