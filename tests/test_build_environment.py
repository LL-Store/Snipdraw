"""打包脚本的环境预检测试：解释器不对时不该抛一堆 traceback。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

BUILD_PY = Path(__file__).resolve().parent.parent / "packaging" / "build.py"


def load_build_module():
    spec = importlib.util.spec_from_file_location("snipdraw_build", BUILD_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load_build_module()


def test_supported_versions_have_no_problem():
    assert build.interpreter_problems((3, 10), True, True) == []
    assert build.interpreter_problems((3, 13), True, True) == []


def test_old_interpreter_is_reported():
    problems = build.interpreter_problems((3, 9), True, True)
    assert len(problems) == 1
    assert "3.10" in problems[0]


def test_too_new_interpreter_is_reported():
    problems = build.interpreter_problems((3, 14), True, True)
    assert problems and "3.14" in problems[0]


def test_missing_dependencies_are_reported():
    problems = build.interpreter_problems((3, 10), False, False)
    assert any("PyInstaller" in item for item in problems)
    assert any("PySide6" in item for item in problems)


def test_choose_fallback_skips_unusable_candidates(tmp_path):
    good = tmp_path / "good.exe"
    bad = tmp_path / "bad.exe"
    good.write_text("", encoding="utf-8")
    bad.write_text("", encoding="utf-8")
    assert build.choose_fallback([bad, good], lambda path: path == good) == good


def test_choose_fallback_returns_none_when_nothing_works(tmp_path):
    assert build.choose_fallback([tmp_path / "missing.exe"], lambda path: True) is None


def test_venv_candidates_cover_both_layouts():
    names = [path.as_posix() for path in build.venv_interpreters(Path("/proj"))]
    assert any(name.endswith(".venv/Scripts/python.exe") for name in names)
    assert any(name.endswith(".venv/bin/python") for name in names)


def test_same_interpreter_matches_equivalent_paths(tmp_path):
    # 应用商店版的 sys.executable 是应用执行别名，Path.resolve() 会抛 WinError 1920，
    # 所以比较必须走 abspath/normcase 而不是 resolve
    assert build._same_interpreter(tmp_path / "sub" / ".." / "python.exe", tmp_path / "python.exe")
    assert not build._same_interpreter(tmp_path / "python.exe", tmp_path / "other-python.exe")
