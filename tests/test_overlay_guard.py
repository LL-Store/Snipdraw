"""overlay 的重入与幂等：F1 连按时不能叠出两个全屏窗口，也不能重复销毁。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from snipdraw.core.capture import CaptureService, Frame
from snipdraw.core.geometry import ScreenGeometry
from snipdraw.ui.overlay.controller import OverlayController
from snipdraw.ui.overlay.window import OverlayWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def make_frame() -> Frame:
    image = QImage(400, 300, QImage.Format.Format_RGB32)
    image.fill(QColor("#304050"))
    return Frame(
        image=image,
        screen=ScreenGeometry("fake", 0, 0, 400, 300, 1.0),
        method="fake",
        captured_at=0.0,
    )


def test_second_start_during_capture_is_ignored(app, monkeypatch):
    """取景过程中再按一次 F1：不允许再来一轮 start()，否则会叠两个 overlay。"""
    controller = OverlayController()
    calls: list[int] = []
    second_results: list[bool] = []

    def capture_then_reenter(self):
        calls.append(1)
        if len(calls) == 1:
            second_results.append(controller.start())   # 模拟热键在取景时重入
        return [make_frame()]

    monkeypatch.setattr(CaptureService, "capture_all", capture_then_reenter)

    assert controller.start() is True
    assert calls == [1]
    assert second_results == [False]
    assert len(controller._windows) == 1
    controller.close_all()


def test_active_is_true_while_capturing(app, monkeypatch):
    """取景还没结束就要算 active，热键守卫才能挡住第二次。"""
    controller = OverlayController()
    seen: list[bool] = []
    original = CaptureService.capture_all

    def capture_then_probe(self):
        seen.append(controller.active)
        return original(self)

    monkeypatch.setattr(CaptureService, "capture_all", capture_then_probe)
    controller.start()
    assert seen == [True]
    controller.close_all()


def test_cancel_emits_only_once(app):
    window = OverlayWindow(make_frame())
    window.set_preview(QRectF(20, 20, 120, 80), QPointF(60, 40))
    hits: list[bool] = []
    window.canceled.connect(lambda: hits.append(True))
    window._abort()
    window._abort()
    assert hits == [True]
    window.deleteLater()


def test_finish_emits_only_once(app):
    window = OverlayWindow(make_frame())
    window.set_preview(QRectF(20, 20, 120, 80), QPointF(60, 40))
    finished: list[str] = []
    window.finished.connect(lambda image, action, scale, pos: finished.append(action))
    window._emit_output("done")
    window._emit_output("done")
    assert finished == ["done"]
    window.deleteLater()
