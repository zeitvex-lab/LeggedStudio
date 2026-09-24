"""v2 契约观测段的投影同步：把 ``contract_legacy_v2.json`` 的 ``observation`` 收敛为 v3 投影。

## 为什么需要它

`contract_legacy_v2.json` 的观测段在 v3 迁移时是**各自手写**的，此后与 v3 分家却无人察觉：

| 机型 | v2 观测段（陈旧） | v3 真值 |
|---|---|---|
| unitree_go2 | 缺 `commands`、多 `base_lin_vel` | 6 项含 `commands` |
| unitree_go1 | 少 `base_lin_vel`（名字和 45 ≠ 声明 48，自身就不自洽） | 7 项含 `base_lin_vel` |
| unitree_go2w | 旧项名（`command` / `wheel_joint_pos_rel` / `wheel_joint_vel_rel` / `actions`） | 6 项 |
| zex-w | 旧项名且缺 `wheel_vel` | 7 项含 `wheel_vel`(4) |

而 v2 恰好是 **create 校验链与包索引记录的执行输入**（B36），预设记录又直接把它端给
训练配置页 ⇒ 页面上显示的观测骨架是旧的那份，与真正上场的 Kit 观测不是一回事。

修法沿用"参数单一家"裁决（B2/2）：v3 是真值，v2 退化为投影（组件名 + 维度）。
投影函数在 ``contracts/contract_loader.project_observation_to_legacy``，本工具只负责
**逐包核对与落盘**，不另写第二份投影逻辑。

用法：
    python tools/sync_legacy_observation.py            # 只核对（CI 用）
    python tools/sync_legacy_observation.py --write     # 把投影写回 v2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.contract_loader import (  # noqa: E402
    load_contract,
    load_legacy_contract,
    project_observation_to_legacy,
)

ROBOTS_DIR = ROOT / "assets" / "robots"


def _legacy_path(robot_dir: Path) -> Path:
    return robot_dir / "contract_legacy_v2.json"


def _observation_of(contract: dict) -> dict:
    observation = contract.get("observation")
    return observation if isinstance(observation, dict) else {}


def audit(robots_dir: Path = ROBOTS_DIR) -> dict:
    """逐包核对 v2 观测段是否等于 v3 投影。只读。"""
    drifted: list[str] = []
    skipped: list[str] = []
    paired = 0
    for robot_dir in sorted(p for p in robots_dir.iterdir() if p.is_dir()):
        legacy_path = _legacy_path(robot_dir)
        if not legacy_path.exists():
            skipped.append(f"{robot_dir.name}: 无 contract_legacy_v2.json")
            continue
        v3 = load_contract(robot_dir)
        v2 = load_legacy_contract(robot_dir)
        if v3 is None or v2 is None:
            skipped.append(f"{robot_dir.name}: 单侧契约缺失（v3={'有' if v3 else '无'} v2={'有' if v2 else '无'}）")
            continue
        if not _observation_of(v3).get("components"):
            skipped.append(f"{robot_dir.name}: v3 无字段级观测组件（v2 仍是唯一表述）")
            continue
        paired += 1
        projected = _observation_of(project_observation_to_legacy(v3, v2))
        current = _observation_of(v2)
        if current.get("components") != projected.get("components") or current.get("dimension") != projected.get("dimension"):
            drifted.append(
                f"{robot_dir.name}: v2 观测段 ≠ v3 投影\n"
                f"    现 v2: {current.get('dimension')} 维 {current.get('components')}\n"
                f"    投影 : {projected.get('dimension')} 维 {projected.get('components')}"
            )
    return {"ok": not drifted, "drifted": drifted, "skipped": skipped, "paired": paired}


def write(robots_dir: Path = ROBOTS_DIR) -> int:
    """把投影写回 v2（保持 2 空格缩进 + 末尾换行，往返逐字节稳定）。只改观测段。"""
    changed = 0
    for robot_dir in sorted(p for p in robots_dir.iterdir() if p.is_dir()):
        legacy_path = _legacy_path(robot_dir)
        if not legacy_path.exists():
            continue
        v3 = load_contract(robot_dir)
        v2 = load_legacy_contract(robot_dir)
        if v3 is None or v2 is None or not _observation_of(v3).get("components"):
            continue
        projected = project_observation_to_legacy(v3, v2)
        if projected == v2:
            continue
        legacy_path.write_text(
            json.dumps(projected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=""
        )
        changed += 1
        print(f"  已投影 {robot_dir.name}: {_observation_of(v2).get('dimension')} → {_observation_of(projected).get('dimension')} 维")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="v2 契约观测段的 v3 投影同步")
    parser.add_argument("--write", action="store_true", help="把投影写回 v2（默认只核对）")
    args = parser.parse_args()

    if args.write:
        changed = write()
        print(f"[legacy-obs] 已改写 {changed} 个包的观测段")
        return 0

    report = audit()
    print(f"[legacy-obs] 核对 {report['paired']} 个 v3/v2 配对包；跳过 {len(report['skipped'])}")
    for item in report["skipped"]:
        print(f"  - 跳过 {item}")
    if report["drifted"]:
        print(f"\n[legacy-obs] {len(report['drifted'])} 个包的观测段与 v3 分家：")
        for item in report["drifted"]:
            print(f"  - {item}")
        print("\n跑 `python tools/sync_legacy_observation.py --write` 收敛（v3 是真值，v2 是投影）。")
        return 1
    print("\n[legacy-obs] 全部一致：v2 观测段 == v3 投影")
    return 0


if __name__ == "__main__":
    sys.exit(main())
