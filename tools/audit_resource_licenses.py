#!/usr/bin/env python3
"""N2：资源库许可**覆盖**门禁（`00_resources/` 84 个目录的许可分布）。

与 `tools/audit_licenses.py` 的分工（两者都关于许可，但**分母与判据不同**）：

| | 分母 | 判据 | 失败时该做什么 |
|---|---|---|---|
| `audit_licenses.py`（I5） | 14 个机器人包的**证据文件** | 逐条祖先链取证 + 与 `registry/licenses.json` 对账 | 补证据或登记缺口 |
| 本门禁（N2） | `00_resources/` 的 **84 个资源目录** | **覆盖率如实、缺口名单显式、不许悄悄恶化** | 评估该资源要不要用 |

## 判据为什么不是"覆盖率必须 ≥ X"

覆盖率**不是目标值** —— 上游项目本身可能就没有许可文件（我们无权替它补一个；
"记录未取证"是真话，"给它安一个许可"是假话，与 I5 同一条原则）。而且资源目录数会随上游快照变化。

所以本门禁守两件事：
1. **数字要如实存在**（分子/分母/分层：顶层有 / 仅深层有 / 完全没有）；
2. **零许可名单必须显式登记**：出现**新的**零许可目录 ⇒ 判红（先评估、再登记）；
   名单里的目录**拿到了**许可 ⇒ 也判红（名单过期就是谎言，改善同样要重新登记）。

## 边界

**静态扫描文件系统**：绿 = "许可文件的存在性分布如实且名单不透支"，**不判断**许可内容是否真适用于我们的用法
（那是 I5 逐条取证的活）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "00_resources"

#: 许可文件名规则（与 audit_licenses.py 同口径：license/licence/copying + 常见文本后缀）
LICENSE_NAME = re.compile(r"^(licen[cs]e|copying)(\.(md|txt|rst|html))?$", re.IGNORECASE)

#: **已登记的"完全没有许可文件"的目录**（2026-09-16 实测冻结）。
#: 出现新名字 ⇒ 判红；名单里的名字消失（拿到了许可）⇒ 也判红（名单要跟着事实走）。
EXPECTED_ZERO_LICENSE: frozenset[str] = frozenset({
    "1000framesai.com",
    "AMP_mjlab",
    "Dreamwaq",
    "LeggedSkillDeploy",
    "g1-manipulation-challenge",
    "go2_unitree_ros2",
    "go2w_sim2sim",
    "humanoid-motion-planning",
    "jie_3d_nav",
    "matrix_zsibot",
    "microduck-simulator",
    "references_1000framesai",
    "rl_sar_zoo",
    "robo_re",
    "robot_mujoco",
    "sim.stackforce.cc",
    "unitree-go2-slam-nav2",
    "unitree_go2_edu_movement",
})


def _has_top_license(directory: Path) -> bool:
    try:
        return any(item.is_file() and LICENSE_NAME.match(item.name) for item in directory.iterdir())
    except OSError:
        return False


def _has_any_license(directory: Path) -> bool:
    for item in directory.rglob("*"):
        try:
            if item.is_file() and LICENSE_NAME.match(item.name):
                return True
        except OSError:
            continue
    return False


def audit(root: Path | None = None) -> dict:
    base = root or RESOURCES
    if not base.is_dir():
        return {
            "ok": False,
            "problems": [f"资源目录不存在：{base}"],
            "scans_content": False,
        }
    dirs = sorted((item for item in base.iterdir() if item.is_dir()), key=lambda item: item.name)

    top: list[str] = []
    deep_only: list[str] = []
    zero: list[str] = []
    for directory in dirs:
        if _has_top_license(directory):
            top.append(directory.name)
        elif _has_any_license(directory):
            deep_only.append(directory.name)
        else:
            zero.append(directory.name)

    zero_set = set(zero)
    problems: list[str] = []
    for name in sorted(zero_set - set(EXPECTED_ZERO_LICENSE)):
        problems.append(
            f"{name}: **新出现的零许可目录** —— 上游快照里没有任何 LICENSE/COPYING。"
            "请先评估该资源是否要用；要用就登记进 EXPECTED_ZERO_LICENSE（并说明处置），"
            "否则它会静默留在资源库里"
        )
    for name in sorted(set(EXPECTED_ZERO_LICENSE) - zero_set):
        problems.append(
            f"{name}: 已登记的零许可目录**现在有许可文件了** —— 名单过期就是谎言，"
            "请核实后把它从 EXPECTED_ZERO_LICENSE 里移出"
        )

    total = len(dirs)
    with_any = len(top) + len(deep_only)
    return {
        "ok": not problems,
        "dirs_total": total,
        "with_top_license": len(top),
        "with_deep_license_only": len(deep_only),
        "zero_license": len(zero),
        "coverage_top_pct": round(100 * len(top) / total, 1) if total else 0.0,
        "coverage_any_pct": round(100 * with_any / total, 1) if total else 0.0,
        "zero_license_dirs": zero,
        "registered_zero_license": sorted(EXPECTED_ZERO_LICENSE),
        "problems": problems,
        # 如实声明边界
        "scans_content": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="N2 资源库许可覆盖门禁")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 78)
        print("N2 资源库许可覆盖（00_resources，只看文件存在性）")
        print("=" * 78)
        if "dirs_total" in report:
            print(f"目录总数 {report['dirs_total']}｜顶层有许可 {report['with_top_license']}"
                  f"（{report['coverage_top_pct']}%）｜仅深层有 {report['with_deep_license_only']}"
                  f"｜**完全没有 {report['zero_license']}**（{report['coverage_any_pct']}% 含线索）")
            if report["zero_license_dirs"]:
                print(f"零许可目录（已登记）：{', '.join(report['zero_license_dirs'])}")
        if report["problems"]:
            print("-" * 78)
            for item in report["problems"]:
                print(f"✗ {item}")
        else:
            print("-" * 78)
            print("✓ 覆盖数字如实，零许可名单与事实一致（未出现新缺口、名单未过期）")
        print("注意：**覆盖率不是目标值** —— 上游可能本就没有许可文件；本门禁守的是"
              "'不能悄悄恶化 + 名单必须显式'，且**不判断许可内容是否适用于我们的用法**"
              "（那是 I5 逐条取证的活）。")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
