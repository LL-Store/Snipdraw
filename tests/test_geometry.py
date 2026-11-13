"""坐标换算与配置校验的单元测试（不需要真实屏幕）。"""

from __future__ import annotations

import pytest

from snipdraw.core.geometry import (
    ScreenGeometry,
    axis_scale,
    containing,
    global_to_local,
    global_to_physical,
    local_to_physical,
    physical_to_local,
    rect_union,
    virtual_bounds,
)
from snipdraw.core.settings import Settings


def screens():
    # 典型双屏：主屏在左（Retina 2x），副屏在右侧且 y 为负（macOS 常见）
    return [
        ScreenGeometry("built-in", 0, 0, 1470, 956, 2.0),
        ScreenGeometry("external", 1470, -400, 1920, 1080, 1.0),
    ]


def test_containing_picks_screen():
    assert containing(screens(), 100, 100).name == "built-in"
    assert containing(screens(), 2000, 100).name == "external"


def test_containing_falls_back_to_nearest():
    # 落在两屏之间的空隙里，也要给出一块屏而不是 None
    assert containing(screens(), 1470, 2000) is not None


def test_physical_conversion_retina():
    screen = screens()[0]
    assert local_to_physical(screen, 100, 50) == (200.0, 100.0)
    assert physical_to_local(screen, 200, 100) == (100.0, 50.0)


def test_global_to_local_handles_negative_origin():
    screen = screens()[1]
    assert global_to_local(screen, 1500, -380) == (30.0, 20.0)
    assert global_to_physical(1500, -380, screen) == (30.0, 20.0)


def test_virtual_bounds_covers_negative_screen():
    assert virtual_bounds(screens()) == (0, -400, 3390, 1356)


def test_axis_scale_uses_real_image_size():
    # 图像实际像素与 dpr 不完全一致时，要按真实尺寸反推比例
    assert axis_scale(1470, 2940) == pytest.approx(2.0)
    assert axis_scale(1470, 2205) == pytest.approx(1.5)
    assert axis_scale(0, 0) == 1.0


def test_rect_union():
    assert rect_union((0, 0, 10, 10), (20, 5, 10, 20)) == (0, 0, 30, 25)


def test_settings_normalized_clamps():
    settings = Settings(delay_seconds=999, jpeg_quality=0, image_format="bmp").normalized()
    assert settings.delay_seconds == 30
    assert settings.jpeg_quality == 1
    assert settings.image_format == "png"


def test_settings_from_dict_ignores_unknown_and_keeps_extra():
    settings = Settings.from_dict({"hotkey": "F1", "delay_seconds": 5, "unknown_key": 1})
    assert settings.hotkey == "F1"
    assert settings.delay_seconds == 5
    assert settings.extra == {"unknown_key": 1}


def test_settings_empty_hotkey_falls_back():
    assert Settings(hotkey="   ").normalized().hotkey == "F1"


def test_settings_theme_clamps():
    assert Settings(theme="neon").normalized().theme == "system"
    assert Settings(theme="dark").normalized().theme == "dark"
    assert Settings(theme="light").normalized().theme == "light"


def test_settings_autostart_default_on_and_preserved():
    assert Settings().start_at_login is True
    off = Settings(start_at_login=False).normalized()
    assert off.start_at_login is False
    on = Settings(start_at_login=False, extra={}).normalized()
    assert on.start_at_login is False

def test_settings_hotkey_can_be_disabled():
    settings = Settings.from_dict({"hotkey_enabled": False})
    assert settings.hotkey_enabled is False
    assert settings.to_dict()["hotkey_enabled"] is False
