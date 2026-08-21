"""Test doubles for the bits of MoleditPy this plugin touches."""

from typing import Any, Dict, List, Optional


class FakeContext:
    """Stands in for PluginContext."""

    def __init__(self, main_window: Any = None) -> None:
        self.main_window = main_window
        self.windows: Dict[str, Any] = {}
        self.menu_actions: List[Any] = []
        self.loaded: List[str] = []
        self.messages: List[str] = []
        self.load_error: Optional[Exception] = None

    def get_main_window(self) -> Any:
        return self.main_window

    def add_plugin_menu(self, path, callback, **kwargs) -> None:
        self.menu_actions.append((path, callback))

    def add_menu_action(self, path, callback, **kwargs) -> None:
        self.menu_actions.append((path, callback))

    def register_window(self, window_id: str, window: Any) -> None:
        self.windows[window_id] = window

    def get_window(self, window_id: str) -> Any:
        return self.windows.get(window_id)

    def load_from_smiles(self, smiles: str) -> None:
        if self.load_error is not None:
            raise self.load_error
        self.loaded.append(smiles)

    def show_status_message(self, message: str, timeout: int = 3000) -> None:
        self.messages.append(message)
