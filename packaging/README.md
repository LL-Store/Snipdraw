# 打包（M7）

目标：**体积优先**。能跑起来的前提下，只留真正用到的 Qt 部分。

## 实测结果

### macOS 26.5.1 / arm64 / Qt 6.12.0 / PyInstaller 6.22.3

| 阶段 | 体积 | 说明 |
|---|---|---|
| `dist/Snipdraw.app`（解压后占用） | **53.9 MB** | 双击即用，无 Dock 图标（LSUIElement） |
| `release/Snipdraw-0.1.0-macos-arm64.dmg`（安装包） | **20.4 MB** | 双击挂载，把 app 拖进 Applications |
| `release/Snipdraw-0.1.0-macos-arm64.zip`（压缩分发） | **19.7 MB** | 不想用 dmg 时的备选 |
| 最小档（去掉 QtMultimedia） | 51.1 MB / 18.4 MB | `SNIPDRAW_NO_MULTIMEDIA=1 python packaging/build.py` |
| 参考：干净 venv | 607 MB | 打包等于砍掉 91% |

剩余体积全是「地板」，砍不动也不该砍（下表为 macOS）：

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

### Windows 11（10.0.26200）/ x64 / Python 3.10 / Qt 6.12.0 / PyInstaller 6.22.3

| 阶段 | 体积 | 说明 |
|---|---|---|
| `dist/Snipdraw/`（解压后占用） | **98.6 MB** | `Snipdraw.exe` + `_internal/`，双击即用 |
| `release/Snipdraw-0.1.0-windows-x64-setup.exe`（安装包） | **26.9 MB** | 双击安装到当前用户目录，免管理员 |
| `release/Snipdraw-0.1.0-windows-amd64.zip`（压缩分发） | **38.5 MB** | 解压即用，不写注册表 |

Windows 上 `strip` 和代码签名都不适用，体积全靠 `EXCLUDES` 与目录丢弃；构建后处理
只剩剔除 `lib-dynload` 里 2 个未用扩展（99.9 → 98.6 MB）。

`_internal` 实测 97.6 MB：`PySide6` 88.8 MB、`shiboken6` 1.1 MB、其余 7.7 MB
（Python 运行时 + api-ms-win 系列 DLL）：

| 文件 | 体积 | 说明 |
|---|---|---|
| `PySide6\opengl32sw.dll` | 19.7 MB | 软件 OpenGL 兜底；实测托盘运行时没加载它，但删不得——没有可用 GPU 驱动的机器要靠它兜底 |
| `Qt6Core.dll` / `Qt6Gui.dll` / `Qt6Widgets.dll` | 10 / 9.2 / 6.2 MB | 真正用到的模块 |
| `Qt6Quick.dll` / `Qt6Qml.dll` | 6.4 / 5.1 MB | 见下方说明，属于未裁剪项 |
| `QtWidgets.pyd` / `QtGui.pyd` / `QtCore.pyd` | 4.7 / 3.8 / 3.4 MB | 绑定层 |
| `python310.dll` | 4.2 MB | 解释器 |
| `PySide6\plugins\` 全目录 | 5.6 MB | 平台插件 + 图片格式等 |

`EXCLUDES` 里的 `PySide6.QtQml` / `PySide6.QtQuick` 只在 **Python 模块层面**生效；
DLL 层面没有对应过滤（spec 的 `keep_qt_lib` 只对 macOS 的 `.framework` 做白名单），
所以 `Qt6Quick.dll` + `Qt6Qml.dll` 合计约 11 MB 仍被打进 Windows 包。实测托盘常驻
运行时这两个 DLL 都没被加载，是 Windows 侧还能再瘦身的地方——但 spec 目前没做，
动之前要按上面的「产物验证」跑一遍。

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

## Windows 安装包（setup.exe）

Windows 另外出一个 Inno Setup 安装包，脚本是 `packaging/installer.iss`，由 `build.py`
在 `package()` 之后调用（`--no-installer` 可跳过）：

- **当前用户安装**（`PrivilegesRequired=lowest`）：默认装到
  `%LOCALAPPDATA%\Programs\Snipdraw`，不弹 UAC；想装到全局可以在向导里切换（会提示提权）。
- 装完后有开始菜单快捷方式、可选的桌面快捷方式，以及「应用和功能」里的卸载项
  （`AppId` 固定为 `{{7A26B4C5-…}}`，新版覆盖旧版不会被当成另一个软件）。
- `CloseApplications=yes`：覆盖安装时会先关掉正在跑的托盘实例，不用手动退出。
- **卸载不删用户配置**：设置存在 `QStandardPaths::AppConfigLocation` 下（`config.json`），
  卸载只删程序目录。
- 向导正文是英文（Inno 6.7 自带的 29 种语言里没有简体中文，中文是社区翻译，没引进来），
  但自定义文案（桌面快捷方式、立即运行）是中文。想要全中文向导，把
  `ChineseSimplified.isl` 放进 `packaging/languages/` 再在 `[Languages]` 里加一行即可。
- 产物未签名，别人双击会先遇到 SmartScreen（「更多信息 → 仍要运行」）。

编译需要 Inno Setup 6 的 `ISCC.exe`：`winget install JRSoftware.InnoSetup`（默认就装到
当前用户目录）。没装时 `build.py` 不会失败，只打印一行 `[installer] 没找到 Inno Setup…`
并继续出 zip。版本号由 `build.py` 读 `snipdraw/__init__.py` 后通过 `/DAppVersion=` 传入，
`OutputBaseFilename` 与 `installer_name()` 保持同一个命名。

安装包大小 26.9 MB，靠 `Compression=lzma2/ultra64` + `SolidCompression` 压出来
（zip 是 38.5 MB，两者内容相同）。

## 怎么砍的（macOS：100 MB → 53.9 MB）

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

## 踩过的坑（改 spec 时别再犯）

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
4. **Windows 上用错了 Python。** 报错栈尾巴只有
   `CalledProcessError: Command '[...] -m PyInstaller ...' returned non-zero exit status 1`，
   真因是商店版 Python 3.9 里没有 PyInstaller/PySide6。`build.py` 现在会自动切到项目
   `.venv`；没有可用 venv 时才需要手动建一个（详见上方「构建」）。
5. **Windows 上自测存图会静默失败。** 屏幕名里的 `|` 让 `QImage.save` 返回 False
   而不抛异常，于是打印「完成」但目录是空的。文件名要消毒，`save` 返回值要检查。

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

解释器要 3.10–3.13（`pyproject.toml` 写的是 `>=3.10,<3.14`），并且必须装过 `.[dev]`——
PyInstaller 和 PySide6 都在这个 extra 里：

```bash
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

```bash
python packaging/build.py                 # 构建 + 打压缩包 +（Windows）出安装包 + 打印体积
python packaging/build.py --only-build
python packaging/build.py --no-installer  # Windows 只出 zip
```

产物：`dist/Snipdraw.app`（macOS）/ `dist/Snipdraw/`（Linux、Windows），压缩包与安装包
都落在 `release/`。Windows 的 setup.exe 需要 Inno Setup（
`winget install JRSoftware.InnoSetup`），没装时这一步只打印一行提示并跳过，zip 照常出。

### Windows 上多一步：别用应用商店版 Python

`WindowsApps\python.exe` 是商店版 Python 3.9 的 stub，里面既没有 PyInstaller
也没有 PySide6，版本也不满足 `>=3.10`。用它跑 `python packaging/build.py` 时，报错栈
尾巴只有 `subprocess.CalledProcessError ... returned non-zero exit status 1`，真因其实
只是一句 `No module named PyInstaller`。

`build.py` 现在会自己在 `main()` 开头做环境预检（`ensure_environment()`）：

- 当前解释器缺依赖或版本不对时，先在项目里找 `.venv`（Windows 的
  `.venv\Scripts\python.exe` / Unix 的 `.venv/bin/python`），探通就**自动换过去重跑**，
  并打印一行 `[env] 改用项目 venv 继续：…`；
- 没有可用 venv 才退出 1，并给出可以直接照抄的三条命令。

所以 Windows 上 `python packaging/build.py` 能够跑通，前提是项目里有装好 `.[dev]`
的 `.venv`。从零准备环境：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe packaging\build.py
```

## 产物验证（每次改 spec 都要跑）

```bash
# 1. 截图链路：截屏 + 存盘 + 剪贴板
./dist/Snipdraw.app/Contents/MacOS/Snipdraw oneshot --out /tmp/pkg.png

# 2. 托盘 + 热键链路（覆盖 ctypes / 热键后端）
./dist/Snipdraw.app/Contents/MacOS/Snipdraw
```

第 3 条自查：`find dist/Snipdraw.app -type f -size +1M -exec du -sh {} \; | sort -rh`
—— 出现 QtQuick/Qml/libav* 就说明过滤失效了。

Windows 产物是 GUI 子系统（spec 里 `console=False`），`--version` 和 `selftest` 的
print 在终端里看不到，所以**以退出码 + 落盘文件为准**：

```powershell
# 1. 截图链路：退出码 0 且目录里确实生成 PNG
dist\Snipdraw\Snipdraw.exe selftest --out "$env:TEMP\snip"

# 2. 托盘链路的验证只能看进程是否活着（4 秒后仍在即通过）
Start-Process dist\Snipdraw\Snipdraw.exe

# 3. 安装包：静默装到临时目录，跑一次，再静默卸载
$dir = "$env:TEMP\SnipdrawInstTest"
.\release\Snipdraw-0.1.0-windows-x64-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="$dir"
Test-Path "$dir\Snipdraw.exe"        # True
& "$dir\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

Windows 的屏幕名形如 `|DELL E1715S`（以 `|` 开头），`|` 在文件名里非法，早前会让
`QImage.save` 静默返回 False——自测打印「完成」却一张图都没有。现在文件名统一走
`selftest.safe_filename()` 消毒，并且检查 `save` 返回值，写不出来直接返回 1。

`build.py` 已经在构建后自动做 strip + 重签（仅 macOS；Windows/Linux 跳过这一步），
所以**别再手动 `strip` 整个 bundle**（会连 bootloader 一起剥坏，也会让签名失效）。

## 三平台差异

| 平台 | 过滤策略 | 产物 |
|---|---|---|
| macOS | 框架白名单 + 插件白名单（arm64 已实测） | `.app` + dmg（安装包）+ zip（备选） |
| Linux | 不做插件白名单（否则 `platforms/libqxcb` 会被砍导致起不来），只按目录丢弃；不含 QtMultimedia（X11 走 `grabWindow`） | 目录 + tar.gz（需在 Linux 上构建，未实机复测） |
| Windows | 同上；不含 QtMultimedia；不做 strip 与签名；DLL 层面没有白名单（PySide6 下 40 个 DLL 全留，含未加载的 Qt6Quick/Qt6Qml）。已实测：98.6 MB / zip 38.5 MB / setup 26.9 MB | 目录 + zip + setup.exe（当前用户安装） |

三个平台都由 `packaging/build.py` 在对应系统上本地构建——仓库里没有 CI workflow，
所以别指望推 tag 自动出产物。

框架白名单仅作用于 macOS 的 `.framework`，`EXCLUDES` 与目录丢弃对三平台都安全。

## 代码签名与公证

当前产物**未签名、未公证**，本机可直接运行；分发给别人时 macOS 会拦
（对方需右键打开，或 `xattr -dr com.apple.quarantine`）；Windows 未签名的 exe
（zip 里的 `Snipdraw.exe` 和 setup.exe 本身）首次运行会弹 SmartScreen 提示
（「更多信息 → 仍要运行」）。WinGet 之类的分发渠道要求先有签名，这一点和 Inno Setup
无关，得另外买证书。
要正式分发需要 Apple Developer ID：`codesign --deep --force -s "Developer ID Application: ..."`
再 `xcrun notarytool submit`，签名不会明显增加体积（`_CodeSignature` 约 32 KB）。
