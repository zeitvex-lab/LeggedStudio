#!/usr/bin/env python3
"""审计**地图资产的双链路**：``assets/maps/``（新链路）vs ``web/sim2sim/assets/go2/``（旧链路）。

**为什么会有两份**（这是设计，不是失误）：

* ``assets/maps/*.xml`` —— **公共地图库**：纯环境（灯光/材质/地形），**不含机器人**；
  服务端下发时按机型注入 ``<include file="../model/robot.xml"/>``，同一张图可跑四足/轮足/人形。
* ``web/sim2sim/assets/go2/*.xml`` —— **内置旧链路（bundled flow）**的静态资源：
  自带 ``<include file="go2.xml"/>``，且与 Go2 策略在 ``references_1000framesai`` 里的
  **reference MJCF/terrain bundle 精确耦合**（``web/sim2sim/app.js`` 的注释明写
  "Keep that exact model/terrain bundle"）。改它可能改变策略复现结果。

**那问题在哪**：两条链路里的**地形几何是同源的**（实测 7/7 一致，只有 ``slope`` 多一个
``friction``），但它们靠**手工同步**。已经因此出过两次真事故：

1. ``assets/maps/imgs/`` 没跟着 xml 一起拷过来 ⇒ ``cross_slope`` / ``cross_stairs``
   **长期编译不过**（引用了不存在的 ``label_*.png``）；
2. 视觉口径各改各的（一边纯黑 skybox、一边 gradient）——两边观感不同却没人发现。

本工具把这两件事变成**每次提交都能跑**的检查：

* **资源完整性 = 硬门禁**（exit 2）：任何一侧引用了不存在的贴图/网格，直接红；
* **地形几何对比 = 报告**（不判红）：差异本身可能是**有意的**（如 ``slope`` 的 friction），
  工具只负责把"差在哪"摆出来，让人判断，而不是替人决定。

用法::

    python tools/audit_map_duplication.py            # 人类可读
    python tools/audit_map_duplication.py --json     # 机器可读
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

#: 新链路：公共地图库（纯环境，不含机器人）
NEW_LINK = ROOT / "assets" / "maps"
#: 旧链路：内置 bundled flow（含 <include file="go2.xml"/>，与 Go2 策略 bundle 耦合）
OLD_LINK = ROOT / "web" / "sim2sim" / "assets" / "go2"

_WORLDBODY_RE = re.compile(r"<worldbody>.*?</worldbody>", re.DOTALL)
_GEOM_RE = re.compile(r"<geom\b[^>]*?/>", re.DOTALL)
_ATTR_RE = re.compile(r"([A-Za-z_]+)=\"([^\"]*)\"")

#: **纯外观**属性：比较"地形几何是否漂移"时应当排除。
#: 否则给一侧补了 `material="terrain"`（视觉统一，物理不变）就会被报成"几何漂移"——
#: 那是把外观变更误报成物理变更。碰撞/摩擦类属性（contype/priority/friction…）**不排除**。
_APPEARANCE_ATTRS = frozenset({"material", "rgba"})
_ASSET_REF_RE = re.compile(r"\b(?:file|meshdir)=\"([^\"]+)\"")
_COMPILER_MESHDIR_RE = re.compile(r"<compiler\b[^>]*\bmeshdir=\"([^\"]+)\"")


def terrain_geoms(text: str) -> Counter:
    """地形几何的**属性级签名**（忽略属性顺序与空白，所以只反映"真的不一样"）。

    只取 ``<worldbody>`` 段：``<include>`` 的机器人几何不在这一段里，天然被排除。
    """
    body = _WORLDBODY_RE.search(text)
    if not body:
        return Counter()
    signatures = []
    for geom in _GEOM_RE.findall(body.group(0)):
        attributes = [
            (key, " ".join(value.split()))
            for key, value in _ATTR_RE.findall(geom)
            if key not in _APPEARANCE_ATTRS
        ]
        signatures.append(tuple(sorted(attributes)))
    return Counter(signatures)


def missing_assets(text: str, base_dir: Path) -> list[str]:
    """列出引用了但磁盘上不存在的资源。

    两处容易误报、必须处理：

    * **``<compiler meshdir="…">``** —— MJCF 里 mesh 常放子目录（如 ``meshdir="assets"``），
      路径要相对 **meshdir** 解析，而不是 MJCF 所在目录；
    * **``../`` 开头的跨目录引用** —— 公共地图库的 ``../model/assets`` 是**服务端按机型注入**
      的机器人 meshdir，不属于地图目录的资产，不该在这里判缺。
    """
    compiler = _COMPILER_MESHDIR_RE.search(text)
    meshdir = (base_dir / compiler.group(1)) if compiler else base_dir
    missing: list[str] = []
    for rel in _ASSET_REF_RE.findall(text):
        if rel.startswith(".."):  # 跨目录（服务端注入的机器人资产）
            continue
        if not ((base_dir / rel).exists() or (meshdir / rel).exists()):
            missing.append(rel)
    return missing


def audit_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return {
        "file": path.name,
        "has_robot_include": bool(re.search(r"<include\b", text)),
        "missing_assets": missing_assets(text, path.parent),
    }


def run() -> dict[str, Any]:
    new_files = {p.name: p for p in sorted(NEW_LINK.glob("*.xml"))}
    old_files = {p.name: p for p in sorted(OLD_LINK.glob("*.xml"))}
    shared = sorted(set(new_files) & set(old_files))

    resource_issues: list[dict[str, Any]] = []
    for label, files in (("assets/maps", new_files), ("web/sim2sim/assets/go2", old_files)):
        for name, path in files.items():
            info = audit_file(path)
            if info["missing_assets"]:
                resource_issues.append(
                    {"link": label, "file": name, "missing": info["missing_assets"]}
                )

    geometry: list[dict[str, Any]] = []
    for name in shared:
        new_text = new_files[name].read_text(encoding="utf-8")
        old_text = old_files[name].read_text(encoding="utf-8")
        new_geoms, old_geoms = terrain_geoms(new_text), terrain_geoms(old_text)
        common = sum((new_geoms & old_geoms).values())
        only_new = list((new_geoms - old_geoms).elements())
        only_old = list((old_geoms - new_geoms).elements())
        geometry.append(
            {
                "file": name,
                "new_count": sum(new_geoms.values()),
                "old_count": sum(old_geoms.values()),
                "identical": common,
                "only_new": [dict(item) for item in only_new[:3]],
                "only_old": [dict(item) for item in only_old[:3]],
                "same": not only_new and not only_old,
            }
        )

    return {
        "new_link": str(NEW_LINK),
        "old_link": str(OLD_LINK),
        "new_only": sorted(set(new_files) - set(old_files)),
        "old_only": sorted(set(old_files) - set(new_files)),
        "shared": shared,
        "resource_issues": resource_issues,
        "geometry": geometry,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="地图双链路审计（资源完整性 + 地形几何对比）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("地图双链路审计")
        print(f"  新链路（纯环境）    {report['new_link']}")
        print(f"  旧链路（含机器人）  {report['old_link']}")
        print()
        print("资源完整性（硬门禁）")
        if report["resource_issues"]:
            for issue in report["resource_issues"]:
                print(f"  [缺资源] {issue['link']}/{issue['file']}: {issue['missing']}")
        else:
            print("  两侧引用的资源都在 ✓")
        print()
        print("同名地形几何对比（报告，不判红——差异可能是有意的）")
        for item in report["geometry"]:
            mark = "一致" if item["same"] else "有差异"
            print(
                f"  {item['file']:<18} 新链路 {item['new_count']:4d} / 旧链路 {item['old_count']:4d}"
                f"  一致 {item['identical']:4d}  [{mark}]"
            )
            if not item["same"]:
                for extra in item["only_new"][:2]:
                    print(f"      仅新链路: {extra}")
                for extra in item["only_old"][:2]:
                    print(f"      仅旧链路: {extra}")
        print()
        print(f"  仅新链路有（{len(report['new_only'])}）：{report['new_only']}")
        print(f"  仅旧链路有（{len(report['old_only'])}）：{report['old_only']}")
        print()
        print("  说明：旧链路与 Go2 策略的 reference bundle 耦合，**不要为了'消除重复'直接删**；")
        print("       要迁移须先跑通 sim2sim 验收（见工具 docstring）。")

    return 2 if report["resource_issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
