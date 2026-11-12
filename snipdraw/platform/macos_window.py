"""macOS 窗口层级：把 overlay / 贴图抬到菜单栏和 Dock 之上。

Qt 的 WindowStaysOnTopHint 相当于 NSFloatingWindowLevel，低于菜单栏（24）和 Dock（20），
全屏 overlay 会被压在下面。这里直接用 objc_msgSend 调 AppKit 抬高 level，
不引 pyobjc——为一个调用装几十 MB 不值得。

注意：objc_msgSend 必须用 ctypes.cast 转成对应签名的函数指针再调用，
直接把 CDLL 属性塞进 CFUNCTYPE(...)(...) 会跳到野地址，进程直接段错误。
"""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtGui import QGuiApplication

LEVEL_ABOVE_SYSTEM = 1000              # NSScreenSaverWindowLevel
NS_FLOATING = 3                        # NSFloatingWindowLevel，贴图用
COLLECTION_ALL_SPACES = (1 << 0) | (1 << 8)   # CanJoinAllSpaces | FullScreenAuxiliary

_SEND_OBJECT = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
_SEND_VOID_LONG = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)
_SEND_VOID_ULONG = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
_SEND_VOID_INT = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)

_cache: dict[str, object] = {}


def _load():
    if "sel" in _cache:
        return _cache
    lib = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
    lib.sel_registerName.restype = ctypes.c_void_p
    lib.sel_registerName.argtypes = [ctypes.c_char_p]
    _cache["sel"] = lib.sel_registerName
    _cache["object"] = ctypes.cast(lib.objc_msgSend, _SEND_OBJECT)
    _cache["long"] = ctypes.cast(lib.objc_msgSend, _SEND_VOID_LONG)
    _cache["ulong"] = ctypes.cast(lib.objc_msgSend, _SEND_VOID_ULONG)
    _cache["int"] = ctypes.cast(lib.objc_msgSend, _SEND_VOID_INT)
    return _cache


def _ns_window(widget):
    # offscreen / minimal 等非 cocoa 平台下 winId() 不是真的 NSView，
    # 拿去调 objc_msgSend 会直接段错误（CI 与无头测试常见）
    app = QGuiApplication.instance()
    if app is None or app.platformName() != "cocoa":
        return None
    cache = _load()
    view = int(widget.winId())
    if not view:
        return None
    send_object = cache["object"]
    return send_object(view, cache["sel"](b"window"))


def raise_above_system(widget, level: int = LEVEL_ABOVE_SYSTEM) -> bool:
    """抬到系统层级之上（盖住菜单栏与 Dock）。失败返回 False，保持原行为。"""
    if sys.platform != "darwin":
        return False
    try:
        cache = _load()
        window = _ns_window(widget)
        if not window:
            return False
        cache["long"](window, cache["sel"](b"setLevel:"), level)
        cache["ulong"](window, cache["sel"](b"setCollectionBehavior:"), COLLECTION_ALL_SPACES)
        return True
    except Exception:
        return False


def set_floating(widget) -> bool:
    """普通浮窗（贴图）用，不抢菜单栏。"""
    if sys.platform != "darwin":
        return False
    try:
        cache = _load()
        window = _ns_window(widget)
        if not window:
            return False
        cache["long"](window, cache["sel"](b"setLevel:"), NS_FLOATING)
        cache["ulong"](window, cache["sel"](b"setCollectionBehavior:"), COLLECTION_ALL_SPACES)
        return True
    except Exception:
        return False


def ignore_mouse_events(widget, ignore: bool) -> bool:
    """贴图的“鼠标穿透”。"""
    if sys.platform != "darwin":
        return False
    try:
        cache = _load()
        window = _ns_window(widget)
        if not window:
            return False
        cache["int"](window, cache["sel"](b"setIgnoresMouseEvents:"), 1 if ignore else 0)
        return True
    except Exception:
        return False
