"""无热键后端：Wayland / 未知平台，热键功能明确不可用。"""

from __future__ import annotations

from typing import Callable

from .hotkey import HotkeyBackend, HotkeyError


class NullHotkey(HotkeyBackend):
    name = "none"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def register(self, sequence: str, callback: Callable[[], None]) -> None:
        raise HotkeyError(self.reason)

    def unregister(self) -> None:
        pass
