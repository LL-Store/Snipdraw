"""Windows 安装包（Inno Setup）生成逻辑的测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

BUILD_PY = Path(__file__).resolve().parent.parent / "packaging" / "build.py"


def load_build_module():
    spec = importlib.util.spec_from_file_location("snipdraw_build_installer", BUILD_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load_build_module()


def test_installer_name_carries_version():
    assert build.installer_name("0.1.0") == "Snipdraw-0.1.0-windows-x64-setup.exe"
    assert build.installer_name("1.2.3").startswith("Snipdraw-1.2.3-")


def test_installer_command_passes_version_and_sources():
    command = build.installer_command(Path("ISCC.exe"), "0.1.0")
    assert command[0] == "ISCC.exe"
    assert "/DAppVersion=0.1.0" in command
    assert any(part.startswith("/DSourceDir=") for part in command)
    assert any(part.startswith("/DOutputDir=") for part in command)
    assert command[-1].endswith("installer.iss")


def test_iscc_candidates_include_per_user_install():
    paths = [path.as_posix() for path in build.iscc_candidates()]
    # winget 默认装到当前用户目录，这里必须能找到
    assert any(path.endswith("Inno Setup 6/ISCC.exe") for path in paths)
    assert any(path.startswith("C:/Program Files") for path in paths)
