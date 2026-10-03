# -*- coding: utf-8 -*-
"""包名册真值（族注册表声明 → 套件声明驱动迭代）。

族收敛后 `assets/robots` 只装**当前名册**（8 台，见 registry/families/*.json 的
members）。契约套件里旧时代硬编码的期望表（limx_tron1/microduck/wuji_hand/
unitree_g1 等）不许再当存在的包来断言。规则：

* **在库包**：不变量照旧全强度（一个不少）；
* **缺席包**：`require_package` 显式 `skipTest`——skip 理由必须点名
  "不在库"，这是名册事实的如实表达，不是静默放行（fail-loud 的 skip）；
* **名册计数**：断言 = 在库包集合 == 族注册表声明成员的并集
  （声明驱动，不再钉魔法数字 14）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
ROBOTS = WORKSPACE / "assets" / "robots"
FAMILIES = WORKSPACE / "registry" / "families"


def present_packages() -> list[str]:
    """在库包（有 contract.json 的目录），排序稳定。"""
    return sorted(p.name for p in ROBOTS.iterdir() if (p / "contract.json").exists())


def package_present(package_id: str) -> bool:
    return (ROBOTS / package_id / "contract.json").is_file()


@lru_cache(maxsize=1)
def declared_members() -> frozenset[str]:
    """族注册表声明的成员并集（名册唯一真值；index.json 之类的目录文件跳过）。"""
    out: set[str] = set()
    for path in sorted(FAMILIES.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        if not doc.get("family_id"):
            continue
        for member in doc.get("members") or []:
            out.add(str(member))
    return frozenset(out)


def require_package(testcase, package_id: str) -> None:
    """在库 → 直接返回；缺席 → skipTest（理由点名名册，不静默）。"""
    if package_present(package_id):
        return
    testcase.skipTest(
        f"包 {package_id!r} 不在库（族收敛后名册 {len(present_packages())} 台）"
        "——期望表按声明名册跳过"
    )
