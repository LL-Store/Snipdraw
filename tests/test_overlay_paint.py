"""overlay 绘制健壮性：按下鼠标那一帧选区是零尺寸，不能把 painter 送进非法状态。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from snipdraw.core.capture import Frame
from snipdraw.core.geometry import ScreenGeometry
from snipdraw.ui.overlay.window import OverlayWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_frame(width: int = 400, height: int = 300) -> Frame:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#304050"))
    return Frame(
        image=image,
        screen=ScreenGeometry("fake", 0, 0, width, height, 1.0),
        method="fake",
        captured_at=0.0,
    )


def paint_into(window: OverlayWindow) -> None:
    target = QImage(window.width(), window.height(), QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(target)
    try:
        window._paint_scene(painter)
    finally:
        painter.end()


def test_paint_scene_handles_zero_size_selection(app):
    """鼠标刚按下时选区是零尺寸（falsy 但不是 None），这一帧必须能画完。"""
    window = OverlayWindow(make_frame())
    window.resize(400, 300)
    point = QPointF(120, 90)
    window._selection_phys = QRectF(point, point)
    paint_into(window)          # 旧代码在这里 TypeError: setClipRect(NoneType)
    window.deleteLater()


@pytest.mark.parametrize(
    "rect",
    [QRectF(20, 20, 200, 120), QRectF(0, 0, 400, 300), QRectF(399, 299, 1, 1)],
)
def test_paint_scene_handles_normal_selection(app, rect):
    window = OverlayWindow(make_frame())
    window.resize(400, 300)
    window.set_preview(rect, QPointF(60, 40))
    paint_into(window)
    window.deleteLater()


def test_paint_scene_handles_no_selection(app):
    window = OverlayWindow(make_frame())
    window.resize(400, 300)
    window._selection_phys = None
    paint_into(window)
    window.deleteLater()
