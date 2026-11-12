"""标注工具栏：跟在选区下方浮动的操作条。

特意做成 overlay 的子控件而不是独立窗口：这样它天然随选区移动、
不会在屏幕上留下一个能被截进去的浮动窗口，也不用单独管生命周期。
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

TOOLS: list[tuple[str, str, str]] = [
    ("rect", "矩形", "R"),
    ("ellipse", "椭圆", "E"),
    ("arrow", "箭头", "A"),
    ("pen", "画笔", "P"),
    ("highlight", "高亮", "H"),
    ("text", "文字", "T"),
    ("mosaic", "马赛克", "M"),
    ("badge", "序号", "N"),
]

COLORS = ["#ff3b30", "#ff9500", "#ffcc00", "#34c759", "#2f7cf6", "#ffffff", "#000000"]

STYLE_SHEET = """
QFrame#snipToolbar {
    background: rgba(30, 30, 32, 0.94);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 9px;
}
QToolButton {
    color: #e8e8e8;
    border: none;
    border-radius: 5px;
    padding: 3px 7px;
    font-size: 12px;
}
QToolButton:hover { background: rgba(255, 255, 255, 0.14); }
QToolButton:checked { background: #2f7cf6; color: #ffffff; }
QToolButton:disabled { color: rgba(255, 255, 255, 0.3); }
"""


class Toolbar(QFrame):
    toolChanged = Signal(str)
    styleChanged = Signal()
    undoRequested = Signal()
    redoRequested = Signal()
    clearRequested = Signal()
    copyRequested = Signal()
    saveRequested = Signal()
    pinRequested = Signal()
    doneRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("snipToolbar")
        self.setStyleSheet(STYLE_SHEET)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._tool = "rect"
        self._color = QColor(color)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(5)

        # 第一行：工具
        tools_row = QHBoxLayout()
        tools_row.setSpacing(1)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        for key, label, shortcut in TOOLS:
            button = QToolButton(self)
            button.setText(label)
            button.setCheckable(True)
            button.setToolTip(f"{label}（{shortcut}）")
            button.clicked.connect(lambda _=False, k=key: self.select_tool(k))
            self._group.addButton(button)
            self._buttons[key] = button
            tools_row.addWidget(button)
            if key == "rect":
                button.setChecked(True)

        tools_row.addStretch(1)
        root.addLayout(tools_row)

        # 第二行：颜色 + 撤销/重做 + 动作
        actions_row = QHBoxLayout()
        actions_row.setSpacing(4)
        self._color_buttons: list[QToolButton] = []
        for value in COLORS:
            swatch = QToolButton(self)
            swatch.setFixedSize(QSize(18, 18))
            swatch.setCheckable(True)
            swatch.setToolTip(value)
            swatch.setStyleSheet(
                f"QToolButton {{ background: {value}; border: 1px solid rgba(255,255,255,0.35);"
                f" border-radius: 4px; }}"
                f" QToolButton:checked {{ border: 2px solid #ffffff; }}"
            )
            swatch.clicked.connect(lambda _=False, v=value: self._select_color(v))
            self._color_buttons.append(swatch)
            actions_row.addWidget(swatch)
        self._select_color(self._color.name())

        actions_row.addSpacing(10)
        self.undo_button = self._action(actions_row, "撤销", "Ctrl+Z", self.undoRequested)
        self.redo_button = self._action(actions_row, "重做", "Ctrl+Shift+Z", self.redoRequested)
        self._action(actions_row, "清空", "", self.clearRequested)
        actions_row.addSpacing(10)
        self._action(actions_row, "复制", "Ctrl+C", self.copyRequested)
        self._action(actions_row, "保存", "Ctrl+S", self.saveRequested)
        self._action(actions_row, "贴图", "P 到屏幕", self.pinRequested)
        actions_row.addSpacing(10)
        self._action(actions_row, "完成", "Enter", self.doneRequested, primary=True)
        self._action(actions_row, "取消", "Esc", self.cancelRequested)
        actions_row.addStretch(1)
        root.addLayout(actions_row)

        self.set_undo_state(False, False)

    def _action(self, row: QHBoxLayout, text: str, tip: str, signal, primary: bool = False) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        if tip:
            button.setToolTip(f"{text}（{tip}）")
        if primary:
            button.setStyleSheet(
                "QToolButton { background: #2f7cf6; color: #ffffff; border-radius: 5px;"
                " padding: 3px 10px; font-size: 12px; }"
                "QToolButton:hover { background: #4b90f8; }"
            )
        button.clicked.connect(signal.emit)
        row.addWidget(button)
        return button

    # ---------------- 状态 ----------------

    def _select_tool(self, key: str) -> None:
        self._tool = key
        self.toolChanged.emit(key)

    def select_tool(self, key: str) -> None:
        """外部（快捷键）切工具时也要让按钮状态跟着走。"""
        button = self._buttons.get(key)
        if button is None:
            return
        button.setChecked(True)
        self._select_tool(key)

    def _select_color(self, value: str) -> None:
        self._color = QColor(value)
        for button in self._color_buttons:
            button.setChecked(button.toolTip().lower() == value.lower())
        self.styleChanged.emit()

    def current_tool(self) -> str:
        return self._tool

    def color(self) -> QColor:
        return QColor(self._color)

    def set_undo_state(self, can_undo: bool, can_redo: bool) -> None:
        self.undo_button.setEnabled(can_undo)
        self.redo_button.setEnabled(can_redo)
