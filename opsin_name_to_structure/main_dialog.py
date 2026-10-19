"""The OPSIN window: names in, structures out, into the 2D editor."""

import csv
import logging
from typing import Any, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from . import engine

logger = logging.getLogger(__name__)

WINDOW_ID = "main_panel"
# "#" is the line the name came in on. It is what makes input order a sort
# order like any other: enabling sorting otherwise reorders the table the
# moment it is filled, and there is no way back to the order you typed.
_COLUMNS = ["#", "Name", "Formula", "SMILES", "InChIKey", "Status"]
_ORDER_COLUMN = 0
_SMILES_COLUMN = 3
#: Qt row -> index into self.results. Sorting reorders rows, not results.
_RESULT_INDEX = Qt.ItemDataRole.UserRole
_PLACEHOLDER = (
    "One name per line, for example:\n"
    "  2,4-dimethoxybenzaldehyde\n"
    "  (2R)-2-amino-3-phenylpropanoic acid\n"
    "  4-[(1E)-2-phenylethenyl]pyridine"
)
#: How long a closing window waits for a conversion before letting it run on.
_CLOSE_GRACE_MS = 3000

#: Workers outliving their dialog. A QThread whose last Python reference goes
#: while it is still running takes the process with it, so they wait here.
_ORPHANED: List["ConvertWorker"] = []


class ConvertWorker(QThread):
    """Runs OPSIN off the GUI thread; a batch is one JVM start."""

    done = Signal(list)
    failed = Signal(str)

    def __init__(self, names: List[str], options: engine.Options) -> None:
        super().__init__()
        self.names = names
        self.options = options

    def run(self) -> None:
        try:
            self.done.emit(engine.convert(self.names, self.options))
        except engine.OpsinUnavailable as exc:
            self.failed.emit(str(exc))
        except (OSError, ValueError, RuntimeError) as exc:  # pragma: no cover
            logger.exception("OPSIN conversion failed")
            self.failed.emit(f"OPSIN failed: {exc}")


class OpsinDialog(QDialog):
    """Non-modal: convert names, then load any result into the editor."""

    def __init__(self, context: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self.context = context
        self.results: List[engine.Conversion] = []
        self.worker: Optional[ConvertWorker] = None
        self._torn_down = False

        self.setWindowTitle("OPSIN Name to Structure")
        self.setModal(False)
        self.resize(880, 640)
        self._build_ui()
        self.check_availability()

    # --- UI ---

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet("QLabel { color: palette(bright-text); }")
        self.notice.hide()
        layout.addWidget(self.notice)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(_PLACEHOLDER)
        self.input.setMinimumHeight(110)
        layout.addWidget(self.input)

        options = QHBoxLayout()
        self.opt_radicals = QCheckBox("Allow radicals (substituent names)")
        self.opt_radicals.setToolTip(
            "Accept names that are only a substituent, such as 'pyridin-2-yl'."
        )
        self.opt_acid = QCheckBox("Allow acids without 'acid'")
        self.opt_acid.setToolTip("Accept 'acetic' as 'acetic acid'.")
        self.opt_stereo = QCheckBox("Allow uninterpretable stereo")
        self.opt_stereo.setToolTip(
            "Ignore stereochemistry OPSIN cannot interpret instead of failing."
        )
        self.opt_wildcard = QCheckBox("Wildcard radicals")
        self.opt_wildcard.setToolTip("Represent open valences as * wildcard atoms.")
        for box in (
            self.opt_radicals,
            self.opt_acid,
            self.opt_stereo,
            self.opt_wildcard,
        ):
            options.addWidget(box)
        options.addStretch()
        layout.addLayout(options)

        actions = QHBoxLayout()
        self.convert_button = QPushButton("Convert")
        self.convert_button.setDefault(True)
        self.convert_button.setToolTip("Convert every name in the box (Ctrl+Enter)")
        self.convert_button.clicked.connect(self.run_conversion)
        actions.addWidget(self.convert_button)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setToolTip("Empty the name box and the results table")
        self.clear_button.clicked.connect(self.clear_all)
        actions.addWidget(self.clear_button)
        self.status = QLabel("Offline — names are parsed on this computer.")
        self.status.setWordWrap(True)
        actions.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # OPSIN reports no progress: just show life
        self.progress.setMaximumWidth(120)
        self.progress.hide()
        actions.addWidget(self.progress)
        layout.addLayout(actions)

        # Enter has to stay a newline in a multi-line box, so Ctrl+Enter converts.
        for sequence in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(sequence), self, activated=self.run_conversion)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(
            _SMILES_COLUMN, QHeaderView.ResizeMode.Stretch
        )
        self.table.itemDoubleClicked.connect(lambda _item: self.load_selected())
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.load_button = QPushButton("Load to 2D Editor")
        self.load_button.clicked.connect(self.load_selected)
        buttons.addWidget(self.load_button)
        for label, attr in (
            ("Copy SMILES", "smiles"),
            ("Copy InChI", "inchi"),
            ("Copy InChIKey", "inchikey"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _c=False, a=attr: self.copy_field(a))
            buttons.addWidget(button)
        self.export_button = QPushButton("Export CSV...")
        self.export_button.setToolTip("Save every row, failures included, as CSV")
        self.export_button.clicked.connect(self.export_csv)
        buttons.addWidget(self.export_button)
        buttons.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def check_availability(self) -> bool:
        """OPSIN needs Java, which pip cannot install: say so up front."""
        usable, message = engine.availability()
        self.convert_button.setEnabled(usable)
        if usable:
            self.notice.hide()
            return True
        self.notice.setText(message)
        self.notice.show()
        self.status.setText("OPSIN is unavailable.")
        return False

    def showEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        """Re-check on every open.

        The window is a singleton, so a user who installs Java after seeing the
        notice would otherwise be stuck with a disabled Convert button for the
        rest of the session.
        """
        super().showEvent(event)
        if not self.convert_button.isEnabled():
            engine.jar_path.cache_clear()
            self.check_availability()

    # --- conversion ---

    def options(self) -> engine.Options:
        return engine.Options(
            allow_acid=self.opt_acid.isChecked(),
            allow_radicals=self.opt_radicals.isChecked(),
            allow_bad_stereo=self.opt_stereo.isChecked(),
            wildcard_radicals=self.opt_wildcard.isChecked(),
        )

    def run_conversion(self) -> None:
        """Start a background conversion of every name in the box."""
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.convert_button.isEnabled():
            return
        names = engine.split_names(self.input.toPlainText())
        if not names:
            self.status.setText("Type at least one name.")
            return

        self._set_busy(True)
        self.status.setText(f"Converting {len(names)} name(s)...")
        self.worker = ConvertWorker(names, self.options())
        self.worker.done.connect(self._conversion_done)
        self.worker.failed.connect(self._conversion_failed)
        self.worker.start()

    def _set_busy(self, busy: bool) -> None:
        """A batch can take a while; show that something is happening."""
        self.convert_button.setEnabled(not busy)
        self.input.setReadOnly(busy)
        self.progress.setVisible(busy)

    def _conversion_done(self, results: List[engine.Conversion]) -> None:
        self.results = results
        self.populate_table()
        good = sum(1 for r in results if r.ok)
        self.status.setText(f"{good} of {len(results)} name(s) converted.")
        self._set_busy(False)

    def _conversion_failed(self, message: str) -> None:
        self.status.setText("OPSIN could not run.")
        self._set_busy(False)
        QMessageBox.warning(self, "OPSIN Name to Structure", message)

    def clear_all(self) -> None:
        """Empty both the input and the results."""
        self.input.clear()
        self.results = []
        self.populate_table()
        self.status.setText("Cleared.")

    def populate_table(self) -> None:
        """Show every row, failures included, so nothing disappears silently."""
        # Filling a sorted table re-sorts as rows arrive, which scrambles them.
        self.table.setSortingEnabled(False)
        try:
            self.table.setRowCount(0)
            for index, result in enumerate(self.results):
                row = self.table.rowCount()
                self.table.insertRow(row)
                status = "OK" if result.ok else (result.error or "Failed")
                cells = (
                    result.name,
                    result.formula,
                    result.smiles,
                    result.inchikey,
                    status,
                )

                order = QTableWidgetItem()
                # A number, not its text: "10" must not sort before "2".
                order.setData(Qt.ItemDataRole.DisplayRole, index + 1)
                order.setData(_RESULT_INDEX, index)
                self.table.setItem(row, _ORDER_COLUMN, order)

                for offset, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    # Sorting shuffles rows; the row number stops meaning
                    # anything, so each cell carries its result's index.
                    item.setData(_RESULT_INDEX, index)
                    if text:
                        item.setToolTip(text)
                    self.table.setItem(row, _ORDER_COLUMN + 1 + offset, item)
        finally:
            self.table.setSortingEnabled(True)
        # Enabling sorting sorts by whatever the header last pointed at; point
        # it at input order so a fresh batch reads the way it was typed.
        self.table.sortItems(_ORDER_COLUMN, Qt.SortOrder.AscendingOrder)
        if self.results:
            self.table.selectRow(0)

    # --- results ---

    def result_at_row(self, row: int) -> Optional[engine.Conversion]:
        """The result a table row stands for, whatever the sort order is."""
        item = self.table.item(row, _ORDER_COLUMN)
        if item is None:
            return None
        index = item.data(_RESULT_INDEX)
        if isinstance(index, int) and 0 <= index < len(self.results):
            return self.results[index]
        return None

    def selected_result(self) -> Optional[engine.Conversion]:
        return self.result_at_row(self.table.currentRow())

    def selected_results(self) -> List[engine.Conversion]:
        """Every selected row, in the order the table shows them."""
        rows = sorted(
            index.row() for index in self.table.selectionModel().selectedRows()
        )
        found = [self.result_at_row(row) for row in rows]
        return [result for result in found if result is not None]

    def load_selected(self) -> None:
        """Put the selected structure into the 2D editor."""
        result = self.selected_result()
        if result is None:
            self.status.setText("Select a row first.")
            return
        if not result.ok:
            self.status.setText(f"'{result.name}' did not convert.")
            return
        try:
            self.context.load_from_smiles(result.smiles)
        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.warning("Could not load %s: %s", result.name, exc)
            QMessageBox.warning(
                self, "OPSIN Name to Structure", f"Could not load the structure: {exc}"
            )
            return
        self.status.setText(f"Loaded: {result.name}")

    def copy_field(self, attribute: str) -> None:
        """Copy one field of every selected row to the clipboard."""
        results = self.selected_results()
        if not results:
            self.status.setText("Select a row first.")
            return
        values = [getattr(result, attribute, "") for result in results]
        values = [value for value in values if value]
        if not values:
            names = ", ".join(f"'{r.name}'" for r in results)
            self.status.setText(f"No {attribute} for {names}.")
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText("\n".join(values))
        if len(values) == 1:
            self.status.setText(f"Copied {attribute} for '{results[0].name}'.")
        else:
            self.status.setText(f"Copied {len(values)} {attribute} values.")

    def export_csv(self) -> None:
        """Write every row, failures included, to a CSV file."""
        if not self.results:
            self.status.setText("Nothing to export yet.")
            return
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export results", "opsin_results.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            # newline="" is csv's own requirement; without it Windows doubles
            # every line break in the file.
            with open(path, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    ["Name", "Formula", "SMILES", "InChIKey", "InChI", "Status"]
                )
                for result in self.results:
                    writer.writerow(
                        [
                            result.name,
                            result.formula,
                            result.smiles,
                            result.inchikey,
                            result.inchi,
                            "OK" if result.ok else (result.error or "Failed"),
                        ]
                    )
        except OSError as exc:
            logger.warning("Could not export results: %s", exc)
            QMessageBox.warning(
                self, "OPSIN Name to Structure", f"Could not write the file: {exc}"
            )
            return
        self.status.setText(f"Exported {len(self.results)} row(s).")

    # --- teardown ---

    def _teardown(self) -> None:
        # close() after reject() would otherwise run all of this twice.
        if self._torn_down:
            return
        self._torn_down = True

        worker = self.worker
        self.worker = None
        if worker is not None:
            # Results must not arrive at a window that is going away.
            for signal in (worker.done, worker.failed):
                try:
                    signal.disconnect()
                except TypeError:  # nothing was connected
                    pass
            if worker.isRunning():
                # A JVM can outlast the window; wait briefly rather than
                # freezing the editor for the whole OPSIN timeout, then let it
                # finish on its own with a reference held so Qt keeps it alive.
                if not worker.wait(_CLOSE_GRACE_MS):
                    _ORPHANED.append(worker)
                    worker.finished.connect(lambda w=worker: _forget(w))
        # Without this the next open reuses a dead window.
        self.context.register_window(WINDOW_ID, None)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        """Release the window so reopening builds a live one."""
        self._teardown()
        event.accept()

    def reject(self) -> None:
        """Esc never reaches closeEvent, so tear down from here too."""
        self._teardown()
        super().reject()


def _forget(worker: "ConvertWorker") -> None:
    """Drop an orphaned worker once its thread has actually finished."""
    try:
        _ORPHANED.remove(worker)
    except ValueError:
        pass
