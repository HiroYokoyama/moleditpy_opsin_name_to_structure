"""Plugin metadata and registration."""

import re

import opsin_name_to_structure as plugin
from opsin_name_to_structure import engine

from .fakes import FakeContext


def test_metadata():
    assert plugin.PLUGIN_NAME == "OPSIN Name to Structure"
    assert re.fullmatch(r"\d+\.\d+\.\d+", plugin.PLUGIN_VERSION)
    assert plugin.PLUGIN_AUTHOR and plugin.PLUGIN_DESCRIPTION
    assert isinstance(plugin.PLUGIN_TAGS, list) and plugin.PLUGIN_TAGS


def test_py2opsin_is_declared_because_it_carries_the_jar():
    assert plugin.PLUGIN_DEPENDENCIES == ["py2opsin"]


def test_supported_os_and_python():
    assert set(plugin.PLUGIN_SUPPORTED_OS) == {"Windows", "macOS", "Linux", "WSL"}
    assert plugin.PLUGIN_SUPPORTED_PYTHON_VERSION.startswith(">=3.9")
    assert plugin.PLUGIN_SUPPORTED_MOLEDITPY_VERSION.startswith(">=3.0.0")


def test_initialize_registers_one_menu_entry(qapp):
    context = FakeContext()
    plugin.initialize(context)
    assert len(context.menu_actions) == 1
    assert context.menu_actions[0][0].startswith("OPSIN Name to Structure")


def test_menu_callback_opens_the_window(qapp, monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    context = FakeContext()
    plugin.initialize(context)

    window = context.menu_actions[0][1]()

    assert context.get_window("main_panel") is window
    window.close()


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
