"""自测工具的文件名与落盘测试：Windows 上屏幕名带 `|` 时必须仍能存图。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage

from snipdraw.core.capture import Frame
from snipdraw.core.geometry import ScreenGeometry
from snipdraw.selftest import WINDOWS_ILLEGAL, frame_filename, safe_filename, save_frame


def test_pipe_prefixed_screen_name_yields_legal_filename():
    # 真实机器上 QScreen.name() 会返回 "|DELL E1715S" 这种以竖线开头的名字，
    # 竖线在 Windows 上是非法字符，直接用会导致 QImage.save 静默失败。
    assert safe_filename("|DELL E1715S") == "_DELL E1715S"


def test_every_illegal_character_is_replaced():
    cleaned = safe_filename('a<b>c:d"e/f\\g|h?i*j')
    assert cleaned == "a_b_c_d_e_f_g_h_i_j"
    assert not (set(cleaned) & set(WINDOWS_ILLEGAL))


def test_trailing_dots_and_spaces_are_stripped():
    # Windows 会丢掉尾部的点与空格，留着就会和期望的文件名对不上
    assert safe_filename("monitor. ") == "monitor"


def test_blank_name_falls_back():
    assert safe_filename("") == "screen"
    assert safe_filename("   ") == "screen"


def test_frame_filename_is_legal_and_descriptive():
    frame = Frame(
        image=QImage(1280, 1024, QImage.Format.Format_RGB32),
        screen=ScreenGeometry("|DELL E1715S", 0, 0, 1280, 1024, 1.0),
        method="fake",
        captured_at=0.0,
    )
    name = frame_filename(0, frame)
    assert name == "00__DELL E1715S_1280x1024.png"
    assert not (set(name) & set(WINDOWS_ILLEGAL))


def test_save_frame_reports_success_and_failure(tmp_path):
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0xFF0000)
    assert save_frame(image, tmp_path / "ok.png") is True
    # 父目录不存在 -> 写不进去，必须如实返回 False 而不是假装成功
    assert save_frame(image, tmp_path / "missing" / "bad.png") is False
