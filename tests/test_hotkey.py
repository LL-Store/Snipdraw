"""热键解析与回退链的单元测试。"""

from __future__ import annotations

import sys
from typing import Callable

import pytest

from snipdraw.platform.hotkey import HotkeyBackend, HotkeyError, HotkeyManager


class _FakeBackend(HotkeyBackend):
    """按预设决定哪些组合"能注册上"。"""

    name = "fake"

    def __init__(self, available: set[str]) -> None:
        self.available = set(available)
        self.active: str | None = None

    def register(self, sequence: str, callback: Callable[[], None]) -> None:
        if sequence not in self.available:
            raise HotkeyError("组合被占用")
        self.active = sequence

    def unregister(self) -> None:
        self.active = None


def test_bind_falls_back_when_primary_occupied():
    manager = HotkeyManager(_FakeBackend({"Ctrl+Alt+A"}))
    assert manager.bind("F1", "Ctrl+Alt+A", lambda: None) == "Ctrl+Alt+A"
    assert "已改用" in manager.message


def test_bind_reports_both_failures():
    manager = HotkeyManager(_FakeBackend(set()))
    assert manager.bind("F1", "Ctrl+Alt+A", lambda: None) is None
    assert "F1" in manager.message and "Ctrl+Alt+A" in manager.message


def test_rebind_clears_stale_message():
    """先回退、再改好设置重绑：上一次的失败提示不能留在 message 里。

    否则 app 会在"其实已经成功"的情况下继续往上贴旧警告。
    """
    manager = HotkeyManager(_FakeBackend({"Ctrl+Alt+A"}))
    manager.bind("F1", "Ctrl+Alt+A", lambda: None)
    assert manager.message

    manager.release()
    manager.backend = _FakeBackend({"F1"})
    assert manager.bind("F1", "Ctrl+Alt+A", lambda: None) == "F1"
    assert manager.message == ""


@pytest.mark.skipif(sys.platform != "darwin", reason="Carbon 键码表只在 macOS 上存在")
def test_darwin_parses_letter_and_function_keys():
    """kVK_ANSI_A 就是 0x00，不能被当成"没有映射"。"""
    from snipdraw.platform.hotkey_darwin import CONTROL_KEY, OPTION_KEY, DarwinHotkey

    vk, mods = DarwinHotkey._parse("Ctrl+Alt+A")
    assert vk == 0x00
    assert mods == CONTROL_KEY | OPTION_KEY

    assert DarwinHotkey._parse("F1")[0] == 0x7A
