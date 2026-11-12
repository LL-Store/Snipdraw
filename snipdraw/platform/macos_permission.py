"""macOS 屏幕录制权限（TCC）：预检、请求、跳转系统设置。

为什么要单独封一层：
- 没授权时 `grabWindow` 不会报错，只会给你一张"没有窗口"的图；我们的兜底
  再走一次 QScreenCapture，系统就会再弹一次权限框。于是"每截一次问一次"。
  正确做法是启动时预检一次，没权限就不再试。
- 预检和请求是 CoreGraphics 的 C 接口，Qt 没有对等 API，只能用 ctypes。
"""

from __future__ import annotations

import ctypes
import subprocess
import sys

PRIVACY_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"


def _coregraphics():
    return ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )


def screen_capture_granted() -> bool:
    """当前进程是否已被授予"屏幕录制"。非 macOS 一律视为已授权。"""
    if sys.platform != "darwin":
        return True
    try:
        cg = _coregraphics()
        cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        return bool(cg.CGPreflightScreenCaptureAccess())
    except Exception:
        # 接口异常时不要拦着用户，让真正的截图去判断
        return True


def request_screen_capture() -> bool:
    """弹一次系统的授权框；已授权时直接返回 True，不会再弹。"""
    if sys.platform != "darwin":
        return True
    try:
        cg = _coregraphics()
        cg.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
        return bool(cg.CGRequestScreenCaptureAccess())
    except Exception:
        return screen_capture_granted()


def open_privacy_settings() -> None:
    if sys.platform != "darwin":
        return
    subprocess.run(["open", PRIVACY_PANE], check=False)


def permission_subject() -> str:
    """告诉用户该在列表里勾选谁。

    打包成 .app 后是 Snipdraw 自己；从源码 `python -m snipdraw` 跑时，
    系统记的是终端/Python，这本身就会让人以为"明明给过了"。
    """
    return "Snipdraw" if getattr(sys, "frozen", False) else "你的终端 / Python"
