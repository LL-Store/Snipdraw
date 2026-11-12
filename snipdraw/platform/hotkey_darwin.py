"""macOS 全局热键：Carbon RegisterEventHotKey。

选它的理由：这是唯一不需要"辅助功能"权限的全局热键通道。
CGEventTap / pynput 都要用户去隐私设置里勾选，体验差很多。
"""

from __future__ import annotations

import ctypes
import ctypes.util
from typing import Callable

from .hotkey import HotkeyBackend, HotkeyError

# Carbon 常量
K_EVENT_CLASS_KEYBOARD = 0x6B657962  # 'keyb'
K_EVENT_HOTKEY_PRESSED = 5
CMD_KEY = 0x0100
SHIFT_KEY = 0x0200
OPTION_KEY = 0x0800
CONTROL_KEY = 0x1000
NO_ERR = 0

# Qt.Key → macOS 虚拟键码（kVK_*）
VK_CODES: dict[int, int] = {
    0x41: 0x00, 0x53: 0x01, 0x44: 0x02, 0x46: 0x03, 0x48: 0x04,
    0x47: 0x05, 0x5A: 0x06, 0x58: 0x07, 0x43: 0x08, 0x56: 0x09,
    0x42: 0x0B, 0x51: 0x0C, 0x57: 0x0D, 0x45: 0x0E, 0x52: 0x0F,
    0x59: 0x10, 0x54: 0x11, 0x31: 0x12, 0x32: 0x13, 0x33: 0x14,
    0x34: 0x15, 0x36: 0x16, 0x35: 0x17, 0x39: 0x19, 0x37: 0x1A,
    0x38: 0x1C, 0x30: 0x1D, 0x4F: 0x1F, 0x55: 0x20, 0x49: 0x22,
    0x50: 0x23, 0x4C: 0x25, 0x4A: 0x26, 0x4B: 0x28, 0x4E: 0x2D,
    0x4D: 0x2E,
}


def _fkey_vk(qt_key: int) -> int | None:
    """Qt.Key_F1=0x01000030，+n 递增；F1–F12 的 mVK 不是连号，逐个给。"""
    table = {
        1: 0x7A, 2: 0x78, 3: 0x63, 4: 0x76, 5: 0x60, 6: 0x61,
        7: 0x62, 8: 0x64, 9: 0x65, 10: 0x6D, 11: 0x67, 12: 0x6F,
    }
    base = 0x01000030
    index = qt_key - base + 1
    return table.get(index)


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


_EventHandlerProc = ctypes.CFUNCTYPE(
    ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)


class DarwinHotkey(HotkeyBackend):
    name = f"Carbon"

    def __init__(self) -> None:
        self._carbon = None
        self._hotkey_ref = ctypes.c_void_p()
        self._handler_ref = ctypes.c_void_p()
        self._proc = None
        self._callback: Callable[[], None] | None = None
        self._next_id = 1

    def _load(self):
        if self._carbon is not None:
            return self._carbon
        path = ctypes.util.find_library("Carbon")
        if not path:
            raise HotkeyError("找不到 Carbon 框架，无法注册全局热键")
        carbon = ctypes.cdll.LoadLibrary(path)
        carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        carbon.GetApplicationEventTarget.argtypes = []
        carbon.RegisterEventHotKey.restype = ctypes.c_int32
        carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            _EventHotKeyID,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        carbon.UnregisterEventHotKey.restype = ctypes.c_int32
        carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        carbon.InstallEventHandler.restype = ctypes.c_int32
        carbon.InstallEventHandler.argtypes = [
            ctypes.c_void_p,
            _EventHandlerProc,
            ctypes.c_int32,
            ctypes.POINTER(_EventTypeSpec),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        carbon.RemoveEventHandler.restype = ctypes.c_int32
        carbon.RemoveEventHandler.argtypes = [ctypes.c_void_p]
        self._carbon = carbon
        return carbon

    @staticmethod
    def _parse(sequence: str) -> tuple[int, int]:
        from PySide6.QtGui import QKeySequence

        qs = QKeySequence.fromString(sequence)
        if qs.count() == 0:
            raise HotkeyError(f"无法解析热键：{sequence}")
        combo = qs[0]
        key = combo.key()
        # 注意：kVK_ANSI_A 的虚拟键码就是 0x00，用 `or` 判断会把它当成"没有"，
        # 于是 Ctrl+Alt+A 这类以 A 结尾的组合永远解析失败。必须显式判存在。
        vk = VK_CODES[key] if key in VK_CODES else _fkey_vk(key)
        if vk is None:
            raise HotkeyError(f"暂不支持该按键：{sequence}")

        mods = 0
        flags = combo.keyboardModifiers()
        from PySide6.QtCore import Qt

        if flags & Qt.KeyboardModifier.ControlModifier:
            mods |= CONTROL_KEY
        if flags & Qt.KeyboardModifier.AltModifier:
            mods |= OPTION_KEY
        if flags & Qt.KeyboardModifier.ShiftModifier:
            mods |= SHIFT_KEY
        if flags & Qt.KeyboardModifier.MetaModifier:
            mods |= CMD_KEY
        return vk, mods

    def register(self, sequence: str, callback: Callable[[], None]) -> None:
        carbon = self._load()
        vk, mods = self._parse(sequence)
        self._callback = callback

        def _handler(call_ref, event_ref, user_data):
            if self._callback is not None:
                try:
                    self._callback()
                except Exception:
                    # 回调异常不能穿回 Carbon 事件循环，否则可能直接崩溃
                    pass
            return NO_ERR

        self._proc = _EventHandlerProc(_handler)
        spec = _EventTypeSpec(K_EVENT_CLASS_KEYBOARD, K_EVENT_HOTKEY_PRESSED)
        target = carbon.GetApplicationEventTarget()
        status = carbon.InstallEventHandler(
            target, self._proc, 1, ctypes.byref(spec), None, ctypes.byref(self._handler_ref)
        )
        if status != NO_ERR:
            raise HotkeyError(f"安装事件处理器失败（OSStatus={status}）")

        hotkey_id = _EventHotKeyID(0x536E7064, self._next_id)  # 'Snpd'
        self._next_id += 1
        status = carbon.RegisterEventHotKey(
            vk, mods, hotkey_id, target, 0, ctypes.byref(self._hotkey_ref)
        )
        if status != NO_ERR:
            carbon.RemoveEventHandler(self._handler_ref)
            self._handler_ref = ctypes.c_void_p()
            self._proc = None
            # -9878 常见于该组合已被系统或别的应用占用
            raise HotkeyError(f"组合被占用或不可用（OSStatus={status}）")

    def unregister(self) -> None:
        carbon = self._carbon
        if carbon is None:
            return
        if self._hotkey_ref:
            carbon.UnregisterEventHotKey(self._hotkey_ref)
            self._hotkey_ref = ctypes.c_void_p()
        if self._handler_ref:
            carbon.RemoveEventHandler(self._handler_ref)
            self._handler_ref = ctypes.c_void_p()
        self._proc = None
        self._callback = None
