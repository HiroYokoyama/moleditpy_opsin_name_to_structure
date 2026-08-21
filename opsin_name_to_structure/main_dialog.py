"""The OPSIN window: names in, structures out, into the 2D editor."""

import logging
from typing import Any, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from . import engine

logger = logging.getLogger(__name__)

WINDOW_ID = "main_panel"
_COLUMNS = ["Name", "Formula", "SMILES", "Status"]
_PLACEHOLDER = (
    "One name per line, for example:\n"
    "  2,4-dimethoxybenzaldehyde\n"
    "  (2R)-2-amino-3-phenylpropanoic acid\n"
    "  4-[(1E)-2-phenylethenyl]pyridine"
)


class ConvertWorker(QThread):
    """Runs OPSIN off the GUI thread; a batch is one JVM start."""

    done = pyqtSignal(list)
    failed = pyqtSignal(str)

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

        self.setWindowTitle("OPSIN Name to Structure")
        self.setModal(False)
        self.resize(820, 620)
        self._build_ui()
        self._check_availability()

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
        self.convert_button.clicked.connect(self.run_conversion)
        actions.addWidget(self.convert_button)
        self.status = QLabel("Offline — names are parsed on this computer.")
        self.status.setWordWrap(True)
        actions.addWidget(self.status, 1)
        layout.addLayout(actions)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
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
        buttons.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _check_availability(self) -> None:
        """OPSIN needs Java, which pip cannot install: say so up front."""
        usable, message = engine.availability()
        self.convert_button.setEnabled(usable)
        if usable:
            self.notice.hide()
            return
        self.notice.setText(message)
        self.notice.show()
        self.status.setText("OPSIN is unavailable.")

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
        names = engine.split_names(self.input.toPlainText())
        if not names:
            self.status.setText("Type at least one name.")
            return

        self.convert_button.setEnabled(False)
        self.status.setText(f"Converting {len(names)} name(s)...")
        self.worker = ConvertWorker(names, self.options())
        self.worker.done.connect(self._conversion_done)
        self.worker.failed.connect(self._conversion_failed)
        self.worker.start()

    def _conversion_done(self, results: List[engine.Conversion]) -> None:
        self.results = results
        self.populate_table()
        good = sum(1 for r in results if r.ok)
        self.status.setText(f"{good} of {len(results)} name(s) converted.")
        self.convert_button.setEnabled(True)

    def _conversion_failed(self, message: str) -> None:
        self.status.setText("OPSIN could not run.")
        self.convert_button.setEnabled(True)
        QMessageBox.warning(self, "OPSIN Name to Structure", message)

    def populate_table(self) -> None:
        """Show every row, failures included, so nothing disappears silently."""
        self.table.setRowCount(0)
        for result in self.results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            status = "OK" if result.ok else (result.error or "Failed")
            for column, text in enumerate(
                (result.name, result.formula, result.smiles, status)
            ):
                self.table.setItem(row, column, QTableWidgetItem(text))
        if self.results:
            self.table.selectRow(0)

    # --- results ---

    def selected_result(self) -> Optional[engine.Conversion]:
        row = self.table.currentRow()
        if 0 <= row < len(self.results):
            return self.results[row]
        return None

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
        """Copy one field of the selected row to the clipboard."""
        result = self.selected_result()
        if result is None:
            self.status.setText("Select a row first.")
            return
        value = getattr(result, attribute, "")
        if not value:
            self.status.setText(f"No {attribute} for '{result.name}'.")
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(value)
        self.status.setText(f"Copied {attribute} for '{result.name}'.")

    # --- teardown ---

    def _teardown(self) -> None:
        worker = self.worker
        if worker is not None and worker.isRunning():
            worker.wait(engine.DEFAULT_TIMEOUT * 1000)
        self.worker = None
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
