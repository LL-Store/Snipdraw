"""开机自启动：纯文本生成与默认行为的单元测试。

注册表 / LaunchAgent / desktop 文件的真实写入依赖平台与用户目录，
这里只校验生成内容的结构；写路径在 set_enabled 内已吞掉 OSError。
"""

from __future__ import annotations

import os
import sys

from snipdraw.platform import autostart


def test_quoted_adds_quotes_for_spaces():
    assert autostart._quoted(["/usr/bin/python3", "-m", "snipdraw"]) == \
        "/usr/bin/python3 -m snipdraw"
    assert autostart._quoted(["/Applications/My App/snipdraw"]) == \
        '"/Applications/My App/snipdraw"'


def test_darwin_plist_contains_label_and_run_at_load():
    text = autostart._darwin_plist_text(["/Applications/Snipdraw.app/Contents/MacOS/snipdraw"])
    assert autostart.LABEL in text
    assert "RunAtLoad" in text
    assert "<true/>" in text
    assert "ProgramArguments" in text
    assert "/Applications/Snipdraw.app/Contents/MacOS/snipdraw" in text


def test_linux_desktop_contains_exec_and_name():
    text = autostart._linux_desktop_text(["/usr/bin/snipdraw"])
    assert "Type=Application" in text
    assert f"Name={autostart.APP_NAME}" in text
    assert "Exec=/usr/bin/snipdraw" in text


def test_set_enabled_does_not_raise_on_unsupported_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert autostart.is_supported() is False
    autostart.set_enabled(True)
    autostart.set_enabled(False)
    assert autostart.is_enabled() is False


def test_program_arguments_dev_mode(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    args = autostart._program_arguments()
    assert args[0] == sys.executable
    assert args[1:] == ["-m", "snipdraw"]
