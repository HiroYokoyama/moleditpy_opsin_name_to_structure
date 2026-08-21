"""The window, with OPSIN stubbed so no JVM starts."""

import pytest

from opsin_name_to_structure import engine
from opsin_name_to_structure.main_dialog import WINDOW_ID, OpsinDialog

from .fakes import FakeContext

BENZENE = engine.Conversion(
    name="benzene",
    smiles="c1ccccc1",
    formula="C6H6",
    inchi="InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H",
    inchikey="UHOVQNZJYSORNB-UHFFFAOYSA-N",
)
BAD = engine.Conversion(name="nonsense", error="OPSIN could not interpret this name.")


@pytest.fixture
def dialog(qapp, monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    context = FakeContext()
    win = OpsinDialog(context)
    yield win
    win.deleteLater()


def convert_returns(monkeypatch, results):
    monkeypatch.setattr(engine, "convert", lambda names, options=None, **kw: results)


def run_sync(dialog):
    """Run the worker and wait, so the test does not race the thread."""
    dialog.run_conversion()
    if dialog.worker is not None:
        dialog.worker.wait(30000)
    from PyQt6.QtWidgets import QApplication

    QApplication.processEvents()


def test_convert_is_enabled_when_opsin_is_available(dialog):
    assert dialog.convert_button.isEnabled()
    assert dialog.notice.isHidden()


def test_missing_java_disables_convert_and_explains(qapp, monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (False, engine.JAVA_MISSING))
    win = OpsinDialog(FakeContext())
    try:
        assert not win.convert_button.isEnabled()
        assert not win.notice.isHidden()
        assert "Java" in win.notice.text()
    finally:
        win.deleteLater()


def test_empty_input_is_reported_without_running(dialog):
    dialog.input.setPlainText("   \n\n")
    dialog.run_conversion()
    assert dialog.worker is None
    assert "at least one name" in dialog.status.text()


def test_results_fill_the_table(dialog, monkeypatch):
    convert_returns(monkeypatch, [BENZENE, BAD])
    dialog.input.setPlainText("benzene\nnonsense")
    run_sync(dialog)

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 0).text() == "benzene"
    assert dialog.table.item(0, 1).text() == "C6H6"
    assert dialog.table.item(0, 3).text() == "OK"
    assert "could not interpret" in dialog.table.item(1, 3).text()
    assert dialog.status.text() == "1 of 2 name(s) converted."


def test_failures_stay_visible(dialog, monkeypatch):
    convert_returns(monkeypatch, [BAD])
    dialog.input.setPlainText("nonsense")
    run_sync(dialog)
    assert dialog.table.rowCount() == 1  # not silently dropped


def test_load_puts_the_structure_in_the_editor(dialog, monkeypatch):
    convert_returns(monkeypatch, [BENZENE])
    dialog.input.setPlainText("benzene")
    run_sync(dialog)

    dialog.load_selected()

    assert dialog.context.loaded == ["c1ccccc1"]
    assert "Loaded" in dialog.status.text()


def test_load_refuses_a_failed_row(dialog, monkeypatch):
    convert_returns(monkeypatch, [BAD])
    dialog.input.setPlainText("nonsense")
    run_sync(dialog)

    dialog.load_selected()

    assert dialog.context.loaded == []
    assert "did not convert" in dialog.status.text()


def test_load_without_a_selection_is_reported(dialog):
    dialog.load_selected()
    assert "Select a row" in dialog.status.text()


def test_load_failure_from_the_host_is_surfaced(dialog, monkeypatch):
    convert_returns(monkeypatch, [BENZENE])
    dialog.input.setPlainText("benzene")
    run_sync(dialog)
    dialog.context.load_error = RuntimeError("editor busy")
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.warning", lambda *a, **k: None)

    dialog.load_selected()

    assert dialog.context.loaded == []


@pytest.mark.parametrize(
    "field,expected",
    [
        ("smiles", "c1ccccc1"),
        ("inchi", "InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H"),
        ("inchikey", "UHOVQNZJYSORNB-UHFFFAOYSA-N"),
    ],
)
def test_copy_puts_the_field_on_the_clipboard(dialog, monkeypatch, field, expected):
    from PyQt6.QtWidgets import QApplication

    convert_returns(monkeypatch, [BENZENE])
    dialog.input.setPlainText("benzene")
    run_sync(dialog)

    dialog.copy_field(field)

    assert QApplication.clipboard().text() == expected


def test_copy_of_a_missing_field_is_reported(dialog, monkeypatch):
    convert_returns(monkeypatch, [BAD])
    dialog.input.setPlainText("nonsense")
    run_sync(dialog)
    dialog.copy_field("inchi")
    assert "No inchi" in dialog.status.text()


def test_options_are_read_from_the_checkboxes(dialog):
    dialog.opt_radicals.setChecked(True)
    dialog.opt_stereo.setChecked(True)
    options = dialog.options()
    assert options.allow_radicals and options.allow_bad_stereo
    assert not options.allow_acid and not options.wildcard_radicals


def test_opsin_failure_shows_a_warning(dialog, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QMessageBox.warning",
        lambda parent, title, text, *a, **k: seen.setdefault("text", text),
    )

    def unavailable(names, options=None, **kwargs):
        raise engine.OpsinUnavailable("Java vanished")

    monkeypatch.setattr(engine, "convert", unavailable)
    dialog.input.setPlainText("benzene")
    run_sync(dialog)

    assert seen["text"] == "Java vanished"
    assert dialog.convert_button.isEnabled()  # not left stuck disabled


def test_close_releases_the_window(qapp, monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    context = FakeContext()
    win = OpsinDialog(context)
    context.register_window(WINDOW_ID, win)

    win.close()

    assert context.windows[WINDOW_ID] is None


def test_escape_releases_the_window_too(qapp, monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    context = FakeContext()
    win = OpsinDialog(context)
    context.register_window(WINDOW_ID, win)

    win.reject()  # Esc never reaches closeEvent

    assert context.windows[WINDOW_ID] is None
