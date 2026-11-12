#!/usr/bin/env python3
"""一条命令出包：PyInstaller 构建 -> 打压缩包 -> 打印体积。

用法（在项目根目录）：
    python packaging/build.py               # 构建 + 压缩 + dmg
    python packaging/build.py --only-build    # 只构建，不打包
    python packaging/build.py --only-package  # 跳过构建，用现有 dist 重新打包

产物：
    dist/Snipdraw.app                          macOS 应用本体
    dist/Snipdraw/                             Linux / Windows 目录
    release/Snipdraw-<版本>-macos-<arch>.dmg   macOS 安装包（拖进 Applications 即可）
    release/Snipdraw-<版本>-windows-x64-setup.exe  Windows 安装包（当前用户安装，免管理员）
    release/Snipdraw-<版本>-<平台>.zip|tar.gz  压缩分发（Windows/Linux，以及 macOS 备选）
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = Path(__file__).resolve().parent / "snipdraw.spec"
BUILD_DIR = ROOT / "build" / "pyinstaller"
DIST_DIR = ROOT / "dist"
RELEASE_DIR = ROOT / "release"
INSTALLER_ISS = Path(__file__).resolve().parent / "installer.iss"

MIN_PYTHON = (3, 10)
# PySide6 的 wheel 还没跟上 3.14，pyproject.toml 里限的是 <3.14
MAX_PYTHON_EXCLUSIVE = (3, 14)


def interpreter_problems(
    version: tuple[int, int], has_pyinstaller: bool, has_pyside6: bool
) -> list[str]:
    """列出当前解释器不能打包的原因；返回空列表表示可以直接构建。"""
    problems = []
    if version < MIN_PYTHON:
        problems.append(
            f"Python 太旧：当前 {version[0]}.{version[1]}，"
            f"打包需要 ≥{MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
        )
    elif version >= MAX_PYTHON_EXCLUSIVE:
        problems.append(
            f"Python 太新：当前 {version[0]}.{version[1]}，PySide6 的 wheel 还没跟上 "
            f"{MAX_PYTHON_EXCLUSIVE[0]}.{MAX_PYTHON_EXCLUSIVE[1]}"
        )
    if not has_pyinstaller:
        problems.append("缺少 PyInstaller（在开发依赖 .[dev] 里）")
    if not has_pyside6:
        problems.append("缺少 PySide6（同上，装 .[dev] 即可）")
    return problems


def venv_interpreters(root: Path = ROOT) -> list[Path]:
    """项目自带 venv 里可能的解释器路径（Windows 与 Unix 两种布局）。"""
    return [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ]


def choose_fallback(candidates: list[Path], probe) -> Path | None:
    """挑第一个「存在且 probe 通过」的解释器。"""
    for candidate in candidates:
        if not candidate.exists():
            continue
        if probe(candidate):
            return candidate
    return None


def _same_interpreter(left: Path, right: Path) -> bool:
    """比较两个解释器路径。不能用 `Path.resolve()`：应用商店版 Python 的
    `sys.executable` 是应用执行别名（reparse point），resolve 会抛 WinError 1920。
    """
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
        os.path.abspath(str(right))
    )


def _can_build(path: Path) -> bool:
    """探一下子解释器：既能 import 两个依赖，版本也在支持区间。"""
    probe = (
        "import sys, PyInstaller, PySide6; "
        f"sys.exit(0 if sys.version_info[:2] >= {MIN_PYTHON!r} else 1)"
    )
    result = subprocess.run([str(path), "-c", probe], capture_output=True, check=False)
    return result.returncode == 0


def ensure_environment() -> None:
    """解释器不适合打包时，先试着切到项目 venv，切不成就给出能照抄的命令。

    起因：Windows 上 `python` 常常落到应用商店版 3.9（没有 PyInstaller / PySide6），
    直接跑本脚本只会抛一句 CalledProcessError，看不出该修哪里。
    """
    problems = interpreter_problems(
        sys.version_info[:2],
        importlib.util.find_spec("PyInstaller") is not None,
        importlib.util.find_spec("PySide6") is not None,
    )
    if not problems:
        return

    fallback = choose_fallback(venv_interpreters(), _can_build)
    if fallback is not None and not _same_interpreter(Path(sys.executable), fallback):
        print(f"[env] 当前解释器不能打包：{sys.executable}")
        for problem in problems:
            print(f"[env]   - {problem}")
        print(f"[env] 改用项目 venv 继续：{fallback}")
        raise SystemExit(
            subprocess.run(
                [str(fallback), str(Path(__file__).resolve()), *sys.argv[1:]]
            ).returncode
        )

    print("[env] 打包环境不满足要求：", file=sys.stderr)
    for problem in problems:
        print(f"[env]   - {problem}", file=sys.stderr)
    print("[env] 先准备环境，再执行构建：", file=sys.stderr)
    print("      py -3.10 -m venv .venv", file=sys.stderr)
    print("      .\\.venv\\Scripts\\python.exe -m pip install -e \".[dev]\"", file=sys.stderr)
    print("      .\\.venv\\Scripts\\python.exe packaging\\build.py", file=sys.stderr)
    raise SystemExit(1)


def project_version() -> str:
    init = ROOT / "snipdraw" / "__init__.py"
    for line in init.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return "0.0.0"


def platform_tag() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin":
        return f"macos-{machine}"
    if system == "Windows":
        return f"windows-{machine}"
    if machine in {"arm64", "aarch64"}:
        return "linux-arm64"
    return "linux-x86_64"


def du_mb(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / 1024 / 1024
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file() and not entry.is_symlink():
            total += entry.stat().st_size
    return total / 1024 / 1024


# Mach-O magic（arm64/x86_64 的 64 位与 32 位、fat binary）
MACHO_MAGICS = (
    b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce",
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
)

# 这些标准库扩展运行时根本不会被导入（实测 import snipdraw.app 后都不在 sys.modules），
# 但 PyInstaller 会把 Python 的整个 lib-dynload 搬进来，所以构建后按名字剔除。
PRUNE_DYNLOAD = (
    "_codecs_cn", "_codecs_hk", "_codecs_jp", "_codecs_kr", "_codecs_tw",
    "_multibytecodec", "unicodedata", "_decimal",
)


def is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) in MACHO_MAGICS
    except OSError:
        return False


def drop_broken_symlinks(bundle: Path) -> int:
    """过滤掉 Qt 框架后，PyInstaller 建的符号链接会变成死链，一并清掉。"""
    removed = 0
    for path in list(bundle.rglob("*")):
        if path.is_symlink():
            try:
                if not path.exists():
                    path.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


def prune_dynload(bundle: Path) -> tuple[int, float]:
    removed = 0
    freed = 0.0
    for path in list(bundle.rglob("*")):
        if path.is_file() and path.name.split(".")[0] in PRUNE_DYNLOAD:
            freed += path.stat().st_size / 1024 / 1024
            path.unlink()
            removed += 1
    return removed, freed


def strip_macho(bundle: Path) -> tuple[int, float]:
    """strip -x 去掉本地符号。PyInstaller 的 strip=True 在 macOS 上实际不生效，
    这一刀通常能省 15%~25%。

    **绝对不能碰 bootloader 可执行文件**：PyInstaller 把 PKG 归档直接追加在
    Mach-O 之后，strip 会让归档读取失败（`Could not load PyInstaller's embedded
    PKG archive`）。所以只处理 dylib / .so，跳过 Contents/MacOS。
    """
    total = 0
    freed = 0.0
    exe_dir = bundle / "Contents" / "MacOS" if sys.platform == "darwin" else None
    for path in list(bundle.rglob("*")):
        if path.is_symlink() or not path.is_file() or not is_macho(path):
            continue
        if exe_dir and exe_dir in path.parents:
            continue
        before = path.stat().st_size
        subprocess.run(["strip", "-x", str(path)], capture_output=True, check=False)
        after = path.stat().st_size
        total += 1
        freed += (before - after) / 1024 / 1024
    return total, freed


def signing_identity() -> str:
    """签名身份：默认 ad-hoc（"-"），可用 SNIPDRAW_CODESIGN_ID 换成固定自签证书。

    为什么要能换：macOS 的「屏幕录制」授权按签名身份记账。ad-hoc 的 csreq 里
    带的是 cdhash——每重建一次内容就变一次，系统把它当新应用，于是又弹权限框。
    换成一张固定的自签证书后，csreq 只认证书，重建不再触发重新授权。
    """
    import os

    return os.environ.get("SNIPDRAW_CODESIGN_ID", "-")


def resign_ad_hoc(bundle: Path) -> None:
    """strip 会破坏签名，arm64 上签名无效的二进制无法执行，必须重签。"""
    identity = signing_identity()
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", identity, str(bundle)],
        check=True, capture_output=True,
    )


def installer_name(version: str) -> str:
    """Windows 安装包的文件名（与 installer.iss 里的 OutputBaseFilename 保持一致）。"""
    return f"Snipdraw-{version}-windows-x64-setup.exe"


def iscc_candidates() -> list[Path]:
    """Inno Setup 编译器可能的位置：winget 默认装到当前用户，也兼容全机安装。"""
    local_appdata = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return [
        local_appdata / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]


def find_iscc() -> Path | None:
    for candidate in iscc_candidates():
        if candidate.exists():
            return candidate
    found = shutil.which("ISCC")
    return Path(found) if found else None


def installer_command(iscc: Path, version: str) -> list[str]:
    return [
        str(iscc),
        f"/DAppVersion={version}",
        f"/DSourceDir={DIST_DIR / 'Snipdraw'}",
        f"/DOutputDir={RELEASE_DIR}",
        "/Qp",
        str(INSTALLER_ISS),
    ]


def package_installer() -> Path | None:
    """用 Inno Setup 把 dist/Snipdraw 打成 setup.exe；非 Windows 或缺 ISCC 时返回 None。"""
    if sys.platform != "win32":
        return None
    iscc = find_iscc()
    if iscc is None:
        print(
            "[installer] 没找到 Inno Setup（ISCC.exe），本次只出 zip。"
            "安装它：winget install JRSoftware.InnoSetup",
            file=sys.stderr,
        )
        return None
    version = project_version()
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    target = RELEASE_DIR / installer_name(version)
    if target.exists():
        target.unlink()
    subprocess.run(installer_command(iscc, version), check=True, cwd=ROOT)
    return target if target.exists() else None


def build() -> None:
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    shutil.rmtree(DIST_DIR, ignore_errors=True)
    cmd = [
        sys.executable, "-m", "PyInstaller", str(SPEC),
        "--noconfirm", "--log-level", "WARN",
        "--workpath", str(BUILD_DIR), "--distpath", str(DIST_DIR),
    ]
    print("[build]", " ".join(cmd[1:]))
    subprocess.run(cmd, check=True, cwd=ROOT)


def package() -> Path:
    version = project_version()
    tag = platform_tag()
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    if sys.platform == "darwin":
        source = DIST_DIR / "Snipdraw.app"
        target = RELEASE_DIR / f"Snipdraw-{version}-{tag}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(source.rglob("*")):
                if path.is_symlink():
                    info = zipfile.ZipInfo(str(path.relative_to(DIST_DIR)))
                    info.external_attr = (0o120777 << 16)
                    archive.writestr(info, path.readlink().as_posix())
                elif path.is_file():
                    archive.write(path, path.relative_to(DIST_DIR).as_posix())
    elif sys.platform == "win32":
        source = DIST_DIR / "Snipdraw"
        target = RELEASE_DIR / f"Snipdraw-{version}-{tag}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.write(path, Path("Snipdraw", path.relative_to(source)).as_posix())
    else:
        source = DIST_DIR / "Snipdraw"
        target = RELEASE_DIR / f"Snipdraw-{version}-{tag}.tar.gz"
        with tarfile.open(target, "w:gz") as archive:
            archive.add(source, arcname="Snipdraw")
    return target


def package_dmg() -> Path | None:
    """macOS 拖拽式安装包：卷里只放 Snipdraw.app + 指向 /Applications 的软链。

    这里不做 AppleScript 摆位和背景图：那需要 Finder 自动化权限，在 CI 和
    无头环境里既慢又容易失败，而 dmg 的核心价值（双击挂载、拖进 Applications）
    不依赖窗口布局。
    """
    if sys.platform != "darwin":
        return None
    version = project_version()
    tag = platform_tag()
    app = DIST_DIR / "Snipdraw.app"
    if not app.exists():
        print(f"[dmg] 没找到 {app}", file=sys.stderr)
        return None

    stage = BUILD_DIR / "dmg"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    # symlinks=True 很关键：.app 里有指向 Python.framework 的软链，
    # 默认 copytree 会跟进去复制，直接把体积翻倍。
    shutil.copytree(app, stage / app.name, symlinks=True)
    (stage / "Applications").symlink_to("/Applications")

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    target = RELEASE_DIR / f"Snipdraw-{version}-{tag}.dmg"
    if target.exists():
        target.unlink()
    subprocess.run(
        [
            "hdiutil", "create",
            "-volname", f"Snipdraw {version}",
            "-srcfolder", str(stage),
            # APFS + LZFSE 比 HFS+/UDZO 小约 2.3 MB；arm64 产物本来就只面向
            # macOS 11+，不存在老系统挂载不了的问题
            "-fs", "APFS",
            "-format", "ULFO",
            "-ov",
            str(target),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-build", action="store_true", help="只构建，不打压缩包")
    parser.add_argument("--only-package", action="store_true", help="跳过构建，只重新打包")
    parser.add_argument("--no-dmg", action="store_true", help="macOS 只出 zip，不出 dmg")
    parser.add_argument("--no-installer", action="store_true", help="Windows 只出 zip，不出 setup.exe")
    args = parser.parse_args()
    ensure_environment()

    if args.only_package:
        archive = package()
        print(f"[size] {archive.name}: {du_mb(archive):.1f} MB（分发体积）")
        if not args.no_dmg:
            dmg = package_dmg()
            if dmg is not None:
                print(f"[size] {dmg.name}: {du_mb(dmg):.1f} MB（安装包）")
        if not args.no_installer:
            setup = package_installer()
            if setup is not None:
                print(f"[size] {setup.name}: {du_mb(setup):.1f} MB（Windows 安装包）")
        return 0

    build()

    bundle = DIST_DIR / ("Snipdraw.app" if sys.platform == "darwin" else "Snipdraw")
    if not bundle.exists():
        print(f"[build] 没找到产物：{bundle}", file=sys.stderr)
        return 1
    before = du_mb(bundle)

    links = drop_broken_symlinks(bundle)
    modules, module_mb = prune_dynload(bundle)

    if sys.platform == "darwin":
        count, freed = strip_macho(bundle)
        resign_ad_hoc(bundle)
        print(f"[shrink] strip {count} 个 Mach-O：-{freed:.1f} MB；重签 ad-hoc 完成")
    else:
        print("[shrink] 非 macOS，跳过 strip / 重签")

    if sys.platform == "darwin" and signing_identity() == "-":
        print(
            "[sign] ad-hoc 签名：重建后 cdhash 会变，macOS 会要求重新授权「屏幕录制」。"
            "想避免就用 SNIPDRAW_CODESIGN_ID 指定一张固定的自签证书。"
        )
    print(f"[shrink] 死链 {links} 个，剔除 {modules} 个未用扩展：-{module_mb:.1f} MB")

    print(f"[size] {bundle.name}: {before:.1f} → {du_mb(bundle):.1f} MB（解压后占用）")

    if args.only_build:
        return 0

    archive = package()
    print(f"[size] {archive.name}: {du_mb(archive):.1f} MB（分发体积）")

    if not args.no_dmg:
        dmg = package_dmg()
        if dmg is not None:
            print(f"[size] {dmg.name}: {du_mb(dmg):.1f} MB（安装包）")

    if not args.no_installer:
        setup = package_installer()
        if setup is not None:
            print(f"[size] {setup.name}: {du_mb(setup):.1f} MB（Windows 安装包）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
