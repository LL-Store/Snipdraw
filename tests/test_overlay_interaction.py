"""交互链路测试：拖框 → 进标注态 → 画图元 → 合成出图。

用 offscreen 平台直接给窗口发鼠标事件，不依赖真实屏幕。
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication, QSpinBox

from snipdraw.core.capture import Frame
from snipdraw.core.geometry import ScreenGeometry
from snipdraw.ui.overlay.shapes import Style
from snipdraw.ui.overlay.window import Mode, OverlayWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_frame() -> Frame:
    image = QImage(800, 600, QImage.Format.Format_RGB32)
    image.fill(QColor("#304050"))
    return Frame(
        image=image,
        screen=ScreenGeometry("fake", 0, 0, 800, 600, 1.0),
        method="fake",
        captured_at=0.0,
    )


def send(window: OverlayWindow, kind: QEvent.Type, x: float, y: float, buttons=Qt.MouseButton.LeftButton):
    event = QMouseEvent(
        kind,
        QPointF(x, y),
        QPointF(x, y),
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(window, event)


def drag(window: OverlayWindow, start: QPointF, end: QPointF) -> None:
    send(window, QEvent.Type.MouseButtonPress, start.x(), start.y())
    send(window, QEvent.Type.MouseMove, (start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
    send(window, QEvent.Type.MouseMove, end.x(), end.y())
    send(window, QEvent.Type.MouseButtonRelease, end.x(), end.y(), Qt.MouseButton.NoButton)


def test_drag_creates_selection_and_enters_annotating(app):
    window = OverlayWindow(make_frame())
    window.show()
    assert window.mode == Mode.SELECTING
    drag(window, QPointF(100, 80), QPointF(400, 300))
    assert window.mode == Mode.ANNOTATING
    sel = window._selection_phys
    assert sel is not None
    assert round(sel.width()) == 300 and round(sel.height()) == 220
    assert window._toolbar is not None
    window.deleteLater()


def test_drag_inside_selection_draws_shape(app):
    window = OverlayWindow(make_frame())
    window.show()
    drag(window, QPointF(100, 80), QPointF(400, 300))
    assert len(window.model.shapes) == 0
    drag(window, QPointF(150, 120), QPointF(280, 220))
    assert len(window.model.shapes) == 1
    assert window.model.shapes[0].kind == "rect"
    image = window.composed()
    assert (image.width(), image.height()) == (300, 220)
    window.deleteLater()


def test_empty_drag_resets_selection(app):
    window = OverlayWindow(make_frame())
    window.show()
    drag(window, QPointF(100, 80), QPointF(101, 81))
    assert window._selection_phys is None
    assert window.mode == Mode.SELECTING
    window.deleteLater()


def test_handle_drag_resizes_selection(app):
    window = OverlayWindow(make_frame())
    window.show()
    drag(window, QPointF(100, 80), QPointF(400, 300))
    # 右下角手柄在 (400, 300)，往外拖 50
    drag(window, QPointF(400, 300), QPointF(450, 350))
    sel = window._selection_phys
    assert sel is not None
    assert round(sel.width()) == 350 and round(sel.height()) == 270
    window.deleteLater()


def test_undo_redo_via_keyboard(app):
    window = OverlayWindow(make_frame())
    window.show()
    drag(window, QPointF(100, 80), QPointF(400, 300))
    drag(window, QPointF(150, 120), QPointF(280, 220))
    assert len(window.model.shapes) == 1
    window.model.undo()
    assert len(window.model.shapes) == 0
    window.model.redo()
    assert len(window.model.shapes) == 1
    window.deleteLater()


def test_escape_emits_canceled(app):
    window = OverlayWindow(make_frame())
    window.show()
    fired: list[bool] = []
    window.canceled.connect(lambda: fired.append(True))
    send(window, QEvent.Type.MouseButtonPress, 100, 80)
    send(window, QEvent.Type.MouseButtonRelease, 300, 200, Qt.MouseButton.NoButton)
    window.keyPressEvent(
        __import__("PySide6.QtGui", fromlist=["QKeyEvent"]).QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
    )
    assert fired == [True]
    window.deleteLater()


def test_pin_button_reports_position_and_scale(app):
    """贴图要知道原始全局位置与缩放，否则贴出来位置/尺寸都不对。"""
    window = OverlayWindow(make_frame())
    window.show()
    drag(window, QPointF(100, 80), QPointF(400, 300))
    pin = window._toolbar
    assert pin is not None
    captured: list[tuple] = []
    window.finished.connect(lambda image, action, scale, pos: captured.append((action, scale, pos)))
    pin.pinRequested.emit()
    assert len(captured) == 1
    action, scale, pos = captured[0]
    assert action == "pin"
    assert scale == 1.0
    # 选区左上角 (100,80) 在 1.0 缩放下就是全局 (100,80)
    assert (round(pos.x()), round(pos.y())) == (100, 80)
    window.deleteLater()


def test_compose_matches_toolbar_color_and_default_width(app):
    """工具栏切色生效，移除线宽控件后仍使用默认线宽。"""
    window = OverlayWindow(make_frame())
    window.show()
    drag(window, QPointF(100, 80), QPointF(400, 300))
    toolbar = window._toolbar
    assert toolbar is not None
    toolbar._select_color("#00ff00")
    window._sync_style()
    assert toolbar.findChildren(QSpinBox) == []
    drag(window, QPointF(150, 120), QPointF(280, 220))
    shape = window.model.shapes[0]
    assert shape.style.color.name() == "#00ff00"
    assert shape.style.width == 3.0
    window.deleteLater()
