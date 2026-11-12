"""overlay 生命周期：截屏 → 每屏一个窗口 → 选区/标注完成或取消。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

from ...core.capture import CaptureError, CaptureService, Frame
from .window import OverlayWindow


class OverlayController(QObject):
    finished = Signal(object, str, float, object)   # QImage, action, scale, 全局逻辑坐标
    canceled = Signal()
    failed = Signal(str)

    def __init__(
        self,
        color: QColor | None = None,
        width: float = 3.0,
        font_size: int = 16,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._windows: list[OverlayWindow] = []
        self._busy = False
        self._color = QColor(color or "#ff3b30")
        self._width = float(width)
        self._font_size = int(font_size)

    @property
    def active(self) -> bool:
        # 取景过程中也算 active：否则第二次热键会在 _windows 还是空的时候重入，
        # 结果叠出两个全屏 overlay（用户看到的是"卡住"，Esc 又要删两遍）
        return self._busy or bool(self._windows)

    def start(self) -> bool:
        if self._busy or self._windows:
            return False
        self._busy = True
        try:
            self.close_all()
            service = CaptureService()
            try:
                frames = service.capture_all()
            except CaptureError as error:
                self.failed.emit(str(error))
                return False

            for frame in frames:
                window = OverlayWindow(frame, self._color, self._width, self._font_size)
                window.finished.connect(self._on_finished)
                window.canceled.connect(self._on_canceled)
                self._windows.append(window)

            # 必须全部建好再统一显示，避免第一块屏的 overlay 被第二块屏的截屏拍到
            for window in self._windows:
                window.show_on_screen()
            return True
        finally:
            self._busy = False

    def focus_active(self) -> bool:
        """已在截图时又按了热键：把现有 overlay 顶上来，别让用户以为程序卡死。"""
        if not self._windows:
            return False
        for window in self._windows:
            window.show()
            window.raise_()
            window.activateWindow()
        return True

    def close_all(self) -> None:
        for window in self._windows:
            window.hide()
            window.close()
            window.deleteLater()
        self._windows.clear()

    def _on_finished(self, image, action: str, scale: float, position) -> None:
        self.close_all()
        self.finished.emit(image, action, scale, position)

    def _on_canceled(self) -> None:
        self.close_all()
        self.canceled.emit()
