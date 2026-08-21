"""Headless Qt + quiet RDKit for the whole suite."""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from rdkit import RDLogger

    RDLogger.DisableLog("rdApp.*")
except ImportError:  # pragma: no cover - rdkit missing is reported by the tests
    pass


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the session; widgets need it to exist."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
