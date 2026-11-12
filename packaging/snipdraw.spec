# -*- mode: python ; coding: utf-8 -*-
"""Snipdraw 打包配置：目标是把体积压到 Qt 的地板附近。

体积构成（macOS arm64，实测）：
  PySide6 绑定 .so    ~42M（QtCore/QtGui/QtWidgets/QtNetwork，必须全留）
  Qt 框架 dylib       ~41M（QtGui 17 + QtWidgets 12 + QtCore 12）
  Qt 插件 + 翻译      ~30M（其中 translations 16M、一堆用不到的插件）
  Python 运行时       ~15M

所以策略只有一条：**只留四个 Qt 模块**，插件按白名单留，翻译全删。
任何“用不到但被 hook 顺手收进来”的东西，一律在 EXCLUDES / 过滤里干掉。
"""

import os
import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH)
ROOT = SPEC_DIR.parent

ASSETS = ROOT / "assets"
ICNS = ASSETS / "Snipdraw.icns"      # macOS 图标（assets/icon-1024.png 是母版）
ICO = ASSETS / "Snipdraw.ico"        # Windows 图标

# ---------------------------------------------------------------- 排除

EXCLUDES = [
    # Python 侧：这些要么从没用过，要么只服务于开发期
    "tkinter", "turtle", "unittest", "doctest", "pydoc", "pydoc_data",
    "test", "idlelib", "lib2to3", "distutils", "ensurepip", "venv",
    "sqlite3", "email", "http", "xmlrpc", "multiprocessing", "asyncio",
    "logging.config", "concurrent", "setuptools",
    "pkg_resources", "pip", "pytest", "pyinstaller",
    # 注意：不能排除 ctypes.macholib —— macOS 上 ctypes.util 会导入它，
    # 托盘/热键那条路径会因此 ModuleNotFoundError
    # 不做任何 TLS 通信（QLocalSocket 走本地域套接字），去掉可省 libcrypto/libssl 约 5M
    "ssl", "_ssl",
    # Qt 侧：只保留 Core / Gui / Widgets / Network / Multimedia
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets", "PySide6.QtQuick3D", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtTest",
    "PySide6.QtSql", "PySide6.QtXml", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtPrintSupport", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtLocation",
    "PySide6.QtPositioning", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtWebChannel", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtRemoteObjects",
    "PySide6.QtTextToSpeech", "PySide6.QtMultimediaWidgets", "PySide6.QtMultimediaQuick",
    "PySide6.QtSpatialAudio", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtHttpServer", "PySide6.QtConcurrent", "PySide6.QtDBus",
    "PySide6.QtPacketProtocol", "PySide6.QtScript", "PySide6.QtScriptTools",
]

if sys.platform != "darwin":
    # Linux / Windows 走 grabWindow 截屏，不需要 QtMultimedia；
    # Linux 上它还会拖进 ffmpeg 一堆库，代价远大于收益
    EXCLUDES.append("PySide6.QtMultimedia")

# macOS 上要不要留 QtMultimedia（QScreenCapture 兜底后端，约 2.7 MB）。
# 想再小一点：SNIPDRAW_NO_MULTIMEDIA=1 python packaging/build.py
# 代价是 grabWindow 万一返回空图时没有第二套截屏路径。
KEEP_MULTIMEDIA = os.environ.get("SNIPDRAW_NO_MULTIMEDIA", "") not in {"1", "true", "yes"}
if sys.platform == "darwin" and not KEEP_MULTIMEDIA:
    EXCLUDES.append("PySide6.QtMultimedia")

# 插件白名单：只在 macOS 上按白名单收紧。
# Linux / Windows 的平台插件种类多（xcb、wayland、windows 风格等），
# 这里不做白名单，只按下面的“整目录丢弃”列表砍，避免把平台插件砍没了导致起不来。
if sys.platform == "darwin":
    PLUGIN_ALLOW = {
        "platforms": ("libqcocoa", "libqminimal", "libqoffscreen"),
        # PNG 是编译进 QtGui 的，插件里只需要 jpeg（存 .jpg）和 ico
        "imageformats": ("libqjpeg", "libqico"),
    }
    if KEEP_MULTIMEDIA:
        PLUGIN_ALLOW["multimedia"] = ("libdarwinmediaplugin",)
    DROP_DIRS = (
        "translations", "qml", "sqldrivers", "sceneparsers", "assetimporters",
        "renderers", "qmltooling", "tls", "geoservices", "canbus", "position",
        "designer", "geometryloaders", "webview", "texttospeech", "generic",
        "scxmldatamodel", "vectorimageformats", "renderplugins", "sensors",
        "networkinformation", "styles", "printsupport", "iconengines",
        "egldeviceintegrations", "virtualkeyboard",
        "wayland-decoration-client", "wayland-graphics-integration-client",
        "wayland-shell-integration", "platforminputcontexts", "platformthemes",
    )
else:
    PLUGIN_ALLOW = None      # None = 不启用白名单
    DROP_DIRS = (
        "translations", "qml", "sqldrivers", "sceneparsers", "assetimporters",
        "renderers", "qmltooling", "canbus", "designer", "geometryloaders",
        "webview", "texttospeech", "scxmldatamodel", "vectorimageformats",
        "renderplugins", "sensors", "virtualkeyboard",
    )

# 框架白名单：按 otool 依赖闭包算出来的最小集合
#   QtGui 链 QtDBus，QtMultimedia 链 QtConcurrent —— 少一个都 dlopen 失败
FRAMEWORK_ALLOW = ["QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtDBus"]
if KEEP_MULTIMEDIA:
    FRAMEWORK_ALLOW += ["QtMultimedia", "QtConcurrent"]

# 这些独立动态库是 ffmpeg 后端和 Python ssl 用的，本项目都不需要
DROP_LIB_PREFIX = ("libavcodec", "libavformat", "libavutil", "libswresample",
                   "libswscale", "libcrypto", "libssl")


def _is_qt_plugin(path: str) -> bool:
    return f"{os.sep}Qt{os.sep}plugins{os.sep}" in path or "/Qt/plugins/" in path


def keep_qt_plugin(path: str) -> bool:
    """macOS 按白名单收紧；其它平台只按 DROP_DIRS 整目录丢弃。"""
    parts = path.replace(os.sep, "/").split("/")
    if "plugins" not in parts:
        return True
    index = parts.index("plugins")
    if index + 2 >= len(parts):
        return False
    group = parts[index + 1]
    name = parts[index + 2]
    if group in DROP_DIRS:
        return False
    if PLUGIN_ALLOW is None:
        return True
    allowed = PLUGIN_ALLOW.get(group)
    if allowed is None:
        return False
    return name.startswith(allowed)


def keep_qt_data(path: str) -> bool:
    """translations / qml 这类纯资源目录整体不要。"""
    normalized = path.replace(os.sep, "/")
    for dropped in DROP_DIRS:
        marker = f"/Qt/{dropped}/"
        if marker in normalized:
            return False
    return True


def keep_qt_lib(path: str) -> bool:
    """框架按白名单留；Qt/lib 下直接躺着的 .dylib 一律不留。

    PyInstaller 的 PySide6 hook 会把整个 Qt/lib 目录搬进来，所以这里必须逐个判。
    注意要按路径里的 `X.framework` 段判断，而不是看 basename——框架内的二进制
    名字就是 `QtGui`，没有 .framework 后缀。
    """
    normalized = path.replace(os.sep, "/")
    for segment in normalized.split("/"):
        if segment.endswith(".framework"):
            name = segment[: -len(".framework")]
            # 只对 Qt 自己的框架做白名单；Python.framework 是运行时命根子
            if not name.startswith("Qt"):
                return True
            return name in FRAMEWORK_ALLOW
    base = os.path.basename(normalized)
    if any(base.startswith(prefix) for prefix in DROP_LIB_PREFIX):
        return False
    return True


def filter_binaries(binaries, datas):
    kept_binaries = [
        entry
        for entry in binaries
        if keep_qt_data(entry[0]) and keep_qt_plugin(entry[0]) and keep_qt_lib(entry[0])
    ]
    kept_datas = [
        entry
        for entry in datas
        if keep_qt_data(entry[0]) and keep_qt_plugin(entry[0]) and keep_qt_lib(entry[0])
    ]
    return kept_binaries, kept_datas


a = Analysis(
    [str(SPEC_DIR / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,
)

a.binaries, a.datas = filter_binaries(a.binaries, a.datas)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Snipdraw",
    icon=str(ICO) if ICO.exists() else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True if sys.platform == "darwin" else False,
    upx=False,
    name="Snipdraw",
)

info_plist = {
    "CFBundleName": "Snipdraw",
    "CFBundleDisplayName": "Snipdraw",
    "CFBundleIdentifier": "store.ll.snipdraw",
    "CFBundleShortVersionString": "0.1.0",
    "CFBundleVersion": "0.1.0",
    "NSHighResolutionCapable": True,
    # 常驻托盘应用：不要 Dock 图标，跟 Snipaste 一致
    "LSUIElement": True,
    "LSMinimumSystemVersion": "11.0",
}

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Snipdraw.app",
        icon=str(ICNS) if ICNS.exists() else None,
        bundle_identifier="store.ll.snipdraw",
        info_plist=info_plist,
    )
