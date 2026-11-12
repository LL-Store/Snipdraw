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
    release/Snipdraw-<版本>-<平台>.zip|tar.gz  压缩分发（Windows/Linux，以及 macOS 备选）
"""

from __future__ import annotations

import argparse
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
    args = parser.parse_args()

    if args.only_package:
        archive = package()
        print(f"[size] {archive.name}: {du_mb(archive):.1f} MB（分发体积）")
        if not args.no_dmg:
            dmg = package_dmg()
            if dmg is not None:
                print(f"[size] {dmg.name}: {du_mb(dmg):.1f} MB（安装包）")
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
        print("[shrink] 非 macOS，跳过 strip（Windows/Linux 由 CI 构建）")

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
