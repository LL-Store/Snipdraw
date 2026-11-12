"""贴图窗口：把一张图钉在屏幕上。

交互对齐 Snipaste：
- 左键拖动移动
- 滚轮缩放（以光标为锚点，不会跳）
- Ctrl + 滚轮调透明度
- 右键菜单：复制 / 保存 / 1:1 / 透明度 / 关闭 / 关闭全部
- 双击或 Esc 关闭

窗口本身是 Frameless + StaysOnTop + Tool，在 macOS 上同样需要抬层级，
否则会被 Dock 和菜单栏压住（跟 overlay 是同一套处理）。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QActionGroup, QColor, QGuiApplication, QImage, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

MIN_ZOOM = 0.2
MAX_ZOOM = 4.0
ZOOM_STEP = 1.12
OPACITY_STEPS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.4)


class PinWindow(QWidget):
    closed = Signal(object)          # self
    copyRequested = Signal(object)   # QImage
    saveRequested = Signal(object)   # QImage
    closeAllRequested = Signal()

    def __init__(
        self,
        image: QImage,
        source_scale: float = 1.0,
        position: QPointF | None = None,
        parent: QWidget | None = None,
    ) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        super().__init__(parent, flags)
        self.image = image
        self._scale = max(0.1, float(source_scale))
        self._zoom = 1.0
        # 物理像素 → 逻辑像素：贴图刚出现时应该跟被截的原始区域一样大
        self._base_w = image.width() / self._scale
        self._base_h = image.height() / self._scale

        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._drag_offset: QPointF | None = None
        self._apply_size()
        if position is None:
            self.center_on_screen()
        else:
            self.move_to(QPointF(position))

    # ---------------- 尺寸与位置 --------------

    def _apply_size(self) -> None:
        self.resize(max(1, int(round(self._base_w * self._zoom))), max(1, int(round(self._base_h * self._zoom))))

    def center_on_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(
            int(area.center().x() - self.width() / 2),
            int(area.center().y() - self.height() / 2),
        )

    def move_to(self, position: QPointF) -> None:
        """放到指定位置，并保证整块贴图没跑出所在屏幕。"""
        screen = QGuiApplication.screenAt(position.toPoint()) or QGuiApplication.primaryScreen()
        x = int(position.x())
        y = int(position.y())
        if screen is not None:
            area = screen.availableGeometry()
            x = max(area.left(), min(x, area.right() - self.width() + 1))
            y = max(area.top(), min(y, area.bottom() - self.height() + 1))
        self.move(x, y)

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, zoom: float, anchor_global: QPointF | None = None) -> None:
        old = self._zoom
        new = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if abs(new - old) < 1e-6:
            return

        anchor = anchor_global or QPointF(
            self.x() + self.width() / 2, self.y() + self.height() / 2
        )
        # 记录锚点在窗口内的相对位置，缩放后把同一个点挪回原处
        ratio_x = (anchor.x() - self.x()) / max(1, self.width())
        ratio_y = (anchor.y() - self.y()) / max(1, self.height())

        self._zoom = new
        self._apply_size()

        target = QPointF(anchor.x() - ratio_x * self.width(), anchor.y() - ratio_y * self.height())
        screen = QGuiApplication.screenAt(anchor.toPoint()) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            target.setX(max(area.left(), min(target.x(), area.right() - self.width() + 1)))
            target.setY(max(area.top(), min(target.y(), area.bottom() - self.height() + 1)))
        self.move(int(target.x()), int(target.y()))
        self.update()

    # ---------------- 显示 --------------

    def show_on_top(self) -> None:
        self.show()
        self.raise_()
        from ...platform.macos_window import set_floating

        # 贴图用浮动层就够（要盖住普通窗口），不该抬到菜单栏之上抢位置
        set_floating(self)
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def close_pin(self) -> None:
        self.hide()
        self.closed.emit(self)

    # ---------------- 事件 --------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawImage(self.rect(), self.image)
        painter.setPen(QPen(QColor(0, 0, 0, 90), 1.0))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    def mousePressEvent(self, event) -> None:
        self.activateWindow()
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() == Qt.MouseButton.RightButton:
            self._show_menu(event.globalPosition().toPoint())
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition() - QPointF(self.x(), self.y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is None:
            return
        delta = event.globalPosition() - self._drag_offset
        self.move(int(delta.x()), int(delta.y()))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.close_pin()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            step = 0.1 if delta > 0 else -0.1
            self.setWindowOpacity(max(0.15, min(1.0, self.windowOpacity() + step)))
            return
        factor = ZOOM_STEP if delta > 0 else 1.0 / ZOOM_STEP
        self.set_zoom(self._zoom * factor, event.globalPosition())

    def keyPressEvent(self, event) -> None:
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_Escape:
            self.close_pin()
            return
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            if key == Qt.Key.Key_C:
                self.copyRequested.emit(self.image)
                return
            if key == Qt.Key.Key_S:
                self.saveRequested.emit(self.image)
                return
        super().keyPressEvent(event)

    # ---------------- 右键菜单 --------------

    def _show_menu(self, global_point) -> None:
        menu = QMenu(self)
        menu.addAction("复制", lambda: self.copyRequested.emit(self.image))
        menu.addAction("保存", lambda: self.saveRequested.emit(self.image))
        menu.addSeparator()

        menu.addAction("1 : 1", lambda: self.set_zoom(1.0))
        menu.addAction("放大", lambda: self.set_zoom(self._zoom * ZOOM_STEP))
        menu.addAction("缩小", lambda: self.set_zoom(self._zoom / ZOOM_STEP))

        opacity_menu = menu.addMenu("透明度")
        group = QActionGroup(opacity_menu)
        group.setExclusive(True)
        current = self.windowOpacity()
        for value in OPACITY_STEPS:
            action = opacity_menu.addAction(f"{int(value * 100)}%")
            action.setCheckable(True)
            action.setChecked(math.isclose(current, value, abs_tol=0.03))
            action.triggered.connect(lambda _=False, v=value: self.setWindowOpacity(v))
            group.addAction(action)

        menu.addSeparator()
        menu.addAction("关闭", self.close_pin)
        menu.addAction("关闭全部贴图", self.closeAllRequested.emit)
        menu.exec(global_point)
