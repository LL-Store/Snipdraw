"""Linux 全局热键占位：X11 用 python-xlib 实现，Wayland 无解。

v1 先明确失败（返回 HotkeyError），由 HotkeyManager 回退到 UI 里的提示，
不做“静默注册成功但其实收不到事件”这种假象。
"""

from __future__ import annotations

from typing import Callable

from .hotkey import HotkeyBackend, HotkeyError


class X11Hotkey(HotkeyBackend):
    name = "XGrabKey"

    def register(self, sequence: str, callback: Callable[[], None]) -> None:
        raise HotkeyError("Linux 全局热键尚未实现（计划在 M5 补 X11 XGrabKey）")

    def unregister(self) -> None:
        pass
