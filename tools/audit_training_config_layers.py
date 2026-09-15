"""训练配置三层拆分的审计（B13）—— 检测 `training/config.json` 与 Recipe 的**字段双写**。

## 背景（B13「无重复真值」）

三层语义：物理 → 契约（`contract_v3.json`，B2/B3）；任务 → Recipe（`training/profiles/*.json`
+ `registry/skills`，B6/B7）；运行 → Run（`backend/training/runs.py`，B9）。

但各包 `training/config.json`（旧文件）里仍混装着 `num_envs / task_name / terrain /
command_ranges / reward_scales / episode_length_s / algorithm` 等字段，与 Recipe 的 profile
**双写**——`schema.py` 里的 `profile.get(X) or training_config.get(X)` 回退链就是现场。
B13 要消除这份双写，让每层字段只有一处真值。

## 本工具做什么

纯只读审计：逐包对比 `training/config.json` 与 `training/profiles/*.json` 的**同名字段**，
报告哪些字段双写、权威在哪层。**不修改任何文件**（先有尺子，再收敛）。

用法::

    python tools/audit_training_config_layers.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def audit() -> dict:
    rows: list[dict] = []
    for robot_dir in sorted(ROBOTS.iterdir()):
        if not robot_dir.is_dir():
            continue
        training_dir = robot_dir / "training"
        config_path = training_dir / "config.json"
        profiles_dir = training_dir / "profiles"
        if not config_path.exists():
            continue
        config = _read_json(config_path)
        profile_keys: set[str] = set()
        profiles: list[str] = []
        if profiles_dir.exists():
            for profile_path in sorted(profiles_dir.glob("*.json")):
                profile = _read_json(profile_path)
                if not profile:
                    continue
                profiles.append(profile_path.name)
                profile_keys.update(profile.keys())

        dup_keys = sorted(set(config.keys()) & profile_keys)
        # 非「重复真值」的键，不算双写：
        # - robot_id / contract_path：物理层引用（指向契约）；
        # - profile_id：config.json 引用哪个 profile（引用，非任务值）；
        # - schema_version / backend：文件格式声明与后端标识，不是任务/运行数值。
        non_duplicate = {"robot_id", "contract_path", "profile_id", "schema_version", "backend"}
        real_dups = [k for k in dup_keys if k not in non_duplicate]
        rows.append({
            "robot": robot_dir.name,
            "config_keys": len(config),
            "profiles": profiles,
            "dup_keys": real_dups,
        })
    return {
        "total": len(rows),
        "with_dup": [r for r in rows if r["dup_keys"]],
        "no_profile": [r for r in rows if not r["profiles"]],
        "rows": rows,
    }


def main() -> int:
    report = audit()
    print(f"包 {report['total']} 个")
    print(f"  与 Recipe 字段双写的包：{len(report['with_dup'])}"
          f"  {[r['robot'] for r in report['with_dup']]}")
    print(f"  无 profile（config.json 是唯一任务真值，不可删）：{len(report['no_profile'])}"
          f"  {[r['robot'] for r in report['no_profile']]}")
    if report["with_dup"]:
        print("\n字段双写明细（config.json 与 profile 同名字段，权威在 Recipe）：")
        for row in report["with_dup"]:
            print(f"  {row['robot']:<22} 双写 {row['dup_keys']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
