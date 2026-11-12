"""overlay 渲染自测：摆好选区、加几个样例标注，把带 overlay 的屏幕拍下来。

没有真人在旁边点，就这样验证“画得对不对”：overlay 显示后拍一张屏，
拍到的图里包含 overlay 自己（macOS 的 grabWindow 会连本进程窗口一起拍）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QTimer
from PySide6.QtGui import QGuiApplication, QColor
from PySide6.QtWidgets import QApplication

from .core.capture import CaptureService
from .ui.overlay.shapes import (
    ArrowShape,
    BadgeShape,
    EllipseShape,
    MosaicShape,
    RectShape,
    Style,
    TextShape,
)
from .ui.overlay.window import OverlayWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="snipdraw demo", description="overlay 渲染自测")
    parser.add_argument("--out", default="/tmp/snipdraw-demo.png")
    args = parser.parse_args(argv)

    app = QApplication([])
    frames = CaptureService().capture_all()
    frame = frames[0]

    width, height = frame.image.width(), frame.image.height()
    rect = QRectF(width * 0.12, height * 0.16, width * 0.52, height * 0.46)
    cursor = QPointF(rect.right() - 40, rect.bottom() - 30)

    window = OverlayWindow(frame)
    window.set_preview(rect, cursor)
    window.show_on_screen()
    window.enter_annotating()

    style = Style(QColor("#ff3b30"), 3.0, 16)
    inner = rect.adjusted(width * 0.02, height * 0.03, -width * 0.02, -height * 0.03)
    window.model.add(RectShape(QRectF(inner.left(), inner.top(), inner.width() * 0.55, inner.height() * 0.5), style))
    window.model.add(EllipseShape(QRectF(inner.left() + 40, inner.top() + 40, 260, 200), Style(QColor("#ffcc00"), 3.0, 16)))
    window.model.add(
        ArrowShape(
            QPointF(inner.left() + 20, inner.bottom() - 40),
            QPointF(inner.left() + 320, inner.top() + 150),
            Style(QColor("#2f7cf6"), 3.0, 16),
        )
    )
    window.model.add(MosaicShape(QRectF(inner.right() - 320, inner.top() + 20, 280, 180), style, 8.0))
    window.model.add(BadgeShape(QPointF(inner.right() - 120, inner.bottom() - 80), 1, Style(QColor("#34c759"), 3.0, 20)))
    window.model.add(TextShape(QPointF(inner.left() + 10, inner.bottom() - 90), "标注文字示例", Style(QColor("#ffffff"), 3.0, 18)))

    def shoot() -> None:
        # 必须拍 overlay 所在的那块屏；多屏时 primaryScreen 不一定是它
        target = None
        for candidate in QGuiApplication.screens():
            if candidate.name() == frame.screen.name:
                target = candidate
                break
        if target is None:
            target = QGuiApplication.primaryScreen()
        pixmap = target.grabWindow(0)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(str(out), "PNG")
        print(
            f"[demo] {out}  {pixmap.width()}x{pixmap.height()}  "
            f"screen={frame.screen.name}  shapes={len(window.model.shapes)}"
        )
        window.hide()
        app.quit()

    QTimer.singleShot(800, shoot)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
