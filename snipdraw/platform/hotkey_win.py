"""Windows 全局热键：RegisterHotKey + WM_HOTKEY。"""

from __future__ import annotations

import ctypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

from .hotkey import HotkeyBackend, HotkeyError

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

VK_PARSE_OK = 0

# Qt.Key → 虚拟键码：字母数字与 ASCII 一致，功能键 0x70 起
VK_EXTRA = {
    "Space": 0x20,
    "Print": 0x2A,
    "Escape": 0x1B,
    "Tab": 0x09,
    "Return": 0x0D,
}


class MSG(ctypes.Structure):
    """只对齐到 message/wParam 就够；后面用 padding 对齐。"""

    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint32),
        ("_pad", ctypes.c_uint32),
        ("wParam", ctypes.c_void_p),
        ("lParam", ctypes.c_void_p),
        ("time", ctypes.c_uint32),
        ("pt_x", ctypes.c_int32),
        ("pt_y", ctypes.c_int32),
        ("lPrivate", ctypes.c_uint32),
    ]


class _WinHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id: int, callback: Callable[[], None]) -> None:
        super().__init__()
        self.hotkey_id = hotkey_id
        self.callback = callback

    def nativeEventFilter(self, eventType, message):  # noqa: N802 (Qt 命名)
        try:
            if bytes(eventType) != b"windows_generic_MSG":
                return False, 0
            msg = MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and int(msg.wParam or 0) == self.hotkey_id:
                self.callback()
        except Exception:
            pass
        return False, 0


class WindowsHotkey(HotkeyBackend):
    name = "RegisterHotKey"

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        self._id = 0xB001
        self._filter: _WinHotkeyFilter | None = None
        self._registered = False

    @staticmethod
    def _parse(sequence: str) -> tuple[int, int]:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeySequence

        qs = QKeySequence.fromString(sequence)
        if qs.count() == 0:
            raise HotkeyError(f"无法解析热键：{sequence}")
        combo = qs[0]
        key = combo.key()
        if 0x41 <= key <= 0x5A or 0x30 <= key <= 0x39:
            vk = key
        elif 0x01000030 <= key <= 0x0100003B:
            vk = 0x70 + (key - 0x01000030)
        else:
            vk = VK_EXTRA.get(QKeySequence(key).toString())
            if vk is None:
                raise HotkeyError(f"暂不支持该按键：{sequence}")

        mods = MOD_NOREPEAT
        flags = combo.keyboardModifiers()
        if flags & Qt.KeyboardModifier.ControlModifier:
            mods |= MOD_CONTROL
        if flags & Qt.KeyboardModifier.AltModifier:
            mods |= MOD_ALT
        if flags & Qt.KeyboardModifier.ShiftModifier:
            mods |= MOD_SHIFT
        if flags & Qt.KeyboardModifier.MetaModifier:
            mods |= MOD_WIN
        return vk, mods

    def register(self, sequence: str, callback: Callable[[], None]) -> None:
        vk, mods = self._parse(sequence)
        self._filter = _WinHotkeyFilter(self._id, callback)
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        if not self._user32.RegisterHotKey(None, self._id, mods, vk):
            QCoreApplication.instance().removeNativeEventFilter(self._filter)
            self._filter = None
            raise HotkeyError("组合被其它程序占用")
        self._registered = True
        self._sequence = sequence

    def unregister(self) -> None:
        if self._registered:
            self._user32.UnregisterHotKey(None, self._id)
            self._registered = False
        if self._filter is not None:
            instance = QCoreApplication.instance()
            if instance is not None:
                instance.removeNativeEventFilter(self._filter)
            self._filter = None
