"""屏幕录制权限闸门的单元测试。"""

from __future__ import annotations

import pytest

from snipdraw.core.capture import CaptureError, CaptureService
from snipdraw.platform import macos_permission


def test_preflight_returns_bool():
    assert isinstance(macos_permission.screen_capture_granted(), bool)


def test_capture_refuses_without_permission(monkeypatch):
    """没授权时不许发起任何截屏调用——否则每试一次系统就弹一次框。"""
    monkeypatch.setattr(macos_permission, "screen_capture_granted", lambda: False)
    service = CaptureService()
    with pytest.raises(CaptureError) as error:
        service.capture_one(None)
    assert "屏幕录制" in str(error.value)


def test_capture_subject_wording():
    assert macos_permission.permission_subject()
