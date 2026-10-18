"""Plugin metadata and registration."""

import re

import pytest

import opsin_name_to_structure as plugin
from opsin_name_to_structure import engine

from .fakes import FakeContext


def test_metadata():
    assert plugin.PLUGIN_NAME == "OPSIN Name to Structure"
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:a\d+)?", plugin.PLUGIN_VERSION)
    assert plugin.PLUGIN_AUTHOR and plugin.PLUGIN_DESCRIPTION
    assert isinstance(plugin.PLUGIN_TAGS, list) and plugin.PLUGIN_TAGS


def test_py2opsin_is_declared_because_it_carries_the_jar():
    assert plugin.PLUGIN_DEPENDENCIES == ["py2opsin"]


def test_supported_os_and_python():
    assert set(plugin.PLUGIN_SUPPORTED_OS) == {"Windows", "macOS", "Linux", "WSL"}
    assert plugin.PLUGIN_SUPPORTED_PYTHON_VERSION.startswith(">=3.10")
    assert plugin.PLUGIN_SUPPORTED_MOLEDITPY_VERSION.startswith(">=3.0.0")


def test_initialize_stores_context_only(qapp):
    """initialize() must NOT call add_plugin_menu; run() is the menu entry point."""
    context = FakeContext()
    plugin.initialize(context)
    assert len(context.menu_actions) == 0
    assert plugin.PLUGIN_CONTEXT is context


def test_run_opens_the_window(qapp, monkeypatch):
    """run(mw) is the entry point the host calls from the Plugins menu."""
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    context = FakeContext()
    plugin.initialize(context)

    plugin.run(context.get_main_window())

    assert context.get_window("main_panel") is not None
    context.get_window("main_panel").close()


def test_run_before_initialize_is_a_no_op():
    """run() called before initialize() must not raise."""
    saved = plugin.PLUGIN_CONTEXT
    plugin.PLUGIN_CONTEXT = None
    try:
        plugin.run(object())  # should return silently
    finally:
        plugin.PLUGIN_CONTEXT = saved


def test_show_dialog_is_a_singleton(qapp, monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    context = FakeContext()
    first = plugin.show_dialog(context)
    second = plugin.show_dialog(context)
    assert first is second
    first.close()


def test_a_non_widget_main_window_does_not_crash(qapp, monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    context = FakeContext(main_window=object())
    window = plugin.show_dialog(context)
    assert window is not None
    window.close()


def test_engine_and_metadata_import_without_qt():
    """The conversion side must not drag in PySide6.

    CI runs the real-OPSIN job without PySide6 installed; keeping Qt out of the
    package import is what lets the engine be used and tested headless.
    """
    import subprocess
    import sys
    from pathlib import Path

    script = (
        "import sys\n"
        "from importlib.abc import MetaPathFinder\n"
        "class Block(MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
        "            raise ModuleNotFoundError(name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "from opsin_name_to_structure import engine\n"
        "import opsin_name_to_structure as p\n"
        "assert callable(engine.convert) and p.PLUGIN_VERSION\n"
        "print('ok')\n"
    )
    repo = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=repo
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


@pytest.mark.parametrize("hook", ["initialize", "run", "show_dialog"])
def test_public_hooks_exist(hook):
    assert callable(getattr(plugin, hook))
