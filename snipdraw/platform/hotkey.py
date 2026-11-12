"""全局热键：统一接口 + 平台后端。

Qt 本身不提供全局热键，所以这里是整个项目里唯一需要写平台代码的地方：
- macOS: Carbon RegisterEventHotKey（不需要辅助功能权限）
- Windows: RegisterHotKey + WM_HOTKEY
- Linux: X11 XGrabKey（v1 之后补），Wayland 无解 → NullHotkey
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import Callable


class HotkeyError(RuntimeError):
    pass


class HotkeyBackend(ABC):
    name = "unknown"

    @abstractmethod
    def register(self, sequence: str, callback: Callable[[], None]) -> None:
        """注册失败抛 HotkeyError，消息要能直接展示给用户。"""

    @abstractmethod
    def unregister(self) -> None:
        ...


def create_backend() -> HotkeyBackend:
    if sys.platform == "darwin":
        from .hotkey_darwin import DarwinHotkey

        return DarwinHotkey()
    if sys.platform == "win32":
        from .hotkey_win import WindowsHotkey

        return WindowsHotkey()
    if sys.platform.startswith("linux"):
        from .hotkey_x11 import X11Hotkey

        return X11Hotkey()
    from .hotkey_null import NullHotkey

    return NullHotkey("当前平台不支持全局热键")


class HotkeyManager:
    """先试主热键，失败再试 fallback，并记录实际生效的组合。"""

    def __init__(self, backend: HotkeyBackend | None = None) -> None:
        self.backend = backend or create_backend()
        self.active_sequence: str | None = None
        self.message: str = ""
        self._callback: Callable[[], None] | None = None

    def bind(self, primary: str, fallback: str, callback: Callable[[], None]) -> str | None:
        self._callback = callback
        self.active_sequence = None
        self.message = ""   # 每次重绑都重新算，别把上一次的失败提示挂在这里
        errors: list[str] = []
        for sequence in (primary, fallback):
            if not sequence:
                continue
            try:
                self.backend.register(sequence, callback)
            except HotkeyError as error:
                errors.append(f"{sequence}: {error}")
                continue
            self.active_sequence = sequence
            if sequence != primary:
                self.message = f"{primary} 注册失败，已改用 {sequence}"
            return sequence
        self.message = "；".join(errors) or "没有可用的热键"
        return None

    def release(self) -> None:
        try:
            self.backend.unregister()
        except Exception:
            pass
        self.active_sequence = None
