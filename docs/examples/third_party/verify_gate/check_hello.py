#!/usr/bin/env python3
"""示范：**第三方自带门禁**（一个 `check_*.py`）。

协议：第三方守自己的东西时，也走同一套目录（`registry/verify/index.json` 的形状）——
一条 `command` + 一个 seam。判据就是**退出码**：0 = 过、非 0 = 判红。
"""

from __future__ import annotations

import sys


def main() -> int:
    print("hello gate: ok（第三方门禁示范：退出码即判据）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
