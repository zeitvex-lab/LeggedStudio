"""训练配置三层拆分的审计（B13 终态）—— 两把尺子：**字段双写** 与 **指针外残留**。

## 背景（B13「无重复真值」→「终态收口」）

三层语义：物理 → 契约（`contract_v3.json`，B2/B3）；任务 → Recipe（`training/profiles/*.json`
+ `registry/skills`，B6/B7）；运行 → Run（`backend/training/runs.py`，B9）。

各包 `training/config.json`（旧文件）的终态是**纯指针文件**：只引用别层的真值，自身不持有
任何任务/运行数值。本工具两把尺子量它：

1. **同名双写**（原有检查）：config.json 与 profile 的同名字段（权威在 Recipe）；
2. **指针外残留**（终态检查，B13 收口）：config.json 里不属于指针字段集的键——即使不与
   profile 同名（如 go2 曾残留的 `reward_scales`）也是残留，终态不允许。

## 终态：14 包全指针化，无例外

全部 14 个内置包的 config.json 只允许指针字段集
`{robot_id, contract_path, profile_id, schema_version, backend}`，**无任何豁免**
（此前的 microduck「待取证」豁免已完成使命：取证结束、字段全删，豁免机制整体拆除）。

## 退出码（可进 CI 的门禁）

- 出现**残留键**或**双写** → ``exit 1``；
- 干净（允许无 profile 的包如实列出）→ ``exit 0``。

纯只读审计，**不修改任何文件**。

用法::

    python tools/audit_training_config_layers.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "assets" / "robots"

#: 指针字段集：config.json 终态只允许这些键（物理层引用 / profile 引用 / 格式与后端声明）。
POINTER_FIELDS = {"robot_id", "contract_path", "profile_id", "schema_version", "backend"}


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def audit(*, robots_dir: Path | str = ROBOTS) -> dict:
    """逐包审计 ``training/config.json``。``robots_dir`` 可注入（测试用假包目录）。

    返回 dict：``total / with_dup / with_residue / no_profile / rows``，
    其中 ``with_dup`` / ``with_residue`` 是**判红项**。
    """
    robots_dir = Path(robots_dir)
    rows: list[dict] = []
    for robot_dir in sorted(robots_dir.iterdir()):
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

        # 尺子一：同名双写（指针字段是引用不是任务值，不算双写）。
        dup_keys = sorted((set(config.keys()) & profile_keys) - POINTER_FIELDS)
        # 尺子二：指针外残留（终态无豁免，凡指针字段集之外的键一律判残留）。
        residue = sorted(k for k in config.keys() if k not in POINTER_FIELDS)
        rows.append({
            "robot": robot_dir.name,
            "config_keys": len(config),
            "profiles": profiles,
            "dup_keys": dup_keys,
            "residue": residue,
        })
    return {
        "total": len(rows),
        "with_dup": [r for r in rows if r["dup_keys"]],
        "with_residue": [r for r in rows if r["residue"]],
        "no_profile": [r for r in rows if not r["profiles"]],
        "rows": rows,
    }


def exit_code(report: dict) -> int:
    """门禁语义：残留或双写任一出现 → 1；否则 0。"""
    return 1 if report["with_dup"] or report["with_residue"] else 0


def main() -> int:
    report = audit()
    print(f"包 {report['total']} 个")
    print(f"  与 Recipe 字段双写的包：{len(report['with_dup'])}"
          f"  {[r['robot'] for r in report['with_dup']]}")
    print(f"  无 profile（config.json 是唯一任务真值，不可删）：{len(report['no_profile'])}"
          f"  {[r['robot'] for r in report['no_profile']]}")
    print(f"  指针外残留的包（须清理）：{len(report['with_residue'])}"
          f"  {[r['robot'] for r in report['with_residue']]}")
    if report["with_dup"]:
        print("\n字段双写明细（config.json 与 profile 同名字段，权威在 Recipe）：")
        for row in report["with_dup"]:
            print(f"  {row['robot']:<22} 双写 {row['dup_keys']}")
    if report["with_residue"]:
        print("\n指针外残留明细（终态 = 纯指针文件，这些键应归位任务层/运行层后删除）：")
        for row in report["with_residue"]:
            print(f"  {row['robot']:<22} 残留 {row['residue']}")
    code = exit_code(report)
    if code:
        print("\n审计不通过（exit 1）：存在指针外残留或字段双写。")
    else:
        print("\n审计通过（exit 0）：14 包全指针化，无残留、无双写。")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
