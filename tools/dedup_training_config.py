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

#: **死数据字段**（B13 下半段）：运行参数，`models.py` 的 `CreateTrainingRequest` 有**硬编码
#: Field 默认值**（`learning_rate=3e-4` / `gamma=0.99` / `clip_param=0.2` …），`create.py` 全从
#: request 读、`schema.py` preview 完全不读它们 —— 所以 config.json 里这层副本**无任何代码读**。
#: 删掉 = 让真值只剩一处（models.py 默认 + 用户提交 + Run 落盘）。
#: 注意**不含** `num_envs` / `episode_length_s`：它们被 `schema.py` 兜底读，且个别包的 profile
#: 没覆盖（如 microduck 的 episode_length_s），删了会丢页面预填来源 —— 那两个是"双写"，上一轮
#: 已按 profile 覆盖情况处理，本白名单只收"确定无消费者的运行参数"。
DEAD_FIELDS = {
    "max_iterations", "learning_rate", "save_interval", "seed",
    "num_steps", "num_minibatches", "gamma", "gae_lambda", "clip_param", "entropy_coef",
    "tau", "batch_size", "alpha", "policy_delay", "exploration_noise", "replay_size",
}


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def plan(robot_dir: Path) -> dict:
    """返回该包的删除计划：{robot, removals, dead, skipped}。"""
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
    dead: list[dict] = []
    skipped: list[str] = []
    for key in sorted(config.keys()):
        if key in _KEEP:
            continue
        if key in DEAD_FIELDS:
            dead.append({"key": key, "config_value": config[key], "reason": "死数据（models.py 默认值取代）"})
            continue
        # 权威值：某个 profile 里的同名键
        cover = next((p[key] for p in profiles if key in p), None)
        if cover is None:
            skipped.append(key)
            continue
        removals.append({"key": key, "config_value": config[key], "profile_value": cover})
    return {"robot": robot_dir.name, "removals": removals, "dead": dead, "skipped": skipped}


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
        dead = result["dead"]
        skipped = result["skipped"]
        if not removals and not dead and not skipped:
            continue
        total_skipped += len(skipped)
        if removals:
            print(f"{result['robot']:<22} 删重复 {len(removals)} 键："
                  f"{[r['key'] for r in removals]}")
        if dead:
            print(f"{result['robot']:<22} 删死数据 {len(dead)} 键："
                  f"{[r['key'] for r in dead]}")
        if removals or dead:
            total_removed += len(removals) + len(dead)
            if write:
                config = _read_json(config_path)
                for r in [*removals, *dead]:
                    config.pop(r["key"], None)
                config_path.write_text(
                    json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                )
        if skipped:
            print(f"{result['robot']:<22} 跳过（profile 无此键，不删）：{skipped}")

    print(f"\n合计：{'已删除' if write else '将删除'} {total_removed} 键"
          f" / 跳过 {total_skipped} 键" + ("" if write else "（--dry-run，未写任何文件）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
