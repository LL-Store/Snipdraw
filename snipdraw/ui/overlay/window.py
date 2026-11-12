"""单屏 overlay：冻结帧 → 框选 → 标注 → 出图。

状态机：
- SELECTING：可新建选区、拖动手柄改变大小、拖动整块移动
- ANNOTATING：选区确认后进入，工具栏出现，画图元
两个状态下都允许拖手柄微调选区，方便“框歪了一点”。
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QRegion
from PySide6.QtWidgets import QLineEdit, QToolButton, QWidget

from ...core.capture import Frame
from .model import AnnotationModel
from .shapes import (
    ArrowShape,
    BadgeShape,
    EllipseShape,
    HighlightShape,
    MosaicShape,
    PenShape,
    RectShape,
    Shape,
    Style,
    TextShape,
)
from .toolbar import Toolbar

DIM_ALPHA = 115
ACCENT = QColor("#2f7cf6")
HANDLE_SIZE = 7.0
HANDLE_TOLERANCE = 7.0
MIN_SELECTION = 4.0
MAG_SIZE = 132.0
MAG_SOURCE = 22.0
MAG_TEXT_H = 26.0

HANDLE_ORDER = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 2), (0, 2), (0, 1)]


class Mode(str, Enum):
    SELECTING = "selecting"
    ANNOTATING = "annotating"


class OverlayWindow(QWidget):
    finished = Signal(object, str, float, object)   # QImage, action, scale, 全局逻辑坐标
    canceled = Signal()

    def __init__(
        self,
        frame: Frame,
        color: QColor | None = None,
        width: float = 3.0,
        font_size: int = 16,
    ) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        super().__init__(None, flags)
        self.frame = frame
        self.model = AnnotationModel(self)
        self.model.changed.connect(self._on_model_changed)

        # macOS 上 Qt::Tool 窗口在应用失焦时会被系统隐藏，必须显式关掉
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.style = Style(QColor(color or "#ff3b30"), float(width), int(font_size))
        self._mode = Mode.SELECTING
        self._anchor_phys: QPointF | None = None
        self._cursor_phys: QPointF | None = None
        self._selection_phys: QRectF | None = None
        self._dragging = False
        self._selected = False
        self._resize_handle: int | None = None
        self._move_origin: QPointF | None = None
        self._original_selection: QRectF | None = None
        self._draft: Shape | None = None
        self._toolbar: Toolbar | None = None
        self._text_edit: QLineEdit | None = None
        self._text_pos: QPointF | None = None
        self._done = False

    # ---------------- 位置与状态 ----------------

    def show_on_screen(self) -> None:
        screen = self.frame.screen
        self.setGeometry(screen.x, screen.y, screen.width, screen.height)
        self.show()
        self.raise_()
        from ...platform.macos_window import raise_above_system

        raise_above_system(self)
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.update()

    def set_preview(self, rect_phys: QRectF, cursor_phys: QPointF) -> None:
        """demo 用：摆好选区与光标，直接看渲染结果。"""
        self._selection_phys = rect_phys
        self._cursor_phys = cursor_phys
        self._selected = True
        self._dragging = False
        self.update()

    def enter_annotating(self) -> None:
        if self._selection_phys is None:
            return
        self._mode = Mode.ANNOTATING
        self._selected = True
        self._ensure_toolbar()
        self._place_toolbar()
        self._refresh_cursor()
        self.update()
        self.setFocus()

    def _refresh_cursor(self) -> None:
        """十字只属于框选；进标注态还给箭头，文字工具用 I 形。

        Windows 上编辑器一直停在十字，就是因为这里之前把 CrossCursor 写死在
        enter_annotating / toolChanged 里，从来没有恢复过。
        """
        if self._mode == Mode.SELECTING:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        tool = self._toolbar.current_tool() if self._toolbar is not None else ""
        self.setCursor(Qt.CursorShape.IBeamCursor if tool == "text" else Qt.CursorShape.ArrowCursor)

    @property
    def mode(self) -> Mode:
        return self._mode

    # ---------------- 工具栏 ----------------

    def _ensure_toolbar(self) -> None:
        if self._toolbar is not None:
            return
        toolbar = Toolbar(self.style.color, self)
        toolbar.toolChanged.connect(lambda key: self._refresh_cursor())
        toolbar.styleChanged.connect(self._sync_style)
        toolbar.undoRequested.connect(self.model.undo)
        toolbar.redoRequested.connect(self.model.redo)
        toolbar.clearRequested.connect(self.model.clear)
        toolbar.copyRequested.connect(lambda: self._emit_output("copy"))
        toolbar.saveRequested.connect(lambda: self._emit_output("save"))
        toolbar.pinRequested.connect(lambda: self._emit_output("pin"))
        toolbar.doneRequested.connect(lambda: self._emit_output("done"))
        toolbar.cancelRequested.connect(self.canceled.emit)
        # 键盘快捷键统一由 overlay 处理，按钮不抢焦点
        for button in toolbar.findChildren(QToolButton):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        toolbar.adjustSize()
        toolbar.show()
        toolbar.raise_()
        self._toolbar = toolbar

    def _sync_style(self) -> None:
        if self._toolbar is None:
            return
        self.style.color = self._toolbar.color()

    def _place_toolbar(self) -> None:
        toolbar = self._toolbar
        if toolbar is None or self._selection_phys is None:
            return
        toolbar.adjustSize()
        size = toolbar.size()
        sel = self._to_widget(self._selection_phys)
        x = sel.right() - size.width()
        y = sel.bottom() + 10
        if y + size.height() > self.height() - 4:
            y = sel.top() - size.height() - 10
        if y < 4:
            y = min(self.height() - size.height() - 4, sel.bottom() - size.height() - 10)
        x = max(4.0, min(x, self.width() - size.width() - 4))
        toolbar.move(int(x), int(max(4.0, y)))

    def _on_model_changed(self) -> None:
        if self._toolbar is not None:
            self._toolbar.set_undo_state(self.model.can_undo(), self.model.can_redo())
        self.update()

    # ---------------- 坐标换算 ----------------

    def _to_phys(self, point: QPointF) -> QPointF:
        return QPointF(point.x() * self.frame.scale_x, point.y() * self.frame.scale_y)

    def _to_widget(self, rect: QRectF) -> QRectF:
        sx, sy = self.frame.scale_x, self.frame.scale_y
        return QRectF(rect.x() / sx, rect.y() / sy, rect.width() / sx, rect.height() / sy)

    def _clamp_phys(self, point: QPointF) -> QPointF:
        image = self.frame.image
        return QPointF(
            max(0.0, min(float(image.width()), point.x())),
            max(0.0, min(float(image.height()), point.y())),
        )

    def _selection_rect_phys(self) -> QRect:
        if self._selection_phys is None:
            return self.frame.image.rect()
        rect = self._selection_phys.toAlignedRect()
        return rect.intersected(self.frame.image.rect())

    # ---------------- 手柄 ----------------

    def _handle_at(self, widget_point: QPointF) -> int | None:
        if self._selection_phys is None:
            return None
        sel = self._to_widget(self._selection_phys)
        for index, (ix, iy) in enumerate(HANDLE_ORDER):
            center = self._handle_center(sel, index)
            if abs(center.x() - widget_point.x()) <= HANDLE_TOLERANCE and abs(
                center.y() - widget_point.y()
            ) <= HANDLE_TOLERANCE:
                return index
        return None

    def _resize_selection(self, handle: int, point: QPointF) -> None:
        if self._selection_phys is None:
            return
        rect = self._selection_phys
        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
        ix, iy = HANDLE_ORDER[handle]
        if ix == 0:
            left = point.x()
        elif ix == 2:
            right = point.x()
        if iy == 0:
            top = point.y()
        elif iy == 2:
            bottom = point.y()
        self._selection_phys = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
        self._place_toolbar()
        self.update()

    # ---------------- 鼠标 ----------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._abort()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        widget_pos = event.position()
        phys = self._clamp_phys(self._to_phys(widget_pos))

        handle = self._handle_at(widget_pos)
        if handle is not None:
            self._resize_handle = handle
            self._dragging = True
            return

        if self._mode == Mode.ANNOTATING and self._selection_phys is not None:
            if self._selection_phys.contains(phys):
                self._begin_shape(phys)
            return

        sel = self._selection_phys
        if sel is not None and sel.contains(phys):
            self._move_origin = phys
            self._original_selection = QRectF(sel)
            self._dragging = True
            return

        self._anchor_phys = phys
        self._cursor_phys = phys
        self._selection_phys = QRectF(phys, phys)
        self._dragging = True
        self._selected = False
        self.update()

    def mouseMoveEvent(self, event) -> None:
        widget_pos = event.position()
        phys = self._clamp_phys(self._to_phys(widget_pos))
        self._cursor_phys = phys

        if self._resize_handle is not None:
            self._resize_selection(self._resize_handle, phys)
            return

        if self._dragging and self._move_origin is not None and self._selection_phys is not None:
            delta = phys - self._move_origin
            moved = self._original_selection.translated(delta)
            image = QRectF(0, 0, self.frame.image.width(), self.frame.image.height())
            dx = 0.0
            dy = 0.0
            if moved.left() < 0:
                dx = -moved.left()
            elif moved.right() > image.right():
                dx = image.right() - moved.right()
            if moved.top() < 0:
                dy = -moved.top()
            elif moved.bottom() > image.bottom():
                dy = image.bottom() - moved.bottom()
            self._selection_phys = moved.translated(QPointF(dx, dy))
            self._place_toolbar()
            self.update()
            return

        if self._dragging and self._anchor_phys is not None:
            self._selection_phys = QRectF(self._anchor_phys, phys).normalized()
            self.update()
            return

        if self._draft is not None:
            self._update_draft(phys)
            self.update()
            return

        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._resize_handle is not None:
            self._resize_handle = None
            self._dragging = False
            self._place_toolbar()
            return

        if self._move_origin is not None:
            self._move_origin = None
            self._dragging = False
            return

        if self._draft is not None:
            self._commit_draft()
            return

        if self._dragging:
            self._dragging = False
            rect = self._selection_phys
            if rect is None or rect.width() < MIN_SELECTION or rect.height() < MIN_SELECTION:
                self._selection_phys = None
                self._selected = False
                self.update()
                return
            self._selected = True
            if self._mode == Mode.SELECTING:
                self.enter_annotating()
            else:
                self.update()

    # ---------------- 画图元 ----------------

    def _begin_shape(self, phys: QPointF) -> None:
        tool = self._toolbar.current_tool() if self._toolbar else "rect"
        self._sync_style()

        if tool == "text":
            self._start_text(phys)
            return
        if tool == "badge":
            badge = BadgeShape(phys, self.model.next_badge(), self.style.copy())
            self.model.add(badge, "添加序号")
            return

        if tool == "rect":
            self._draft = RectShape(QRectF(phys, phys), self.style.copy())
        elif tool == "ellipse":
            self._draft = EllipseShape(QRectF(phys, phys), self.style.copy())
        elif tool == "arrow":
            self._draft = ArrowShape(phys, phys, self.style.copy())
        elif tool == "pen":
            self._draft = PenShape([phys], self.style.copy())
        elif tool == "highlight":
            self._draft = HighlightShape([phys], self.style.copy())
        elif tool == "mosaic":
            self._draft = MosaicShape(QRectF(phys, phys), self.style.copy())
        else:
            self._draft = RectShape(QRectF(phys, phys), self.style.copy())
        self.update()

    def _update_draft(self, phys: QPointF) -> None:
        draft = self._draft
        if draft is None:
            return
        if isinstance(draft, (PenShape, HighlightShape)):
            draft.points.append(phys)
            return
        if isinstance(draft, (RectShape, EllipseShape, MosaicShape)):
            draft.rect = QRectF(draft.rect.topLeft(), phys).normalized()
            return
        if isinstance(draft, ArrowShape):
            draft.end = phys

    def _commit_draft(self) -> None:
        draft = self._draft
        self._draft = None
        if draft is None:
            return
        if isinstance(draft, (RectShape, EllipseShape, MosaicShape)):
            if draft.rect.width() < 2 or draft.rect.height() < 2:
                self.update()
                return
        if isinstance(draft, ArrowShape):
            if abs(draft.end.x() - draft.start.x()) < 2 and abs(draft.end.y() - draft.start.y()) < 2:
                self.update()
                return
        if isinstance(draft, (PenShape, HighlightShape)) and len(draft.points) < 2:
            self.update()
            return
        self.model.add(draft)

    # ---------------- 文字 ----------------

    def _start_text(self, phys: QPointF) -> None:
        self._close_text_edit(commit=True)
        widget = self._to_widget(QRectF(phys, phys)).topLeft()
        edit = QLineEdit(self)
        edit.setStyleSheet(
            "QLineEdit { background: rgba(0,0,0,0.45); color: #ffffff;"
            " border: 1px dashed #2f7cf6; padding: 2px 4px; font-size: 14px; }"
        )
        edit.setMinimumWidth(140)
        edit.move(int(widget.x()), int(widget.y()))
        edit.show()
        edit.setFocus(Qt.FocusReason.MouseFocusReason)
        edit.installEventFilter(self)
        edit.editingFinished.connect(lambda: self._close_text_edit(commit=True))
        self._text_edit = edit
        self._text_pos = phys

    def _close_text_edit(self, commit: bool) -> None:
        edit = self._text_edit
        if edit is None:
            return
        self._text_edit = None
        text = edit.text().strip()
        edit.removeEventFilter(self)
        edit.hide()
        edit.deleteLater()
        if commit and text and self._text_pos is not None:
            shape = TextShape(self._text_pos, text, self.style.copy())
            self.model.add(shape, "添加文字")
        self._text_pos = None
        self.setFocus()

    def eventFilter(self, obj, event):
        if obj is self._text_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._close_text_edit(commit=False)
                return True
        return super().eventFilter(obj, event)

    # ---------------- 键盘 ----------------

    def keyPressEvent(self, event) -> None:
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key.Key_Escape:
            if self._text_edit is not None:
                self._close_text_edit(commit=False)
                return
            self._abort()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not event.isAutoRepeat():
                self._emit_output("done")
            return

        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and self.model.can_undo():
            self.model.undo()
            return

        if modifiers & Qt.KeyboardModifier.ControlModifier or modifiers & Qt.KeyboardModifier.MetaModifier:
            if key == Qt.Key.Key_Z:
                if modifiers & Qt.KeyboardModifier.ShiftModifier:
                    self.model.redo()
                else:
                    self.model.undo()
                return
            if key == Qt.Key.Key_C:
                self._emit_output("copy")
                return
            if key == Qt.Key.Key_S:
                self._emit_output("save")
                return

        if self._mode == Mode.ANNOTATING and self._toolbar is not None:
            shortcuts = {
                Qt.Key.Key_R: "rect",
                Qt.Key.Key_E: "ellipse",
                Qt.Key.Key_A: "arrow",
                Qt.Key.Key_P: "pen",
                Qt.Key.Key_H: "highlight",
                Qt.Key.Key_T: "text",
                Qt.Key.Key_M: "mosaic",
                Qt.Key.Key_N: "badge",
            }
            if key in shortcuts:
                self._toolbar.select_tool(shortcuts[key])
                return

        super().keyPressEvent(event)

    def _abort(self) -> None:
        if self._done:
            return
        self._done = True
        self._close_text_edit(commit=False)
        self.canceled.emit()

    # ---------------- 输出 ----------------

    def composed(self) -> QImage:
        rect = self._selection_rect_phys()
        if rect.width() < 1 or rect.height() < 1:
            rect = self.frame.image.rect()
        out = QImage(rect.width(), rect.height(), QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.drawImage(QRect(0, 0, rect.width(), rect.height()), self.frame.image, rect)
            painter.translate(-rect.x(), -rect.y())
            for shape in self.model.shapes:
                shape.paint(painter, self.frame.image, self.frame.scale_x)
        finally:
            painter.end()
        return out

    def _emit_output(self, action: str) -> None:
        if self._done:
            return
        self._done = True
        self._close_text_edit(commit=True)
        image = self.composed()
        # 贴图要知道“这张图原来在屏幕的哪个位置、属于什么缩放比例”，
        # 否则贴出来会跑到屏幕中间、尺寸也不对
        rect = self._selection_rect_phys()
        scale = self.frame.scale_x
        position = QPointF(
            self.frame.screen.x + rect.x() / scale,
            self.frame.screen.y + rect.y() / scale,
        )
        self.finished.emit(image, action, scale, position)

    # ---------------- 绘制 ----------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        try:
            self._paint_scene(painter)
        finally:
            painter.end()

    def _paint_scene(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawImage(self.rect(), self.frame.image)

        # 只按 is None 判断：鼠标刚按下时选区是零尺寸的 QRectF，在 PySide 里是 falsy，
        # 用 if self._selection_phys 会把 None 传给 setClipRect，paintEvent 抛 TypeError
        # 后 painter 没 end，Qt 销毁绘图设备时直接 abort（0xc0000409）
        sel_widget = None
        if self._selection_phys is not None:
            sel_widget = self._to_widget(self._selection_phys)

        if self._selection_phys is not None:
            painter.save()
            painter.setClipRect(sel_widget)
            painter.scale(1.0 / self.frame.scale_x, 1.0 / self.frame.scale_y)
            for shape in self.model.shapes:
                shape.paint(painter, self.frame.image, self.frame.scale_x)
            if self._draft is not None:
                self._draft.paint(painter, self.frame.image, self.frame.scale_x)
            painter.restore()

        self._paint_dim(painter, sel_widget)
        if self._selection_phys is not None and sel_widget is not None:
            self._paint_selection(painter, sel_widget, self._selection_phys or QRectF())

        if self._mode == Mode.SELECTING:
            if not self._selected and self._cursor_phys is not None:
                self._paint_crosshair(painter)
            if self._selection_phys is not None and sel_widget is not None:
                self._paint_badge_size(painter, sel_widget, self._selection_phys or QRectF())
            if self._cursor_phys is not None:
                self._paint_magnifier(painter, self._cursor_phys)

    def _paint_dim(self, painter: QPainter, sel_widget: QRectF | None) -> None:
        region = QRegion(self.rect())
        if sel_widget is not None:
            region = region.subtracted(QRegion(sel_widget.toAlignedRect()))
        painter.save()
        painter.setClipRegion(region)
        painter.fillRect(self.rect(), QColor(0, 0, 0, DIM_ALPHA))
        painter.restore()

    def _paint_selection(self, painter: QPainter, sel_widget: QRectF, sel_phys: QRectF) -> None:
        painter.save()
        painter.setPen(QPen(ACCENT, 1.0))
        painter.drawRect(sel_widget.adjusted(0, 0, -1, -1))
        painter.setBrush(QColor(255, 255, 255, 235))
        for index in range(8):
            center = self._handle_center(sel_widget, index)
            rect = QRectF(
                center.x() - HANDLE_SIZE / 2,
                center.y() - HANDLE_SIZE / 2,
                HANDLE_SIZE,
                HANDLE_SIZE,
            )
            painter.drawRect(rect)
        painter.restore()

    @staticmethod
    def _handle_center(rect: QRectF, index: int) -> QPointF:
        xs = (rect.left(), rect.center().x(), rect.right())
        ys = (rect.top(), rect.center().y(), rect.bottom())
        ix, iy = HANDLE_ORDER[index % 8]
        return QPointF(xs[ix], ys[iy])

    def _paint_crosshair(self, painter: QPainter) -> None:
        cursor = self._cursor_phys
        if cursor is None:
            return
        widget = self._to_widget(QRectF(cursor, cursor)).topLeft()
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1.0))
        painter.drawLine(QPointF(0, widget.y()), QPointF(self.width(), widget.y()))
        painter.drawLine(QPointF(widget.x(), 0), QPointF(widget.x(), self.height()))
        painter.restore()

    def _paint_badge_size(self, painter: QPainter, sel_widget: QRectF, sel_phys: QRectF) -> None:
        text = f"{int(sel_phys.width())} × {int(sel_phys.height())}"
        font = QFont()
        font.setPointSizeF(12.0)
        painter.save()
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + 14
        height = metrics.height() + 6

        x = sel_widget.left()
        y = sel_widget.top() - height - 6
        if y < 0:
            y = sel_widget.top() + 6
        if x + width > self.width():
            x = self.width() - width - 6
        rect = QRectF(x, max(0.0, y), width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 200))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor(255, 255, 255, 240))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _paint_magnifier(self, painter: QPainter, cursor_phys: QPointF) -> None:
        image: QImage = self.frame.image
        half = MAG_SOURCE / 2
        src = QRectF(cursor_phys.x() - half, cursor_phys.y() - half, MAG_SOURCE, MAG_SOURCE)
        src = src.intersected(QRectF(0, 0, image.width(), image.height()))
        if src.width() < 1 or src.height() < 1:
            return

        box_w = MAG_SIZE
        box_h = MAG_SIZE + MAG_TEXT_H
        offset = 20.0
        x = cursor_phys.x() / self.frame.scale_x + offset
        y = cursor_phys.y() / self.frame.scale_y + offset
        if x + box_w > self.width():
            x = cursor_phys.x() / self.frame.scale_x - offset - box_w
        if y + box_h > self.height():
            y = cursor_phys.y() / self.frame.scale_y - offset - box_h
        x = max(2.0, min(x, self.width() - box_w - 2))
        y = max(2.0, min(y, self.height() - box_h - 2))
        box = QRectF(x, y, box_w, box_h)

        painter.save()
        painter.setBrush(QColor(0, 0, 0, 215))
        painter.setPen(QPen(ACCENT, 1.0))
        painter.drawRect(box)

        sampled = image.copy(src.toAlignedRect())
        target = QRectF(x + 1, y + 1, box_w - 2, MAG_SIZE - 2)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(target, sampled)

        color = image.pixelColor(int(cursor_phys.x()), int(cursor_phys.y()))
        font = QFont()
        font.setPointSizeF(9.5)
        painter.setFont(font)
        painter.setPen(QColor(235, 235, 235))
        text_rect = QRectF(x, y + MAG_SIZE, box_w, MAG_TEXT_H)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignCenter,
            f"{int(cursor_phys.x())},{int(cursor_phys.y())}  {color.name().upper()}",
        )
        painter.restore()
