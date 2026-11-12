"""设置对话框：热键、延时、保存位置与格式。"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.settings import Settings
from ..core.storage import picture_dir


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Snipdraw 设置")
        self.setMinimumWidth(460)
        self._settings = settings

        form = QFormLayout()

        self.hotkey_check = QCheckBox("启用全局热键")
        self.hotkey_check.setToolTip("关闭后只能从托盘菜单触发截图，适合热键被其它软件占用的情况")
        self.hotkey_check.setChecked(settings.hotkey_enabled)
        form.addRow("", self.hotkey_check)

        self.hotkey_edit = QKeySequenceEdit(QKeySequence(settings.hotkey))
        self.hotkey_edit.setEnabled(settings.hotkey_enabled)
        self.hotkey_edit.setToolTip(
            "macOS 上若 F1 是亮度键，需要在系统设置里勾选“将 F1、F2 用作标准功能键”"
        )
        self.hotkey_check.toggled.connect(self.hotkey_edit.setEnabled)
        form.addRow("截图热键", self.hotkey_edit)

        if sys.platform == "darwin":
            # 屏幕录制权限不写在界面上，用户就只能在"每次截图被弹框"里猜
            from ..platform.macos_permission import (
                open_privacy_settings,
                permission_subject,
                screen_capture_granted,
            )

            granted = screen_capture_granted()
            status = QLabel("已授权" if granted else "未授权 · 截图会被系统拦下")
            status.setStyleSheet(f"color: {'#2f9e44' if granted else '#c92a2a'};")
            status.setToolTip(
                f"授权对象是「{permission_subject()}」。系统设置里勾选后需要重启 Snipdraw；"
                "选“允许一次”只对当次生效。"
            )
            row = QHBoxLayout()
            row.addWidget(status, 1)
            grant = QPushButton("打开系统设置")
            grant.clicked.connect(open_privacy_settings)
            row.addWidget(grant)
            holder = QWidget()
            holder.setLayout(row)
            form.addRow("屏幕录制", holder)

        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 30)
        self.delay_spin.setSuffix(" 秒")
        self.delay_spin.setValue(settings.delay_seconds)
        form.addRow("默认延时时长", self.delay_spin)

        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(settings.save_dir)
        self.dir_edit.setPlaceholderText(str(picture_dir() / "Snipdraw"))
        browse = QPushButton("选择…")
        browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse)
        container = QWidget()
        container.setLayout(dir_row)
        form.addRow("保存目录", container)

        self.format_combo = QComboBox()
        self.format_combo.addItem("PNG（无损）", "png")
        self.format_combo.addItem("JPG（体积小）", "jpg")
        index = self.format_combo.findData(settings.image_format)
        self.format_combo.setCurrentIndex(max(index, 0))
        form.addRow("保存格式", self.format_combo)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(settings.jpeg_quality)
        self.quality_spin.setEnabled(settings.image_format == "jpg")
        self.format_combo.currentIndexChanged.connect(
            lambda: self.quality_spin.setEnabled(self.format_combo.currentData() == "jpg")
        )
        form.addRow("JPG 质量", self.quality_spin)

        self.auto_copy_check = QCheckBox("截图后自动复制到剪贴板")
        self.auto_copy_check.setChecked(settings.auto_copy)
        form.addRow("", self.auto_copy_check)

        self.auto_save_check = QCheckBox("截图后自动保存到磁盘")
        self.auto_save_check.setChecked(settings.auto_save)
        form.addRow("", self.auto_save_check)

        hint = QLabel(
            "总可以只用托盘：菜单里的「截图」和「延时截图」不依赖热键。"
            "热键被占用时先自动改用 Ctrl+Alt+A，两个都失败就只剩托盘。"
            "Wayland 会话不支持全局热键，同样走托盘。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)

        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, False)

    def _browse_dir(self) -> None:
        start = self.dir_edit.text().strip() or str(picture_dir())
        chosen = QFileDialog.getExistingDirectory(self, "选择保存目录", start)
        if chosen:
            self.dir_edit.setText(chosen)

    def result_settings(self) -> Settings:
        sequence = self.hotkey_edit.keySequence().toString()
        settings = Settings(
            hotkey=sequence or self._settings.hotkey,
            hotkey_fallback=self._settings.hotkey_fallback,
            hotkey_enabled=self.hotkey_check.isChecked(),
            delay_seconds=self.delay_spin.value(),
            save_dir=self.dir_edit.text().strip(),
            image_format=self.format_combo.currentData(),
            jpeg_quality=self.quality_spin.value(),
            auto_copy=self.auto_copy_check.isChecked(),
            auto_save=self.auto_save_check.isChecked(),
            play_sound=self._settings.play_sound,
            start_at_login=self._settings.start_at_login,
            pin_limit=self._settings.pin_limit,
            annotation_color=self._settings.annotation_color,
            annotation_width=self._settings.annotation_width,
            font_size=self._settings.font_size,
        )
        return settings.normalized()
