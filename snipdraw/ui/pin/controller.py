"""贴图管理：数量上限、级联摆放、统一关闭。"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, Signal
from PySide6.QtGui import QGuiApplication, QImage

from .window import PinWindow


class PinController(QObject):
    copyRequested = Signal(object)
    saveRequested = Signal(object)
    countChanged = Signal(int)
    empty = Signal()

    def __init__(self, limit: int = 20, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._limit = max(1, int(limit))
        self._pins: list[PinWindow] = []

    @property
    def count(self) -> int:
        return len(self._pins)

    def set_limit(self, limit: int) -> None:
        self._limit = max(1, int(limit))
        self._trim()

    def create(
        self,
        image: QImage,
        source_scale: float = 1.0,
        position: QPointF | None = None,
    ) -> PinWindow:
        if image is None or image.isNull():
            raise ValueError("贴图图片为空")

        pin = PinWindow(image, source_scale, position)
        pin.closed.connect(self._on_closed)
        pin.copyRequested.connect(self.copyRequested.emit)
        pin.saveRequested.connect(self.saveRequested.emit)
        pin.closeAllRequested.connect(self.close_all)
        self._pins.append(pin)
        self._trim()
        pin.show_on_top()
        self.countChanged.emit(self.count)
        return pin

    def create_centered(self, image: QImage, source_scale: float = 1.0) -> PinWindow:
        """没有源位置时（比如从剪贴板贴图），摆在主屏中间。"""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return self.create(image, source_scale)
        area = screen.availableGeometry()
        logical_w = image.width() / max(0.1, source_scale)
        logical_h = image.height() / max(0.1, source_scale)
        # 大图别顶出屏幕，先缩到可用区域的 80%
        scale_fit = min(1.0, area.width() * 0.8 / logical_w, area.height() * 0.8 / logical_h)
        position = QPointF(
            area.center().x() - logical_w * scale_fit / 2,
            area.center().y() - logical_h * scale_fit / 2,
        )
        pin = self.create(image, source_scale, position)
        if scale_fit < 1.0:
            pin.set_zoom(scale_fit)
        return pin

    def close_all(self) -> None:
        for pin in list(self._pins):
            pin.close_pin()

    def _trim(self) -> None:
        # 超上限就关最早的，避免用户贴一百张把屏幕糊住
        while len(self._pins) > self._limit:
            oldest = self._pins[0]
            oldest.close_pin()

    def _on_closed(self, pin: PinWindow) -> None:
        if pin in self._pins:
            self._pins.remove(pin)
        pin.deleteLater()
        self.countChanged.emit(self.count)
        if not self._pins:
            self.empty.emit()
