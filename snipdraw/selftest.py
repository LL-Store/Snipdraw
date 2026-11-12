"""截屏自测：把每块屏各抓一张存盘，并核对逻辑尺寸 × 缩放 = 实际像素。

这是唯一能自动验证“截屏到底对不对”的手段，改截屏代码后要先跑它。
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QImage

from .core.capture import CaptureService, CaptureError, Frame, looks_blank

# Windows 文件名里不能出现的字符（`|` 尤其常见：QScreen.name() 在 Windows 上
# 会返回 `|DELL E1715S` 这种以竖线开头的名字）
WINDOWS_ILLEGAL = '<>:"/\\|?*'
_ILLEGAL = set(WINDOWS_ILLEGAL) | {chr(code) for code in range(32)}


def safe_filename(text: str) -> str:
    """把屏幕名压成跨平台合法的文件名片段。

    直接拿屏幕名当文件名会让 QImage.save 在这类名字上静默失败（返回 False 而
    不抛异常），于是自测打印“完成”却一张图都没有，所以这里逐字符替换。
    """
    cleaned = "".join("_" if char in _ILLEGAL else char for char in text)
    # Windows 会吃掉文件名尾部的点和空格，留着就和实际落盘的名字对不上
    cleaned = cleaned.rstrip(" .")
    return cleaned or "screen"


def frame_filename(index: int, frame: Frame) -> str:
    """单帧的文件名：序号 + 屏幕名 + 像素尺寸。"""
    image = frame.image
    return f"{index:02d}_{safe_filename(frame.screen.name)}_{image.width()}x{image.height()}.png"


def save_frame(image: QImage, path: Path) -> bool:
    """落盘并如实返回结果；写不出来要报出来，不能当成功。"""
    saved = bool(image.save(str(path), "PNG"))
    if not saved:
        print(f"[失败] 写不出 {path}", file=sys.stderr)
    return saved


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
    failed = 0
    for index, frame in enumerate(frames):
        screen = frame.screen
        path = out_dir / frame_filename(index, frame)
        blank = looks_blank(frame.image)

        print(
            f"[{index}] {screen.name} 逻辑={screen.width}x{screen.height} "
            f"@{screen.x},{screen.y} dpr={screen.dpr:g} "
            f"图片={frame.image.width()}x{frame.image.height()} "
            f"scale={frame.scale_x:.3f} 后端={frame.method} "
            f"整块同色={'是' if blank else '否'}"
        )
        if save_frame(frame.image, path):
            print(f"     -> {path}")
        else:
            failed += 1

        expected += screen.physical_size[0] * screen.physical_size[1]
        actual += frame.image.width() * frame.image.height()

    for note in service.notes:
        print(f"[降级] {note}")

    if failed:
        print(f"[失败] {failed} 张图没写出来，检查输出目录：{out_dir}")
        return 1

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
