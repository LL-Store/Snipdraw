"""命令行入口：默认进托盘常驻，其余是调试用子命令。"""

from __future__ import annotations

import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    command = args[1] if len(args) > 1 else ""

    if command in ("-v", "--version"):
        print(f"Snipdraw {__version__}")
        return 0
    if command == "selftest":
        from .selftest import main as selftest_main

        return selftest_main(args[2:])
    if command == "demo":
        from .demo import main as demo_main

        return demo_main(args[2:])
    if command == "oneshot":
        from .oneshot import main as oneshot_main

        return oneshot_main(args[2:])

    from .app import run

    # `settings`：直接开设置窗口。已有实例在跑时，这句会转发给它，
    # 所以托盘图标被一堆图标挤住时也能改配置。
    return run(args, open_settings=(command == "settings"))


if __name__ == "__main__":
    raise SystemExit(main())
