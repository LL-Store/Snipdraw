"""标注图元。

坐标一律用**物理像素**（图像坐标系），绘制时按 `unit = 物理/逻辑` 放大线宽与字号，
所以屏幕上的观感和导出图里的粗细完全一致。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF


@dataclass
class Style:
    color: QColor = field(default_factory=lambda: QColor("#ff3b30"))
    width: float = 3.0
    font_size: int = 16

    def copy(self) -> "Style":
        return Style(QColor(self.color), float(self.width), int(self.font_size))


class Shape:
    kind = "shape"

    def __init__(self, style: Style) -> None:
        self.style = style

    def paint(self, painter: QPainter, base: QImage, unit: float) -> None:
        raise NotImplementedError

    def bounds(self) -> QRectF:
        raise NotImplementedError

    def hit(self, point: QPointF, tolerance: float = 6.0) -> bool:
        return self.bounds().adjusted(-tolerance, -tolerance, tolerance, tolerance).contains(point)

    def translated(self, delta: QPointF) -> "Shape":
        raise NotImplementedError

    def _pen(self, unit: float, alpha: int = 255) -> QPen:
        color = QColor(self.style.color)
        color.setAlpha(alpha)
        pen = QPen(color, max(1.0, self.style.width * unit))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen


class RectShape(Shape):
    kind = "rect"

    def __init__(self, rect: QRectF, style: Style) -> None:
        super().__init__(style)
        self.rect = rect

    def paint(self, painter: QPainter, base: QImage, unit: float) -> None:
        painter.setPen(self._pen(unit))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect)

    def bounds(self) -> QRectF:
        return self.rect.normalized()

    def translated(self, delta: QPointF) -> "RectShape":
        return RectShape(self.rect.translated(delta), self.style.copy())


class EllipseShape(Shape):
    kind = "ellipse"

    def __init__(self, rect: QRectF, style: Style) -> None:
        super().__init__(style)
        self.rect = rect

    def paint(self, painter: QPainter, base: QImage, unit: float) -> None:
        painter.setPen(self._pen(unit))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self.rect)

    def bounds(self) -> QRectF:
        return self.rect.normalized()

    def translated(self, delta: QPointF) -> "EllipseShape":
        return EllipseShape(self.rect.translated(delta), self.style.copy())


class ArrowShape(Shape):
    kind = "arrow"

    def __init__(self, start: QPointF, end: QPointF, style: Style) -> None:
        super().__init__(style)
        self.start = start
        self.end = end

    def paint(self, painter: QPainter, base: QImage, unit: float) -> None:
        start, end = self.start, self.end
        dx, dy = end.x() - start.x(), end.y() - start.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return
        width = max(1.0, self.style.width * unit)
        head = max(width * 4.0, 9.0 * unit)
        ux, uy = dx / length, dy / length

        # 箭杆缩到箭头顶部，避免线头从三角形里穿出来
        shaft_end = QPointF(end.x() - ux * head * 0.85, end.y() - uy * head * 0.85)
        painter.setPen(self._pen(unit))
        painter.drawLine(start, shaft_end)

        half = head * 0.42
        base_point = QPointF(end.x() - ux * head, end.y() - uy * head)
        left = QPointF(base_point.x() - uy * half, base_point.y() + ux * half)
        right = QPointF(base_point.x() + uy * half, base_point.y() - ux * half)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.style.color)
        painter.drawPolygon(QPolygonF([end, left, right]))

    def bounds(self) -> QRectF:
        return QRectF(self.start, self.end).normalized()

    def hit(self, point: QPointF, tolerance: float = 6.0) -> bool:
        return _distance_to_segment(point, self.start, self.end) <= tolerance

    def translated(self, delta: QPointF) -> "ArrowShape":
        return ArrowShape(self.start + delta, self.end + delta, self.style.copy())


class PenShape(Shape):
    kind = "pen"

    def __init__(self, points: list[QPointF], style: Style) -> None:
        super().__init__(style)
        self.points = list(points)

    def paint(self, painter: QPainter, base: QImage, unit: float) -> None:
        if not self.points:
            return
        painter.setPen(self._pen(unit))
        if len(self.points) == 1:
            painter.drawPoint(self.points[0])
            return
        path = QPainterPath(self.points[0])
        for point in self.points[1:]:
            path.lineTo(point)
        painter.drawPath(path)

    def bounds(self) -> QRectF:
        if not self.points:
            return QRectF()
        rect = QRectF(self.points[0], self.points[0])
        for point in self.points[1:]:
            rect = rect.united(QRectF(point, point))
        return rect

    def translated(self, delta: QPointF) -> "PenShape":
        return PenShape([p + delta for p in self.points], self.style.copy())


class HighlightShape(PenShape):
    kind = "highlight"

    def paint(self, painter: QPainter, base: QImage, unit: float) -> None:
        if len(self.points) < 2:
            return
        pen = self._pen(unit, alpha=110)
        pen.setWidthF(max(3.0, self.style.width * unit * 2.4))
        painter.setPen(pen)
        path = QPainterPath(self.points[0])
        for point in self.points[1:]:
            path.lineTo(point)
        painter.drawPath(path)

    def translated(self, delta: QPointF) -> "HighlightShape":
        return HighlightShape([p + delta for p in self.points], self.style.copy())


class TextShape(Shape):
    kind = "text"

    def __init__(self, position: QPointF, text: str, style: Style) -> None:
        super().__init__(style)
        self.position = position
        self.text = text

    def _font(self, unit: float) -> QFont:
        font = QFont()
        font.setPixelSize(max(6, int(round(self.style.font_size * unit))))
        return font

    def bounds(self) -> QRectF:
        # 用 1.0 单位估算，再按字号放大；只要够用来做命中与移动
        lines = self.text.split("\n")
        width = max(len(line) for line in lines) if lines else 1
        height = len(lines) * self.style.font_size * 1.35
        return QRectF(
            self.position.x(),
            self.position.y(),
            width * self.style.font_size * 0.72,
            height,
        )

    def paint(self, painter: QPainter, base: QImage, unit: float) -> None:
        painter.setFont(self._font(unit))
        painter.setPen(QColor(self.style.color))
        metrics = painter.fontMetrics()
        x = self.position.x()
        y = self.position.y() + metrics.ascent()
        for line in self.text.split("\n"):
            painter.drawText(QPointF(x, y), line)
            y += metrics.lineSpacing()

    def hit(self, point: QPointF, tolerance: float = 6.0) -> bool:
        return self.bounds().adjusted(-tolerance, -tolerance, tolerance, tolerance).contains(point)

    def translated(self, delta: QPointF) -> "TextShape":
        return TextShape(self.position + delta, self.text, self.style.copy())


class MosaicShape(Shape):
    """马赛克不烘像素：每次重绘都从原图重新取样，所以移动/撤销都正确。"""

    kind = "mosaic"

    def __init__(self, rect: QRectF, style: Style, block: float = 8.0) -> None:
        super().__init__(style)
        self.rect = rect
        self.block = block

    def paint(self, painter: QPainter, base: QImage, unit: float) -> None:
        target = self.rect.normalized().intersected(QRectF(0, 0, base.width(), base.height()))
        if target.width() < 1 or target.height() < 1:
            return
        block_px = max(2, int(round(self.block * unit)))
        source = base.copy(target.toAlignedRect())
        columns = max(1, int(target.width()) // block_px)
        rows = max(1, int(target.height()) // block_px)
        small = source.scaled(
            columns,
            rows,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(target, small)
        painter.restore()

    def bounds(self) -> QRectF:
        return self.rect.normalized()

    def translated(self, delta: QPointF) -> "MosaicShape":
        return MosaicShape(self.rect.translated(delta), self.style.copy(), self.block)


class BadgeShape(Shape):
    """①②③ 那种序号圆标。"""

    kind = "badge"

    def __init__(self, center: QPointF, number: int, style: Style) -> None:
        super().__init__(style)
        self.center = center
        self.number = number

    @property
    def radius(self) -> float:
        return self.style.font_size * 0.95

    def paint(self, painter: QPainter, base: QImage, unit: float) -> None:
        radius = self.radius
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.style.color)
        painter.drawEllipse(self.center, radius, radius)

        font = QFont()
        font.setPixelSize(max(6, int(self.style.font_size * 0.95)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        rect = QRectF(
            self.center.x() - radius,
            self.center.y() - radius,
            radius * 2,
            radius * 2,
        )
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self.number))

    def bounds(self) -> QRectF:
        r = self.radius
        return QRectF(self.center.x() - r, self.center.y() - r, r * 2, r * 2)

    def hit(self, point: QPointF, tolerance: float = 6.0) -> bool:
        dx = point.x() - self.center.x()
        dy = point.y() - self.center.y()
        return math.hypot(dx, dy) <= self.radius + tolerance

    def translated(self, delta: QPointF) -> "BadgeShape":
        return BadgeShape(self.center + delta, self.number, self.style.copy())


def _distance_to_segment(point: QPointF, a: QPointF, b: QPointF) -> float:
    ax, ay = a.x(), a.y()
    bx, by = b.x(), b.y()
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(point.x() - ax, point.y() - ay)
    t = ((point.x() - ax) * dx + (point.y() - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(point.x() - (ax + t * dx), point.y() - (ay + t * dy))
