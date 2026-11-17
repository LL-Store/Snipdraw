"""应用装配：单实例 + 托盘 + 全局热键 + overlay + 输出。

流程：热键/托盘触发 → （可选）延时 → 截全屏 → 每屏 overlay 冻结帧框选
      → 复制到剪贴板 / 存盘 → 托盘提示。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog

from . import __version__
from .core import storage
from .core.capture import Frame
from .core.settings import Settings
from .core.single_instance import SingleInstance
from .platform import autostart
from .platform.hotkey import HotkeyManager
from .ui.icon import app_icon
from .ui.overlay.controller import OverlayController
from .ui.pin.controller import PinController
from .ui.settings_dialog import SettingsDialog
from .ui.tray import Tray


class SnipdrawApp(QObject):
    def __init__(self, argv: list[str], open_settings: bool = False) -> None:
        super().__init__()
        self.qt = QApplication(argv)
        self.qt.setApplicationName("Snipdraw")
        self.qt.setApplicationDisplayName("Snipdraw")
        self.qt.setOrganizationName("zxl20070701")
        self.qt.setApplicationVersion(__version__)
        self.qt.setWindowIcon(app_icon())
        # 托盘常驻应用：关掉最后一个窗口不等于退出
        self.qt.setQuitOnLastWindowClosed(False)

        self.settings: Settings = storage.load()
        self.should_exit = False
        self._open_settings_on_start = open_settings

        # 启动时按设置对齐一次自启动状态：默认开启，首次运行就注册。
        autostart.set_enabled(self.settings.start_at_login)

        # 单实例：已有实例就转发指令后退出，避免两个进程抢同一个热键
        self.instance = SingleInstance()
        if self.instance.notify_existing("settings" if open_settings else "capture"):
            self.should_exit = True
            return
        self.instance.listen()
        self.instance.commandReceived.connect(self._on_remote_command)

        self.overlay = OverlayController(
            color=QColor(self.settings.annotation_color),
            width=self.settings.annotation_width,
            font_size=self.settings.font_size,
            parent=self,
        )
        self.overlay.finished.connect(self._on_overlay_finished)
        self.overlay.canceled.connect(self._on_overlay_canceled)
        self.overlay.failed.connect(self._on_overlay_failed)

        # 贴图：数量上限来自设置，超出后关掉最旧的一张
        self.pins = PinController(limit=self.settings.pin_limit, parent=self)
        self.pins.copyRequested.connect(self._copy_image)
        self.pins.saveRequested.connect(self._save_image)
        self.pins.countChanged.connect(self._on_pin_count)

        self.tray = Tray()
        self.tray.captureRequested.connect(self.capture_now)
        self.tray.settingsRequested.connect(self.open_settings)
        self.tray.openSaveDirRequested.connect(self.open_save_dir)
        self.tray.closePinsRequested.connect(self.pins.close_all)
        self.tray.quitRequested.connect(self.quit)
        self.tray.show()

        self.hotkeys = HotkeyManager()
        self._bind_hotkey()

        # macOS「屏幕录制」权限：启动时预检一次，没给就请求一次。
        # 之后每次截图都只看这个结果——不再反复尝试，系统就不会反复弹框。
        self.can_screen_capture = True
        if sys.platform == "darwin":
            from .platform.macos_permission import (
                request_screen_capture,
                screen_capture_granted,
            )

            self.can_screen_capture = screen_capture_granted() or request_screen_capture()

        if self._open_settings_on_start:
            # 没有托盘图标可点时的备用入口：python -m snipdraw settings
            QTimer.singleShot(0, self.open_settings)

    # ---------------- 热键 ----------------

    def _bind_hotkey(self) -> None:
        # 关掉全局热键就只走托盘：热键被别的软件占死时，这是唯一干净的退路
        if not self.settings.hotkey_enabled:
            self.hotkeys.release()
            self.tray.set_hotkey_state("仅托盘", "热键已关闭 · 从菜单「截图」触发")
            return
        sequence = self.hotkeys.bind(
            self.settings.hotkey, self.settings.hotkey_fallback, self.capture_now
        )
        if not sequence:
            # 两个组合都抢不到：仍可用，但要说清楚去哪儿点
            self.tray.set_hotkey_state("用托盘", self.hotkeys.message or "全局热键不可用")
        elif self.hotkeys.message:
            # 主键失败、已回退：把真实生效的组合摆在菜单上，不弹窗
            self.tray.set_hotkey_state(sequence, self.hotkeys.message)
        else:
            self.tray.set_hotkey_state(sequence, f"按 {sequence} 截图")

    def _rebind_hotkey(self) -> None:
        self.hotkeys.release()
        self._bind_hotkey()

    # ---------------- 权限 ----------------

    def _ensure_screen_permission(self) -> bool:
        """没授权就只提示、不尝试截图：每次尝试都会再触发系统弹框。"""
        if self.can_screen_capture:
            return True
        if sys.platform != "darwin":
            return True

        from .platform.macos_permission import permission_subject, screen_capture_granted

        # 用户可能刚在系统设置里勾上，这里再预检一次，能救回"不用重启"的情况
        self.can_screen_capture = screen_capture_granted()
        if self.can_screen_capture:
            return True

        self.tray.notify(
            "Snipdraw 需要「屏幕录制」权限",
            f"系统设置 → 隐私与安全性 → 屏幕录制，勾选 {permission_subject()} 后重启 Snipdraw。"
            "（选“允许一次”只对当次生效，下次还会问）",
            8000,
        )
        return False

    # ---------------- 截图流程 ----------------

    def capture_now(self, delay: int = 0) -> None:
        if self.should_exit:
            return
        if self.overlay.active:
            # 已经在截图/标注：再按热键只把窗口顶上来，不开第二份 overlay。
            # 静默忽略会让用户以为程序卡死，然后去按 Esc。
            self.overlay.focus_active()
            return

        if not self._ensure_screen_permission():
            return

        if delay > 0:
            self.tray.notify("Snipdraw", f"{delay} 秒后截图…", 2000)
            QTimer.singleShot(delay * 1000, self._open_overlay)
            return
        self._open_overlay()

    def _open_overlay(self) -> None:
        if self.overlay.active:
            return
        self.overlay.start()

    def _on_overlay_finished(self, image, action: str = "done", scale: float = 1.0, position=None) -> None:
        if image is None or image.isNull():
            self.tray.notify("Snipdraw", "截图区域无效")
            return

        if action == "pin":
            self.pins.create(image, scale, position)
            self.tray.notify(
                f"Snipdraw  {image.width()}×{image.height()}",
                f"已贴到屏幕上（共 {self.pins.count} 张）",
            )
            return

        messages: list[str] = []
        want_copy = action in ("done", "copy") and (action == "copy" or self.settings.auto_copy)
        want_save = action == "save" or (action == "done" and self.settings.auto_save)

        if want_copy:
            self._copy_image(image)
            messages.append("已复制")

        if want_save:
            path = self._save(image)
            if path is not None:
                messages.append(f"已保存 {path.name}")

        self.tray.notify(
            f"Snipdraw  {image.width()}×{image.height()}",
            " · ".join(messages) or "已完成",
        )

    def _copy_image(self, image) -> None:
        QGuiApplication.clipboard().setImage(image)

    def _save_image(self, image) -> None:
        path = self._save(image)
        if path is not None:
            self.tray.notify("Snipdraw", f"已保存 {path.name}")

    def _on_pin_count(self, count: int) -> None:
        self.tray.set_pin_count(count)

    def _on_overlay_canceled(self) -> None:
        pass

    def _on_overlay_failed(self, message: str) -> None:
        self.tray.notify("Snipdraw 截图失败", message, 6000)

    def _save(self, image) -> Path | None:
        directory = storage.resolve_save_dir(self.settings)
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.tray.notify("Snipdraw", f"无法创建目录：{error}", 6000)
            return None

        name = storage.build_filename(self.settings.image_format)
        path = storage.unique_path(directory, name)
        fmt = "JPG" if self.settings.image_format == "jpg" else "PNG"
        quality = self.settings.jpeg_quality if fmt == "JPG" else -1
        if not image.save(str(path), fmt, quality):
            self.tray.notify("Snipdraw", f"保存失败：{path}", 6000)
            return None
        return path

    # ---------------- 其它入口 ----------------

    def open_settings(self) -> None:
        if self.overlay.active:
            return
        dialog = SettingsDialog(self.settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings = dialog.result_settings()
            storage.save(self.settings)
            autostart.set_enabled(self.settings.start_at_login)
            self._rebind_hotkey()

    def open_save_dir(self) -> None:
        directory = storage.resolve_save_dir(self.settings)
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _on_remote_command(self, command: str) -> None:
        command = command.strip()
        if command == "capture":
            self.capture_now(0)
        elif command == "settings":
            self.open_settings()

    def quit(self) -> None:
        self.hotkeys.release()
        self.pins.close_all()
        self.overlay.close_all()
        self.tray.hide()
        self.qt.quit()

    def run(self) -> int:
        if self.should_exit:
            return 0
        return self.qt.exec()


def run(argv: list[str] | None = None, open_settings: bool = False) -> int:
    app = SnipdrawApp(list(sys.argv if argv is None else argv), open_settings=open_settings)
    return app.run()
