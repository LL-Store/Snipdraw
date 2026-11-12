# 打包（M7）

目标：**体积优先**。能跑起来的前提下，只留真正用到的 Qt 部分。

## 实测结果（macOS 26.5.1 / arm64 / Qt 6.12.0 / PyInstaller 6.22.3）

| 阶段 | 体积 | 说明 |
|---|---|---|
| `dist/Snipdraw.app`（解压后占用） | **53.9 MB** | 双击即用，无 Dock 图标（LSUIElement） |
| `release/Snipdraw-0.1.0-macos-arm64.dmg`（安装包） | **20.4 MB** | 双击挂载，把 app 拖进 Applications |
| `release/Snipdraw-0.1.0-macos-arm64.zip`（压缩分发） | **19.7 MB** | 不想用 dmg 时的备选 |
| 最小档（去掉 QtMultimedia） | 51.1 MB / 18.4 MB | `SNIPDRAW_NO_MULTIMEDIA=1 python packaging/build.py` |
| 参考：干净 venv | 607 MB | 打包等于砍掉 91% |

剩余体积全是「地板」，砍不动也不该砍：

| 文件 | 体积（strip 后） | 为什么必须留 |
|---|---|---|
| `QtWidgets.abi3.so` | 6.3 MB | 整个 UI 层 |
| `QtGui.framework` | ~6.5 MB | 绘制、字体、截图管线 |
| `QtGui.abi3.so` | ~4.9 MB | 同上，绑定层 |
| `QtCore.abi3.so` / `QtCore.framework` | ~4.6 + ~5.0 MB | 事件循环 |
| `QtWidgets.framework` | ~4.3 MB | |
| `Python.framework` | 4.3 MB | 解释器本身 |
| `QtNetwork`（so + framework） | ~2.9 MB | `QLocalSocket` 单实例锁 |
| `QtMultimedia` + darwin 插件 | ~2.0 MB | macOS 上 `QScreenCapture` 兜底后端（可关） |
| `QtDBus` | ~0.7 MB | QtGui 在 macOS 上确实链它 |

## 安装包（dmg）

`.app` 是应用本体，`zip` 只是压缩分发——用户拿到 zip 还得解压、再自己拖进
`/Applications`，中间容易被 Gatekeeper 拦一手。所以 macOS 另外出一个 dmg：

```bash
python packaging/build.py                 # 构建 + zip + dmg
python packaging/build.py --only-package  # 用现有 dist 重新打包，不重新构建
python packaging/build.py --no-dmg        # 只出 zip
```

做法就三行：建临时目录 → `copytree(symlinks=True)` 拷 `Snipdraw.app` → 建一个
指向 `/Applications` 的软链，然后 `hdiutil create -fs APFS -format ULFO`。

- **`symlinks=True` 不能省**：`.app` 里有指向 `Python.framework` 的软链，默认
  `copytree` 会跟进去把目标复制一遍，包体直接翻倍。
- **APFS + ULFO 比 HFS+ + UDZO 小约 2.3 MB**（22.7 → 20.4）。arm64 产物本来就
  只面向 macOS 11+，不存在老系统挂不上 APFS 卷的问题。
- **不做 AppleScript 摆位和背景图**：那需要 Finder 自动化权限，在 CI 和无头环境里
  又慢又容易失败，而 dmg 的核心价值（双击挂载、拖进 Applications）不依赖窗口布局。

挂载验证：卷里有 `Snipdraw.app` 和 `Applications` 软链，且直接从卷里跑
`Snipdraw.app/Contents/MacOS/Snipdraw --version` 能出 `Snipdraw 0.1.0`。

## 怎么砍的（100 MB → 53.9 MB）

1. **基线 100 MB**。PyInstaller 的 PySide6 hook 会把整个 `Qt/lib` 目录搬进来：
   QtQuick 5.8 MB、QtQml 4.6 MB、QtVirtualKeyboard、QtSvg、QtOpenGL，
   还有 `QtMultimedia` 白带的 **ffmpeg（libavcodec 12 MB + libavformat 2.5 MB）**，
   以及 `translations/` 16 MB。
2. **加框架白名单 + 插件白名单 + 去 ssl → 58 MB**（产物启动失败，见下）。
3. **补齐真实依赖 → 63 MB**，`oneshot` 截图与托盘常驻均验证通过。
4. **构建后处理 → 53.6 MB**（`strip` 55 个 Mach-O 省 7.0 MB，剔除 8 个未用扩展省 2.4 MB）：
   这一步在 `packaging/build.py` 里自动完成，spec 的 `strip=True` 在 macOS 上其实是空转。

`packaging/snipdraw.spec` 里对应四组开关：

- `EXCLUDES`：Python 侧（tkinter/unittest/sqlite3/email/asyncio/ssl…）+ Qt 侧（除
  Core/Gui/Widgets/Network/Multimedia 之外的模块）。
- `PLUGIN_ALLOW`：插件白名单，只留 `platforms`(cocoa/minimal/offscreen)、
  `imageformats`(jpeg/ico)、`multimedia`(darwin)。
- `FRAMEWORK_ALLOW`：框架白名单，`QtCore/QtGui/QtWidgets/QtNetwork/QtMultimedia/QtDBus/QtConcurrent`。
- `DROP_LIB_PREFIX`：干掉 `libavcodec/avformat/avutil/swresample/swscale`、
  `libcrypto/libssl`。

## 构建后处理（`build.py` 自动做）

1. `strip -x` 所有 Mach-O（dylib / .so / framework 二进制）。
   **不能碰 `Contents/MacOS/Snipdraw`**：PyInstaller 的 PKG 归档追加在 Mach-O 尾部按偏移读取，
   strip 会截断它，运行时报 `Could not load PyInstaller's embedded PKG archive`。
2. strip 破坏签名，arm64 上签名无效的二进制不能执行，所以立刻
   `codesign --force --deep --sign - dist/Snipdraw.app` 重签（ad-hoc 够本机跑）。
   构建完用 `codesign --verify --deep --strict` 复核。
3. 剔除 Python `lib-dynload` 里运行时不用的扩展：
   `unicodedata` / `_decimal` / `_codecs_cn,hk,jp,kr,tw` / `_multibytecodec`。
   判断依据是实测 `import snipdraw.app` 之后这些都不在 `sys.modules`。
4. 清掉过滤框架后留下的死链（`Resources/QtQuick -> ...QtQuick.framework/...`）。
5. 再 strip 更狠的参数（`-x -u`、`-x -u -r`）实测与 `-x` 体积完全相同，没有额外收益。

## 踩过的三个坑（改 spec 时别再犯）

1. **白名单不能一视同仁地扫所有 `.framework`。**
   第一版按后缀 `.framework` 判，结果 `Python.framework` 被一起干掉，
   产物启动报 `Failed to load Python shared library .../Frameworks/Python`。
   现在只对 `Qt*` 前缀的框架生效。
2. **Qt 的依赖不能靠猜，要用 `otool -L` 算闭包。**
   砍掉 QtDBus 后 QtGui 直接 `dlopen` 失败（`Library not loaded: @rpath/QtDBus`）。
   闭包：`QtGui → QtCore, QtDBus`；`QtWidgets → QtCore, QtGui`；
   `QtNetwork → QtCore`；`QtMultimedia → QtConcurrent, QtCore, QtGui, QtNetwork`。
3. **`ctypes.macholib` 不能排除。** macOS 上 `ctypes.util` 会导入它，
   而这条路径只有「启动托盘 / 注册热键」才走到，`oneshot` 走不到 ——
   只测 `oneshot` 会漏掉，必须两种都跑。

## 图标

母版是 `assets/icon-1024.png`（1:1，透明背景，圆角方底板），
派生出 `assets/Snipdraw.icns`（macOS）与 `assets/Snipdraw.ico`（Windows），
spec 里 `BUNDLE(icon=…)` / `EXE(icon=…)` 直接引用。

icns 只打 16/32/128/256/512 五档：把 `@2x` 档也全打进去会到 877 KB，
五档用无损优化后是 450 KB，Retina 由系统从 512 放大，观感差异看不出来。
试过调色板量化（能把 icns 压到 ~135 KB），但在深色渐变上会出现斑点，不划算。

更换图标：把新母版覆盖 `assets/icon-1024.png`，然后

```bash
python3 - <<'EOF'
from PIL import Image
src = Image.open("assets/icon-1024.png").convert("RGBA")
import os; os.makedirs("/tmp/Snipdraw.iconset", exist_ok=True)
for size, name in ((16,"icon_16x16.png"),(32,"icon_32x32.png"),(128,"icon_128x128.png"),
                   (256,"icon_256x256.png"),(512,"icon_512x512.png")):
    src.resize((size,size), Image.LANCZOS).save(f"/tmp/Snipdraw.iconset/{name}", "PNG", optimize=True, compress_level=9)
EOF
iconutil -c icns /tmp/Snipdraw.iconset -o assets/Snipdraw.icns
```

改完图标 Finder 可能还显示旧图标（LaunchServices 缓存），
`touch dist/Snipdraw.app` 或 `lsregister -f dist/Snipdraw.app` 刷新即可。

## 构建

```bash
python packaging/build.py            # 构建 + 打压缩包 + 打印体积
python packaging/build.py --only-build
```

产物：`dist/Snipdraw.app`（macOS）/ `dist/Snipdraw/`（Linux、Windows），
压缩包落在 `release/`。

## 产物验证（每次改 spec 都要跑）

```bash
# 1. 截图链路：截屏 + 存盘 + 剪贴板
./dist/Snipdraw.app/Contents/MacOS/Snipdraw oneshot --out /tmp/pkg.png

# 2. 托盘 + 热键链路（覆盖 ctypes / 热键后端）
./dist/Snipdraw.app/Contents/MacOS/Snipdraw
```

第 3 条自查：`find dist/Snipdraw.app -type f -size +1M -exec du -sh {} \; | sort -rh`
—— 出现 QtQuick/Qml/libav* 就说明过滤失效了。

`build.py` 已经在构建后自动做 strip + 重签，所以**别再手动 `strip` 整个 bundle**
（会连 bootloader 一起剥坏，也会让签名失效）。

## 三平台差异

| 平台 | 过滤策略 | 产物 |
|---|---|---|
| macOS | 框架白名单 + 插件白名单（arm64 已实测） | `.app` + dmg（安装包）+ zip（备选） |
| Linux | 不做插件白名单（否则 `platforms/libqxcb` 会被砍导致起不来），只按目录丢弃；不含 QtMultimedia（X11 走 `grabWindow`） | 目录 + tar.gz |
| Windows | 同上；不含 QtMultimedia | 目录 + zip |

框架白名单仅作用于 macOS 的 `.framework`，`EXCLUDES` 与目录丢弃对三平台都安全。

## 代码签名与公证

当前产物**未签名、未公证**，本机可直接运行；分发给别人时 macOS 会拦
（对方需右键打开，或 `xattr -dr com.apple.quarantine`）。
要正式分发需要 Apple Developer ID：`codesign --deep --force -s "Developer ID Application: ..."`
再 `xcrun notarytool submit`，签名不会明显增加体积（`_CodeSignature` 约 32 KB）。
