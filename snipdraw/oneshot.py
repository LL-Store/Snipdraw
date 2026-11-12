"""无交互冒烟：截一张、裁一块、存盘、进剪贴板。

用来在没有鼠标可点的环境里验证「输出链路」是否通，不替代 overlay 的手动验收。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from .core.capture import CaptureService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="snipdraw oneshot", description="输出链路冒烟")
    parser.add_argument("--out", default="/tmp/snipdraw-oneshot.png")
    parser.add_argument("--ratio", type=float, default=0.4, help="裁剪边长占比")
    args = parser.parse_args(argv)

    app = QApplication([])
    frame = CaptureService().capture_one(QGuiApplication.primaryScreen())

    width, height = frame.image.width(), frame.image.height()
    side_w = int(width * args.ratio)
    side_h = int(height * args.ratio)
    rect = QRect((width - side_w) // 2, (height - side_h) // 2, side_w, side_h)
    image = frame.image.copy(rect)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ok = image.save(str(out), "PNG")
    QGuiApplication.clipboard().setImage(image)

    print(f"[oneshot] {out} {image.width()}x{image.height()} saved={ok} clipboard=yes")
    app.quit()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
