"""合成导出测试：不依赖真实屏幕，用手造的 Frame 验证出图像素。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, QRect, QRectF
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from snipdraw.core.capture import Frame
from snipdraw.core.geometry import ScreenGeometry
from snipdraw.ui.overlay.shapes import (
    BadgeShape,
    EllipseShape,
    MosaicShape,
    PenShape,
    RectShape,
    Style,
    TextShape,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_frame() -> Frame:
    image = QImage(400, 300, QImage.Format.Format_RGB32)
    image.fill(QColor("#204060"))
    screen = ScreenGeometry("fake", 0, 0, 400, 300, 1.0)
    return Frame(image=image, screen=screen, method="fake", captured_at=0.0)


def test_compose_crops_to_selection(app):
    from snipdraw.ui.overlay.window import OverlayWindow

    window = OverlayWindow(make_frame())
    window.set_preview(QRectF(100, 50, 200, 150), QPointF(150, 100))
    image = window.composed()
    assert image.width() == 200
    assert image.height() == 150
    assert image.pixelColor(10, 10).name() == "#204060"
    window.deleteLater()


def test_compose_draws_shapes(app):
    from snipdraw.ui.overlay.window import OverlayWindow

    window = OverlayWindow(make_frame())
    window.set_preview(QRectF(100, 50, 200, 150), QPointF(150, 100))
    window.model.add(RectShape(QRectF(110, 60, 100, 80), Style(QColor("#ff0000"), 4.0, 16)))
    image = window.composed()
    # 矩形上边线上应该出现红色（取靠近边框内侧的像素）
    sample = image.pixelColor(60, 11)
    assert sample.red() > 200 and sample.green() < 80
    window.deleteLater()


def test_compose_mosaic_reads_base_image(app):
    from snipdraw.ui.overlay.window import OverlayWindow

    frame = make_frame()
    window = OverlayWindow(frame)
    window.set_preview(QRectF(100, 50, 200, 150), QPointF(150, 100))
    window.model.add(MosaicShape(QRectF(150, 80, 80, 60), Style(QColor("#000000"), 3.0, 16), 8.0))
    image = window.composed()
    # 马赛克区域仍然取自原图，不应变成纯黑
    sample = image.pixelColor(80, 50)
    assert sample.blue() > 50
    window.deleteLater()


def test_badge_and_text_do_not_crash(app):
    from snipdraw.ui.overlay.window import OverlayWindow

    window = OverlayWindow(make_frame())
    window.set_preview(QRectF(100, 50, 200, 150), QPointF(150, 100))
    window.model.add(BadgeShape(QPointF(180, 120), 1, Style(QColor("#00ff00"), 3.0, 20)))
    window.model.add(TextShape(QPointF(120, 90), "测试文本", Style(QColor("#ffffff"), 3.0, 18)))
    window.model.add(EllipseShape(QRectF(130, 100, 90, 70), Style(QColor("#ffff00"), 3.0, 16)))
    image = window.composed()
    assert image.width() == 200 and image.height() == 150
    window.deleteLater()


def test_badge_does_not_fill_following_pen_stroke(app):
    from snipdraw.ui.overlay.window import OverlayWindow

    window = OverlayWindow(make_frame())
    window.set_preview(QRectF(0, 0, 400, 300), QPointF(150, 100))
    style = Style(QColor("#ff0000"), 3.0, 20)
    window.model.add(BadgeShape(QPointF(300, 200), 1, style))
    window.model.add(
        PenShape(
            [QPointF(100, 100), QPointF(160, 100), QPointF(100, 160)],
            style,
        )
    )

    image = window.composed()
    assert image.pixelColor(110, 110).name() == "#204060"
    window.deleteLater()


def test_undo_removes_shape(app):
    from snipdraw.ui.overlay.window import OverlayWindow

    window = OverlayWindow(make_frame())
    window.model.add(BadgeShape(QPointF(180, 120), 1, Style(QColor("#00ff00"), 3.0, 20)))
    assert len(window.model.shapes) == 1
    window.model.undo()
    assert len(window.model.shapes) == 0
    window.model.redo()
    assert len(window.model.shapes) == 1
    window.model.clear()
    assert len(window.model.shapes) == 0
    window.model.undo()
    assert len(window.model.shapes) == 1
    window.deleteLater()
