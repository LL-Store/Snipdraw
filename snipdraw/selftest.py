"""截屏自测：把每块屏各抓一张存盘，并核对逻辑尺寸 × 缩放 = 实际像素。

这是唯一能自动验证“截屏到底对不对”的手段，改截屏代码后要先跑它。
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from .core.capture import CaptureService, CaptureError, looks_blank


def run(out_dir: Path) -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    service = CaptureService()
    try:
        frames = service.capture_all()
    except CaptureError as error:
        print(f"[失败] {error}")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    expected = 0
    actual = 0
    for index, frame in enumerate(frames):
        screen = frame.screen
        name = f"{index:02d}_{screen.name.replace('/', '_')}"
        path = out_dir / f"{name}_{frame.image.width()}x{frame.image.height()}.png"
        frame.image.save(str(path), "PNG")

        expected += screen.physical_size[0] * screen.physical_size[1]
        actual += frame.image.width() * frame.image.height()
        blank = looks_blank(frame.image)

        print(
            f"[{index}] {screen.name} 逻辑={screen.width}x{screen.height} "
            f"@{screen.x},{screen.y} dpr={screen.dpr:g} "
            f"图片={frame.image.width()}x{frame.image.height()} "
            f"scale={frame.scale_x:.3f} 后端={frame.method} "
            f"整块同色={'是' if blank else '否'}"
        )
        print(f"     -> {path}")

    for note in service.notes:
        print(f"[降级] {note}")

    if expected and abs(actual - expected) > expected * 0.02:
        print(f"[警告] 像素总量与逻辑尺寸×dpr 相差较大：期望 {expected}，实际 {actual}")
        return 2

    print(f"[完成] 共 {len(frames)} 块屏，像素总量 {actual}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="snipdraw.selftest", description="截屏自测")
    parser.add_argument(
        "--out",
        default=str(Path(tempfile.gettempdir()) / "snipdraw-selftest"),
        help="截图输出目录",
    )
    args = parser.parse_args(argv)
    return run(Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
