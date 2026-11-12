"""PyInstaller 入口：只做一件事——把包入口暴露成可执行脚本。"""

import sys

from snipdraw.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
