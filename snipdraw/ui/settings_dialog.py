"""设置对话框：热键、延时、保存位置与格式。"""

from __future__ import annotations

import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (
    QColor,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.settings import Settings
from ..core.storage import data_dir, picture_dir
from ..ui.icon import app_icon
from ..ui.theme import resolve_theme

PRIMARY = "#2f7cf6"
PRIMARY_HOVER = "#4b90f8"

# 浅色 / 深色两套配色，按当前系统配色亮度切换，避免深色模式下白底黑字。
_LIGHT = {
    "bg": "#f4f5f7",
    "card": "#ffffff",
    "card_border": "#e6e8ec",
    "text": "#1d1f24",
    "muted": "#8a8f99",
    "field_bg": "#ffffff",
    "field_border": "#d6d9df",
    "field_disabled_bg": "#f0f1f3",
    "hint_bg": "#eceef1",
    "success_bg": "#e6f4ea",
    "success_text": "#2f9e44",
    "danger_bg": "#fdecea",
    "danger_text": "#c92a2a",
}
_DARK = {
    "bg": "#1e1f22",
    "card": "#2a2b2f",
    "card_border": "#3a3b40",
    "text": "#e8e8e8",
    "muted": "#9a9ea8",
    "field_bg": "#333438",
    "field_border": "#45464c",
    "field_disabled_bg": "#26272a",
    "hint_bg": "#26272a",
    "success_bg": "#1f3d2a",
    "success_text": "#4cd07d",
    "danger_bg": "#472626",
    "danger_text": "#ff6b63",
}


def _palette(theme: str) -> dict[str, str]:
    return _DARK if resolve_theme(theme) == "dark" else _LIGHT


_ARROW_CACHE: dict[str, str] = {}


def _arrow_path(kind: str, color: str) -> str:
    """画一个 12x12 的三角箭头并缓存为 png，供 QSS 的 image: url() 引用。

    QSS 只能引用图片文件，不能内嵌位图；写到应用数据目录，打包后也可写。
    kind: "up" / "down"。
    """
    key = f"{kind}-{color}"
    cached = _ARROW_CACHE.get(key)
    if cached:
        return cached

    size = 12
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    path = QPainterPath()
    if kind == "up":
        path.moveTo(3.0, 9.0)
        path.lineTo(size - 3.0, 9.0)
        path.lineTo(size / 2.0, 3.0)
    else:
        path.moveTo(3.0, 3.0)
        path.lineTo(size - 3.0, 3.0)
        path.lineTo(size / 2.0, size - 3.0)
    path.closeSubpath()
    painter.drawPath(path)
    painter.end()

    assets = data_dir() / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    target = assets / f"arrow-{kind}-{color.lstrip('#')}.png"
    pixmap.save(str(target), "PNG")
    _ARROW_CACHE[key] = str(target)
    return str(target)


def _build_stylesheet(c: dict[str, str]) -> str:
    arrow_down = _arrow_path("down", c["muted"])
    arrow_up = _arrow_path("up", c["muted"])
    return f"""
    QDialog {{ background: {c['bg']}; }}

    QFrame#card {{
        background: {c['card']};
        border: 1px solid {c['card_border']};
        border-radius: 12px;
    }}
    QLabel#cardTitle {{ color: {c['text']}; font-size: 13px; font-weight: 600; }}
    QLabel#dialogTitle {{ color: {c['text']}; font-size: 16px; font-weight: 700; }}
    QLabel#muted {{ color: {c['muted']}; font-size: 12px; }}
    QLabel {{ color: {c['text']}; font-size: 13px; }}

    QLineEdit, QComboBox, QSpinBox, QKeySequenceEdit {{
        background: {c['field_bg']};
        color: {c['text']};
        border: 1px solid {c['field_border']};
        border-radius: 8px;
        min-height: 28px;
        font-size: 13px;
        selection-background-color: {PRIMARY};
        selection-color: #ffffff;
    }}
    QLineEdit, QKeySequenceEdit {{ padding: 0 10px; }}
    QComboBox {{ padding: 0 30px 0 10px; }}
    QSpinBox {{ padding: 0 26px 0 10px; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QKeySequenceEdit:focus {{
        border: 1px solid {PRIMARY};
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QKeySequenceEdit:disabled {{
        background: {c['field_disabled_bg']};
        color: {c['muted']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
        subcontrol-origin: padding;
        subcontrol-position: center right;
        right: 8px;
        image: url("{arrow_down}");
    }}
    QComboBox QAbstractItemView {{
        background: {c['field_bg']};
        color: {c['text']};
        border: 1px solid {c['card_border']};
        border-radius: 8px;
        padding: 4px;
        selection-background-color: {PRIMARY};
        selection-color: #ffffff;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        border: none;
        width: 20px;
        subcontrol-origin: padding;
    }}
    QSpinBox::up-button {{
        subcontrol-position: top right;
        image: url("{arrow_up}");
    }}
    QSpinBox::down-button {{
        subcontrol-position: bottom right;
        image: url("{arrow_down}");
    }}
    QSpinBox::up-button:disabled, QSpinBox::down-button:disabled {{ image: none; }}

    QCheckBox {{ spacing: 8px; font-size: 13px; color: {c['text']}; }}
    QCheckBox:disabled {{ color: {c['muted']}; }}

    QPushButton {{
        min-height: 32px;
        padding: 0 16px;
        border-radius: 8px;
        font-size: 13px;
        border: 1px solid {c['field_border']};
        background: {c['field_bg']};
        color: {c['text']};
    }}
    QPushButton#browseDirectory {{
        min-height: 28px;
    }}
    QPushButton:hover {{ background: {c['hint_bg']}; }}
    QPushButton#primary {{
        background: {PRIMARY};
        border: 1px solid {PRIMARY};
        color: #ffffff;
        font-weight: 600;
    }}
    QPushButton#primary:hover {{ background: {PRIMARY_HOVER}; }}

    QLabel#badge {{ border-radius: 11px; padding: 5px 12px; font-size: 12px; font-weight: 600; }}
    QFrame#hintBox {{ background: {c['hint_bg']}; border-radius: 10px; }}
    QFrame#hintBox QLabel {{ color: {c['muted']}; font-size: 12px; }}
    """


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Snipdraw 设置")
        self.setMinimumWidth(520)
        self._settings = settings
        self._pal = _palette(settings.theme)
        self.setStyleSheet(_build_stylesheet(self._pal))

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        root.addLayout(self._build_header())

        # ---------- 热键与权限 ----------
        hotkey_card, hotkey_form = self._make_card("热键与权限")

        self.hotkey_check = QCheckBox("启用全局热键")
        self.hotkey_check.setToolTip(
            "关闭后只能从托盘菜单触发截图，适合热键被其它软件占用的情况"
        )
        self.hotkey_check.setChecked(settings.hotkey_enabled)
        self._add_check_row(hotkey_form, self.hotkey_check)

        self.hotkey_edit = QKeySequenceEdit(QKeySequence(settings.hotkey))
        self.hotkey_edit.setEnabled(settings.hotkey_enabled)
        self.hotkey_edit.setToolTip(
            "macOS 上若 F1 是亮度键，需要在系统设置里勾选“将 F1、F2 用作标准功能键”"
        )
        self.hotkey_check.toggled.connect(self.hotkey_edit.setEnabled)
        self._add_row(hotkey_form, "截图热键", self.hotkey_edit)

        if sys.platform == "darwin":
            # 屏幕录制权限不写在界面上，用户就只能在"每次截图被弹框"里猜
            from ..platform.macos_permission import (
                open_privacy_settings,
                permission_subject,
                screen_capture_granted,
            )

            granted = screen_capture_granted()
            status = QLabel("已授权" if granted else "未授权 · 截图会被系统拦下")
            status.setObjectName("badge")
            badge_color = "success" if granted else "danger"
            status.setStyleSheet(
                f"background: {self._pal[badge_color + '_bg']};"
                f"color: {self._pal[badge_color + '_text']};"
            )
            status.setToolTip(
                f"授权对象是「{permission_subject()}」。系统设置里勾选后需要重启 Snipdraw；"
                "选“允许一次”只对当次生效。"
            )
            row = QHBoxLayout()
            row.setSpacing(10)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(status, 1, Qt.AlignmentFlag.AlignLeft)
            grant = QPushButton("打开系统设置")
            grant.clicked.connect(open_privacy_settings)
            row.addWidget(grant)
            holder = QWidget()
            holder.setLayout(row)
            self._add_row(hotkey_form, "屏幕录制", holder)

        root.addWidget(hotkey_card)

        # ---------- 保存 ----------
        save_card, save_form = self._make_card("保存")

        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 30)
        self.delay_spin.setSuffix(" 秒")
        self.delay_spin.setValue(settings.delay_seconds)
        self.delay_spin.lineEdit().setTextMargins(10, 0, 0, 0)
        self._add_row(save_form, "默认延时时长", self.delay_spin)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(10)
        dir_row.setContentsMargins(0, 0, 0, 0)
        self.dir_edit = QLineEdit(settings.save_dir)
        self.dir_edit.setPlaceholderText(str(picture_dir() / "Snipdraw"))
        # 长路径下输入框要能被压缩，否则最小尺寸把「选择…」按钮挤出并排位置
        self.dir_edit.setMinimumWidth(0)
        self.dir_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        browse = QPushButton("选择…")
        browse.setObjectName("browseDirectory")
        browse.setFixedWidth(92)
        browse.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse, 0)
        label = QLabel("保存目录")
        label.setMinimumWidth(104)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        save_form.addRow(label, dir_row)

        self.format_combo = QComboBox()
        self.format_combo.addItem("PNG（无损）", "png")
        self.format_combo.addItem("JPG（体积小）", "jpg")
        index = self.format_combo.findData(settings.image_format)
        self.format_combo.setCurrentIndex(max(index, 0))
        self._add_row(save_form, "保存格式", self.format_combo)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(settings.jpeg_quality)
        self.quality_spin.setEnabled(settings.image_format == "jpg")
        self.format_combo.currentIndexChanged.connect(
            lambda: self.quality_spin.setEnabled(
                self.format_combo.currentData() == "jpg"
            )
        )
        self.quality_spin.lineEdit().setTextMargins(10, 0, 0, 0)
        self._add_row(save_form, "JPG 质量", self.quality_spin)

        root.addWidget(save_card)

        # ---------- 外观 ----------
        appearance_card, appearance_form = self._make_card("外观")

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        theme_index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(max(theme_index, 0))
        self.theme_combo.currentIndexChanged.connect(self._reapply_theme)
        self._add_row(appearance_form, "主题", self.theme_combo)

        root.addWidget(appearance_card)

        # ---------- 行为 ----------
        behavior_card, behavior_form = self._make_card("行为")

        self.auto_copy_check = QCheckBox("截图后自动复制到剪贴板")
        self.auto_copy_check.setChecked(settings.auto_copy)
        self._add_check_row(behavior_form, self.auto_copy_check)

        self.auto_save_check = QCheckBox("截图后自动保存到磁盘")
        self.auto_save_check.setChecked(settings.auto_save)
        self._add_check_row(behavior_form, self.auto_save_check)

        self.autostart_check = QCheckBox("开机时自动启动 Snipdraw")
        self.autostart_check.setToolTip(
            "登录系统后后台常驻托盘，需要截图时按热键或点托盘图标"
        )
        self.autostart_check.setChecked(settings.start_at_login)
        self._add_check_row(behavior_form, self.autostart_check)

        root.addWidget(behavior_card)

        # ---------- 底部提示 ----------
        hint = QLabel(
            "总可以只用托盘：菜单里的「截图」和「延时截图」不依赖热键。"
            "热键被占用时先自动改用 Ctrl+Alt+A，两个都失败就只剩托盘。"
            "Wayland 会话不支持全局热键，同样走托盘。"
        )
        hint.setWordWrap(True)
        hint_box = QFrame()
        hint_box.setObjectName("hintBox")
        hint_layout = QVBoxLayout(hint_box)
        hint_layout.setContentsMargins(14, 10, 14, 10)
        hint_layout.addWidget(hint)
        root.addWidget(hint_box)

        # ---------- 按钮 ----------
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("完成")
        ok_btn.setObjectName("primary")
        ok_btn.clicked.connect(self.accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(ok_btn)
        root.addLayout(buttons)

        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, False)
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    # ---------------- 构建辅助 ----------------

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(12)

        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(QSize(32, 32)))
        icon.setFixedSize(QSize(32, 32))
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Snipdraw 设置")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("热键、保存位置与截图行为")
        subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        return header

    def _make_card(self, title: str) -> tuple[QFrame, QFormLayout]:
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        card_layout.addWidget(title_label)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        card_layout.addLayout(form)
        return card, form

    @staticmethod
    def _add_row(form: QFormLayout, text: str, widget: QWidget) -> None:
        label = QLabel(text)
        label.setMinimumWidth(104)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow(label, widget)

    @staticmethod
    def _add_check_row(form: QFormLayout, check: QCheckBox) -> None:
        spacer = QLabel("")
        spacer.setMinimumWidth(104)
        form.addRow(spacer, check)

    def _reapply_theme(self) -> None:
        self._pal = _palette(self.theme_combo.currentData())
        self.setStyleSheet(_build_stylesheet(self._pal))

    # ---------------- 交互 ----------------

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
            start_at_login=self.autostart_check.isChecked(),
            theme=self.theme_combo.currentData(),
            pin_limit=self._settings.pin_limit,
            annotation_color=self._settings.annotation_color,
            annotation_width=self._settings.annotation_width,
            font_size=self._settings.font_size,
        )
        return settings.normalized()
