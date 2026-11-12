"""程序内绘制图标：不往仓库塞二进制图片。"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def draw_glyph(size: int = 64, color: QColor | None = None) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = color or QColor(0, 0, 0)

    pen = QPen(color, size * 0.09)
    painter.setPen(pen)
    inset = size * 0.14
    corner = size * 0.22
    box = QRectF(inset, inset, size - inset * 2, size - inset * 2)
    # 四个括角，像一个取景框
    painter.drawLine(box.topLeft(), box.topLeft() + QRectF(0, 0, corner, 0).bottomRight())
    painter.drawLine(box.topLeft(), box.topLeft() + QRectF(0, 0, 0, corner).bottomRight())
    painter.drawLine(box.topRight(), box.topRight() - QRectF(corner, 0, 0, 0).bottomRight())
    painter.drawLine(box.topRight(), box.topRight() + QRectF(0, 0, 0, corner).bottomRight())
    painter.drawLine(box.bottomLeft(), box.bottomLeft() + QRectF(corner, 0, 0, 0).bottomRight())
    painter.drawLine(box.bottomLeft(), box.bottomLeft() - QRectF(0, corner, 0, 0).bottomRight())
    painter.drawLine(box.bottomRight(), box.bottomRight() - QRectF(corner, 0, 0, 0).bottomRight())
    painter.drawLine(box.bottomRight(), box.bottomRight() - QRectF(0, corner, 0, 0).bottomRight())

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    radius = size * 0.12
    painter.drawEllipse(QRectF(size * 0.5 - radius, size * 0.5 - radius, radius * 2, radius * 2))
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    """彩色版本，用于窗口/通知。

    颜色取品牌色（`assets/Snipdraw.icns` 里那道红笔的 #ff3b30），
    跟应用图标保持同一个识别点；打包后的 Finder/Dock 图标由 .icns 提供，
    这里只负责运行期内存里的 QIcon。
    """
    icon = QIcon()
    for size in (32, 64, 128, 256):
        icon.addPixmap(draw_glyph(size, QColor("#ff3b30")))
    return icon


def tray_icon() -> QIcon:
    """菜单栏模板图标：macOS 会自动跟随明暗主题反色。"""
    icon = QIcon()
    for size in (16, 32, 64):
        icon.addPixmap(draw_glyph(size, QColor(0, 0, 0)))
    icon.setIsMask(True)
    return icon
