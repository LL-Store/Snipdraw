"""开机自启动：统一接口 + 平台后端。

- macOS: ``~/Library/LaunchAgents/<label>.plist``，``RunAtLoad``
- Windows: 当前用户注册表 ``Run`` 键下写一个字符串值
- Linux: ``~/.config/autostart/snipdraw.desktop``
- 其它平台: 空实现，``is_supported()`` 为 False，开关静默无效

写失败（权限、目录不可写）不阻断主流程：自启动只是临时偏好，不该让截图功能报错。
"""

from __future__ import annotations

import sys
from pathlib import Path

LABEL = "com.llstore.snipdraw"
APP_NAME = "Snipdraw"


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _program_arguments() -> list[str]:
    """开机后用来拉起本程序的命令。

    打包后的可执行文件直接运行；开发态用解释器跑 ``-m snipdraw``。
    """
    if _frozen():
        return [sys.executable]
    return [sys.executable, "-m", "snipdraw"]


def _quoted(cmd: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in cmd)


def is_supported() -> bool:
    return (
        sys.platform == "darwin"
        or sys.platform == "win32"
        or sys.platform.startswith("linux")
    )


# ---------------- macOS ----------------


def _darwin_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _darwin_plist_text(args: list[str]) -> str:
    items = "\n".join(f"  <string>{arg}</string>" for arg in args)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "  <key>Label</key>\n"
        f"  <string>{LABEL}</string>\n"
        "  <key>ProgramArguments</key>\n"
        "  <array>\n"
        f"{items}\n"
        "  </array>\n"
        "  <key>RunAtLoad</key>\n"
        "  <true/>\n"
        "</dict>\n"
        "</plist>\n"
    )


# ---------------- Windows ----------------


def _win_reg_key() -> str:
    return r"Software\Microsoft\Windows\CurrentVersion\Run"


# ---------------- Linux ----------------


def _linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / "snipdraw.desktop"


def _linux_desktop_text(args: list[str]) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Exec={_quoted(args)}\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


# ---------------- 统一接口 ----------------


def is_enabled() -> bool:
    """当前是否已注册为开机自启；读不到一律按未启用处理。"""
    try:
        if sys.platform == "darwin":
            return _darwin_plist_path().exists()
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _win_reg_key()) as key:
                winreg.QueryValueEx(key, APP_NAME)
            return True
        if sys.platform.startswith("linux"):
            return _linux_desktop_path().exists()
    except OSError:
        return False
    return False


def set_enabled(enabled: bool) -> None:
    """按开关注册 / 注销自启动；不支持的平台直接忽略。"""
    if not is_supported():
        return
    args = _program_arguments()
    try:
        if sys.platform == "darwin":
            path = _darwin_plist_path()
            if enabled:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(_darwin_plist_text(args), encoding="utf-8")
            elif path.exists():
                path.unlink()
        elif sys.platform == "win32":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _win_reg_key(), 0, winreg.KEY_SET_VALUE
            ) as key:
                if enabled:
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _quoted(args))
                else:
                    try:
                        winreg.DeleteValue(key, APP_NAME)
                    except FileNotFoundError:
                        pass
        elif sys.platform.startswith("linux"):
            path = _linux_desktop_path()
            if enabled:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(_linux_desktop_text(args), encoding="utf-8")
            elif path.exists():
                path.unlink()
    except OSError:
        # 写不进去（权限 / 目录缺失）不影响截图主流程
        pass
