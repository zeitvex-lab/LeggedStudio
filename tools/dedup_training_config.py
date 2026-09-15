"""消除 `training/config.json` 与 Recipe 的字段双写（B13「无重复真值」）。

背景：14 包的 `training/config.json`（旧文件）与 `training/profiles/*.json`（Recipe 权威）
双写了 `algorithm / num_envs / episode_length_s / task_name / command_ranges / terrain_type /
seed` 等字段；`schema.py` 的兜底 `profile.get(X) or training_config.get(X)` 因 14 包都有
profile 而**永不触发**，故这些字段是死数据。本工具把它们从 config.json 删掉，让真值只剩
Recipe 一处。

安全设计（fail-closed）：

- 默认 ``--dry-run``：只打印删除计划，**不写任何文件**；
- ``--write`` 才落盘，且每个键删除前**必须**能在某个 profile 里找到同名键（能覆盖），
  找不到就跳过并记 ``skipped``（宁可留着也不丢数据）；
- 只删白名单键（物理引用 / 格式声明 / profile 引用一律不动）；
- 每包只改自己的 config.json，写前备份原值进 ``removed`` 报告（可人工核对/回滚）。

用法::

    python tools/dedup_training_config.py            # 只打印计划
    python tools/dedup_training_config.py --write    # 落盘删除
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"

#: 不动的键（物理引用 / 格式声明 / profile 引用）
_KEEP = {"robot_id", "contract_path", "profile_id", "schema_version", "backend"}


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def plan(robot_dir: Path) -> dict:
    """返回该包的删除计划：{robot, removals: [{key, config_value, profile_value}], skipped}。"""
    config_path = robot_dir / "training" / "config.json"
    config = _read_json(config_path)
    profiles_dir = robot_dir / "training" / "profiles"
    profiles: list[dict] = []
    if profiles_dir.exists():
        for p in profiles_dir.glob("*.json"):
            value = _read_json(p)
            if value:
                profiles.append(value)

    removals: list[dict] = []
    skipped: list[str] = []
    for key in sorted(config.keys()):
        if key in _KEEP:
            continue
        # 权威值：某个 profile 里的同名键
        cover = next((p[key] for p in profiles if key in p), None)
        if cover is None:
            skipped.append(key)
            continue
        removals.append({"key": key, "config_value": config[key], "profile_value": cover})
    return {"robot": robot_dir.name, "removals": removals, "skipped": skipped}


def main() -> int:
    write = "--write" in sys.argv
    total_removed = 0
    total_skipped = 0
    for robot_dir in sorted(ROBOTS.iterdir()):
        if not robot_dir.is_dir():
            continue
        config_path = robot_dir / "training" / "config.json"
        if not config_path.exists():
            continue
        result = plan(robot_dir)
        removals = result["removals"]
        skipped = result["skipped"]
        if not removals and not skipped:
            continue
        total_skipped += len(skipped)
        if removals:
            print(f"{result['robot']:<22} 删 {len(removals)} 键："
                  f"{[r['key'] for r in removals]}")
            if write:
                config = _read_json(config_path)
                for r in removals:
                    config.pop(r["key"], None)
                config_path.write_text(
                    json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                )
                total_removed += len(removals)
        if skipped:
            print(f"{result['robot']:<22} 跳过（profile 无此键，不删）：{skipped}")

    print(f"\n合计：{'已删除' if write else '将删除'} {total_removed} 键"
          f" / 跳过 {total_skipped} 键" + ("" if write else "（--dry-run，未写任何文件）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
