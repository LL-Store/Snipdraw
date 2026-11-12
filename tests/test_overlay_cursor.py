"""光标策略：十字只属于框选阶段，进标注态要还给用户箭头。

Windows 上一直停在十字（macOS 上看着正常），原因是 enter_annotating() 与
toolChanged 都把光标写死成 CrossCursor，从来没恢复过。
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from snipdraw.core.capture import Frame
from snipdraw.core.geometry import ScreenGeometry
from snipdraw.ui.overlay.window import OverlayWindow


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


def make_window(app) -> OverlayWindow:
    window = OverlayWindow(make_frame())
    window.show()
    window.set_preview(
        __import__("PySide6.QtCore", fromlist=["QRectF"]).QRectF(100, 80, 300, 220),
        QPointF(300, 200),
    )
    return window


def test_crosshair_while_selecting(app):
    window = OverlayWindow(make_frame())
    window.show()
    assert window.cursor().shape() == Qt.CursorShape.CrossCursor
    window.deleteLater()


def test_arrow_after_entering_annotating(app):
    window = make_window(app)
    window.enter_annotating()
    assert window.mode.name == "ANNOTATING"
    assert window.cursor().shape() == Qt.CursorShape.ArrowCursor
    window.deleteLater()


def test_text_tool_gets_ibeam_cursor(app):
    window = make_window(app)
    window.enter_annotating()
    window._toolbar.select_tool("text")
    assert window.cursor().shape() == Qt.CursorShape.IBeamCursor
    window.deleteLater()


def test_switching_back_to_drawing_tool_restores_arrow(app):
    window = make_window(app)
    window.enter_annotating()
    window._toolbar.select_tool("text")
    window._toolbar.select_tool("pen")
    assert window.cursor().shape() == Qt.CursorShape.ArrowCursor
    window.deleteLater()
