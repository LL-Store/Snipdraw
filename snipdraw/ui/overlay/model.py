"""标注模型：图元列表 + 撤销栈。

所有修改都走 QUndoCommand，emitting changed 由撤销栈的 indexChanged 统一驱动，
避免“有的操作发信号、有的不发”这种不一致。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from .shapes import Shape


class AddShape(QUndoCommand):
    def __init__(self, model: "AnnotationModel", shape: Shape, text: str = "添加标注") -> None:
        super().__init__(text)
        self.model = model
        self.shape = shape

    def redo(self) -> None:
        self.model._shapes.append(self.shape)

    def undo(self) -> None:
        if self.shape in self.model._shapes:
            self.model._shapes.remove(self.shape)


class MoveShape(QUndoCommand):
    def __init__(self, model: "AnnotationModel", index: int, delta: QPointF) -> None:
        super().__init__("移动标注")
        self.model = model
        self.index = index
        self.delta = delta

    def redo(self) -> None:
        self._apply(self.delta)

    def undo(self) -> None:
        self._apply(QPointF(-self.delta.x(), -self.delta.y()))

    def _apply(self, delta: QPointF) -> None:
        shapes = self.model._shapes
        if 0 <= self.index < len(shapes):
            shapes[self.index] = shapes[self.index].translated(delta)


class ClearShapes(QUndoCommand):
    def __init__(self, model: "AnnotationModel") -> None:
        super().__init__("清空标注")
        self.model = model
        self.removed: list[Shape] = []

    def redo(self) -> None:
        self.removed = list(self.model._shapes)
        self.model._shapes.clear()

    def undo(self) -> None:
        self.model._shapes.extend(self.removed)


class AnnotationModel(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._shapes: list[Shape] = []
        self.stack = QUndoStack(self)
        # 用绑定方法而不是 lambda：控件销毁时 PySide 才会自动断开，
        # 否则退出应用时会报 "Signal source has been deleted"
        self.stack.indexChanged.connect(self._on_stack_changed)

    def _on_stack_changed(self, _index: int) -> None:
        try:
            self.changed.emit()
        except RuntimeError:
            pass

    @property
    def shapes(self) -> list[Shape]:
        return list(self._shapes)

    def add(self, shape: Shape, text: str = "添加标注") -> None:
        self.stack.push(AddShape(self, shape, text))

    def move(self, index: int, delta: QPointF) -> None:
        if delta.isNull():
            return
        self.stack.push(MoveShape(self, index, delta))

    def clear(self) -> None:
        if self._shapes:
            self.stack.push(ClearShapes(self))

    def undo(self) -> None:
        self.stack.undo()

    def redo(self) -> None:
        self.stack.redo()

    def can_undo(self) -> bool:
        return self.stack.canUndo()

    def can_redo(self) -> bool:
        return self.stack.canRedo()

    def next_badge(self) -> int:
        badges = [s for s in self._shapes if s.kind == "badge"]
        return len(badges) + 1

    def topmost_at(self, point: QPointF, tolerance: float) -> int | None:
        for index in range(len(self._shapes) - 1, -1, -1):
            if self._shapes[index].hit(point, tolerance):
                return index
        return None
