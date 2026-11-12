"""贴图窗口测试：逻辑尺寸、缩放锚点、拖动、上限。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication

from snipdraw.ui.pin.controller import PinController
from snipdraw.ui.pin.window import MAX_ZOOM, MIN_ZOOM, PinWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_image(w: int = 400, h: int = 200) -> QImage:
    image = QImage(w, h, QImage.Format.Format_RGB32)
    image.fill(QColor("#3366cc"))
    return image


def test_logical_size_uses_source_scale(app):
    pin = PinWindow(make_image(400, 200), source_scale=2.0, position=QPointF(10, 10))
    assert (pin.width(), pin.height()) == (200, 100)
    pin.deleteLater()


def test_zoom_scales_geometry(app):
    pin = PinWindow(make_image(400, 200), source_scale=2.0, position=QPointF(10, 10))
    pin.set_zoom(2.0)
    assert (pin.width(), pin.height()) == (400, 200)
    pin.set_zoom(10.0)
    assert pin.zoom == MAX_ZOOM
    pin.set_zoom(0.0)
    assert pin.zoom == MIN_ZOOM
    pin.deleteLater()


def test_zoom_keeps_anchor_point(app):
    pin = PinWindow(make_image(400, 200), source_scale=1.0, position=QPointF(100, 100))
    anchor = QPointF(200, 150)   # 窗口内 100/50 的位置
    ratio_x = (anchor.x() - pin.x()) / pin.width()
    ratio_y = (anchor.y() - pin.y()) / pin.height()
    before = (ratio_x, ratio_y)

    pin.set_zoom(2.0, anchor)
    after = (
        (anchor.x() - pin.x()) / pin.width(),
        (anchor.y() - pin.y()) / pin.height(),
    )
    # 缩放后同一个屏幕点仍在窗口内的同一相对位置（允许 1px 取整误差）
    assert abs(after[0] - before[0]) < 0.02
    assert abs(after[1] - before[1]) < 0.02
    pin.deleteLater()


def test_drag_moves_window(app):
    pin = PinWindow(make_image(), position=QPointF(50, 50))
    pin.show()

    def send(kind, point, buttons):
        QApplication.sendEvent(
            pin,
            QMouseEvent(kind, point, point, Qt.MouseButton.LeftButton, buttons,
                        Qt.KeyboardModifier.NoModifier),
        )

    send(QEvent.Type.MouseButtonPress, QPointF(80, 80), Qt.MouseButton.LeftButton)
    send(QEvent.Type.MouseMove, QPointF(140, 160), Qt.MouseButton.LeftButton)
    send(QEvent.Type.MouseButtonRelease, QPointF(140, 160), Qt.MouseButton.NoButton)
    assert (pin.x(), pin.y()) == (110, 130)
    pin.deleteLater()


def test_close_emits_signal(app):
    pin = PinWindow(make_image(), position=QPointF(10, 10))
    closed: list[object] = []
    pin.closed.connect(closed.append)
    pin.close_pin()
    assert closed == [pin]
    pin.deleteLater()


def test_controller_enforces_limit(app):
    controller = PinController(limit=2)
    for _ in range(3):
        controller.create(make_image(), 1.0, QPointF(40, 40))
    assert controller.count == 2
    controller.close_all()
    assert controller.count == 0


def test_controller_centered_fits_large_image(app):
    controller = PinController(limit=5)
    screen = QApplication.primaryScreen().availableGeometry()
    image = make_image(screen.width() * 3, screen.height() * 3)
    pin = controller.create_centered(image, 1.0)
    assert pin.zoom < 1.0
    assert pin.width() <= screen.width() and pin.height() <= screen.height()
    controller.close_all()
