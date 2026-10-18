"""
OPSIN Name to Structure plugin for MoleditPy.
Converts systematic IUPAC names into structures locally with OPSIN, and loads
them into the 2D editor. No network: names are parsed on this computer, so it
also handles names no database has ever indexed.

OPSIN is a Java program. This plugin ships no Java of its own — the jar comes
from the pip-installable py2opsin package, and a Java runtime must be present.

Source code, README, and full license (GNU GPL):
    https://github.com/HiroYokoyama/moleditpy_opsin_name_to_structure
Copyright (c) HiroYokoyama. Licensed under the GNU General Public License;
see the LICENSE file in the repository above for the full terms.
"""

import logging

logger = logging.getLogger(__name__)

# Qt and the dialog are imported inside show_dialog on purpose: it keeps
# `from opsin_name_to_structure import engine` working without PySide6, so the
# conversion logic can be used (and tested) headless.

# --- Plugin Metadata ---
PLUGIN_NAME = "OPSIN Name to Structure"
PLUGIN_VERSION = "2.0.0"
PLUGIN_AUTHOR = "HiroYokoyama"
PLUGIN_DESCRIPTION = (
    "Convert systematic IUPAC names into structures offline with OPSIN "
    "and load them into the 2D editor. Requires Java Runtime (JRE)."
)
PLUGIN_CATEGORY = "Import"
PLUGIN_TAGS = ["Utility"]
PLUGIN_DEPENDENCIES = ["py2opsin"]
PLUGIN_SUPPORTED_MOLEDITPY_VERSION = ">=5.0.0, <6.0.0"
PLUGIN_SUPPORTED_PYTHON_VERSION = ">=3.10, <3.15"
PLUGIN_SUPPORTED_OS = ["Windows", "macOS", "Linux", "WSL"]

PLUGIN_CONTEXT = None


def initialize(context):
    """Store the context for the host-auto-registered run() entry point.

    The host picks up run() and adds it to the Plugins menu automatically,
    so no explicit add_plugin_menu() call is needed here.
    """
    global PLUGIN_CONTEXT
    PLUGIN_CONTEXT = context


def run(mw):
    """Entry point called by the host from the Plugins menu."""
    if hasattr(mw, "host"):
        mw = mw.host
    context = PLUGIN_CONTEXT
    if not context:
        return
    show_dialog(context)


def show_dialog(context):
    """Singleton: reuse the existing window if it is already open."""
    from PySide6.QtWidgets import QWidget

    from .main_dialog import WINDOW_ID, OpsinDialog

    window = context.get_window(WINDOW_ID)
    if window:
        window.show()
        window.raise_()
        window.activateWindow()
        return window

    main_window = context.get_main_window()
    parent = main_window if isinstance(main_window, QWidget) else None
    dialog = OpsinDialog(context, parent)
    context.register_window(WINDOW_ID, dialog)
    dialog.show()
    return dialog
