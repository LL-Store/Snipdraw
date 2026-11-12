"""截屏实现：两套后端，一个接口。

- GrabWindowCapturer：QScreen.grabWindow(0)，同步、最快，Win / X11 走这条。
- MediaCapturer：QScreenCapture + QVideoSink，取首帧即停，macOS 走这条
  （Qt 内部走 ScreenCaptureKit，兼容 macOS 14+ 对 CGWindowList 的弃用）。
- 运行时不预设平台：先 grabWindow，拿到空图再降级到 MediaCapturer，
  并把实际用的方式记在 Frame 上，便于排查“截出黑图”一类问题。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QScreen

from .geometry import ScreenGeometry, axis_scale
from .screen import geometry_of


@dataclass
class Frame:
    """一帧截图 + 它来自哪块屏 + 图像与逻辑坐标的比例关系。"""

    image: QImage
    screen: ScreenGeometry
    method: str
    captured_at: float

    @property
    def size(self) -> tuple[int, int]:
        return self.image.width(), self.image.height()

    @property
    def scale_x(self) -> float:
        return axis_scale(self.screen.width, self.image.width())

    @property
    def scale_y(self) -> float:
        return axis_scale(self.screen.height, self.image.height())

    def physical_to_local(self, px: float, py: float) -> tuple[float, float]:
        return px / self.scale_x, py / self.scale_y

    def local_to_physical(self, lx: float, ly: float) -> tuple[float, float]:
        return lx * self.scale_x, ly * self.scale_y


class CaptureError(RuntimeError):
    pass


class GrabWindowCapturer:
    name = "grabWindow"

    def grab(self, qscreen: QScreen) -> Frame | None:
        pixmap = qscreen.grabWindow(0)
        if pixmap.isNull():
            return None
        image = pixmap.toImage()
        if image.isNull():
            return None
        return Frame(
            image=image,
            screen=geometry_of(qscreen),
            method=self.name,
            captured_at=time.monotonic(),
        )


class MediaCapturer:
    """用 QtMultimedia 抓首帧，超时返回 None。"""

    name = "QScreenCapture"

    def __init__(self, timeout_ms: int = 1500) -> None:
        self.timeout_ms = timeout_ms

    def grab(self, qscreen: QScreen) -> Frame | None:
        from PySide6.QtMultimedia import (
            QMediaCaptureSession,
            QScreenCapture,
            QVideoSink,
        )

        capture = QScreenCapture()
        capture.setScreen(qscreen)
        session = QMediaCaptureSession()
        session.setScreenCapture(capture)
        sink = QVideoSink()
        session.setVideoSink(sink)

        holder: dict[str, QImage] = {}
        loop = QEventLoop()

        def on_frame(frame) -> None:
            if "image" in holder:
                return
            image = frame.toImage()
            if image.isNull():
                return
            holder["image"] = image
            QTimer.singleShot(0, loop.quit)

        sink.videoFrameChanged.connect(on_frame)
        capture.setActive(True)
        QTimer.singleShot(self.timeout_ms, loop.quit)
        loop.exec()
        capture.setActive(False)
        try:
            sink.videoFrameChanged.disconnect(on_frame)
        except (RuntimeError, TypeError):
            pass

        image = holder.get("image")
        if image is None:
            return None
        return Frame(
            image=image,
            screen=geometry_of(qscreen),
            method=self.name,
            captured_at=time.monotonic(),
        )


def looks_blank(image: QImage, samples: int = 5) -> bool:
    """粗判是否整块同色（多半是权限没给 / 受保护内容）。

    只用来提示，不用来自动重试——真有一块纯色桌面时不该误判成失败。
    """
    if image.isNull():
        return True
    step_x = max(image.width() // (samples + 1), 1)
    step_y = max(image.height() // (samples + 1), 1)
    first = image.pixelColor(step_x, step_y).rgba()
    for ix in range(1, samples + 1):
        for iy in range(1, samples + 1):
            if image.pixelColor(ix * step_x, iy * step_y).rgba() != first:
                return False
    return True


class CaptureService:
    def __init__(self) -> None:
        self._grab = GrabWindowCapturer()
        self._media = MediaCapturer()
        self.notes: list[str] = []

    def capture_one(self, qscreen: QScreen) -> Frame:
        # macOS 没给「屏幕录制」时，第一后端拿不到窗口、兜底又会让系统再弹一次权限框。
        # 所以先预检：没权限直接报清楚，不发起任何截屏调用。
        from ..platform.macos_permission import screen_capture_granted

        if not screen_capture_granted():
            raise CaptureError(
                "缺少 macOS「屏幕录制」权限：系统设置 → 隐私与安全性 → 屏幕录制，"
                "勾选后重启 Snipdraw 再截图。"
            )

        frame = self._grab.grab(qscreen)
        if frame is None:
            self.notes.append(f"{qscreen.name()}: grabWindow 返回空图，改用 QScreenCapture")
            try:
                frame = self._media.grab(qscreen)
            except Exception as exc:  # 精简打包时可能没带 QtMultimedia，不能让兜底反而崩掉
                self.notes.append(f"{qscreen.name()}: QScreenCapture 不可用（{exc}）")
                frame = None
        if frame is None:
            raise CaptureError(
                "截屏失败：两个后端都拿不到图像。"
                "macOS 请确认已授予“屏幕录制”权限并重启应用；"
                "Linux 请确认当前是 X11 会话。"
            )
        return frame

    def capture_all(self) -> list[Frame]:
        self.notes.clear()
        frames: list[Frame] = []
        for qscreen in QGuiApplication.screens():
            frames.append(self.capture_one(qscreen))
        return frames
