"""主题解析：system 跟随系统配色，light / dark 强制深浅。"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication


def system_is_dark() -> bool:
    window = QGuiApplication.palette().window().color()
    return window.lightness() < 128


def resolve_theme(theme: str) -> str:
    """把存储的 theme 归一成 "light" / "dark"。"""
    if theme == "light":
        return "light"
    if theme == "dark":
        return "dark"
    return "dark" if system_is_dark() else "light"
