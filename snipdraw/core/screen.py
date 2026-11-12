"""Qt 屏幕枚举：把 QScreen 包装成纯数据的 ScreenGeometry。"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication, QScreen

from .geometry import ScreenGeometry


def geometry_of(qscreen: QScreen) -> ScreenGeometry:
    g = qscreen.geometry()
    return ScreenGeometry(
        name=qscreen.name() or "display",
        x=g.x(),
        y=g.y(),
        width=g.width(),
        height=g.height(),
        dpr=float(qscreen.devicePixelRatio()),
    )


def qscreens() -> list[QScreen]:
    return list(QGuiApplication.screens())


def screen_pairs() -> list[tuple[ScreenGeometry, QScreen]]:
    """按枚举顺序返回 (几何, QScreen)，两边的索引一一对应。"""
    return [(geometry_of(s), s) for s in qscreens()]


def screens() -> list[ScreenGeometry]:
    return [geometry_of(s) for s in qscreens()]


def primary() -> ScreenGeometry | None:
    screen = QGuiApplication.primaryScreen()
    return geometry_of(screen) if screen else None
