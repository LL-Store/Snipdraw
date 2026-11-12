"""托盘：常驻入口，热键不可用时的兜底操作面。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .icon import tray_icon


class Tray(QObject):
    captureRequested = Signal(int)      # 0 = 立即，其余为延时秒数
    settingsRequested = Signal()
    openSaveDirRequested = Signal()
    closePinsRequested = Signal()
    quitRequested = Signal()

    def __init__(self, hotkey_label: str = "", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._icon = QSystemTrayIcon(tray_icon(), self)
        self._icon.setToolTip("Snipdraw")

        menu = QMenu()
        self._capture_action = menu.addAction("截图")
        self._capture_action.triggered.connect(lambda: self.captureRequested.emit(0))

        self._delay_menu = menu.addMenu("延时截图")
        for seconds in (3, 5, 10):
            action = self._delay_menu.addAction(f"{seconds} 秒")
            action.triggered.connect(lambda _=False, s=seconds: self.captureRequested.emit(s))

        menu.addSeparator()
        settings_action = menu.addAction("设置…")
        settings_action.triggered.connect(self.settingsRequested.emit)
        open_dir_action = menu.addAction("打开保存目录")
        open_dir_action.triggered.connect(self.openSaveDirRequested.emit)
        self._close_pins_action = menu.addAction("关闭所有贴图")
        self._close_pins_action.triggered.connect(self.closePinsRequested.emit)
        self._close_pins_action.setEnabled(False)

        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.quitRequested.emit)

        self._menu = menu
        self._icon.setContextMenu(menu)
        self.set_hotkey_label(hotkey_label)

    def set_hotkey_state(self, label: str, hint: str = "") -> None:
        """热键状态只写在菜单标签和 tooltip 上，不弹系统通知。

        弹窗留给"截图完了/失败了"这类一次性结果；热键状态是常驻信息，
        每次启动都弹一遍只会变成噪音。
        """
        self._capture_action.setText(f"截图    {label}" if label else "截图")
        self._icon.setToolTip("Snipdraw" + (f" · {hint}" if hint else ""))

    def set_hotkey_label(self, label: str) -> None:
        self.set_hotkey_state(label)

    def set_pin_count(self, count: int) -> None:
        self._close_pins_action.setEnabled(count > 0)
        self._close_pins_action.setText(f"关闭所有贴图（{count}）" if count else "关闭所有贴图")

    def show(self) -> None:
        self._icon.show()

    def hide(self) -> None:
        self._icon.hide()

    def notify(self, title: str, message: str, msecs: int = 3000) -> None:
        if self._icon.isVisible():
            self._icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, msecs)
