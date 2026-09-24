"""族通用可训矩阵：**同一地形档在每台同族机型上都能真训**（"一键开训"的证据工具）。

与 `tools/validate_training_smoke.py` 的分工：那个按**档案**（profile）逐档冒烟；本工具按
**地形档**（`registry/terrains` 的口径）走**通用任务路径**（不带档案）逐档真跑——它回答的是
"这台机型（尤其是**新导入的同族机型**）能不能用族级通用架构训、能训哪几档"。

做法：对每台机型 × 每个本族 `ready` 的地形档，起一次 native_worker（小规模、1 iteration），
断言：退出码 0 + 生效配置 == 预览 + ONNX 导出 + **解析后的配方地形 == 该档 id**（防止静默退回平地）。
结果落 `tools/baselines/family_trainability.json`（矩阵基线，供后续对照）。

用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe tools/validate_family_trainability.py                 # 8 台 × 本族 ready 档
    PYTHONUTF8=1 .venv/Scripts/python.exe tools/validate_family_trainability.py --robot unitree_b2w
    PYTHONUTF8=1 .venv/Scripts/python.exe tools/validate_family_trainability.py --terrains plane,stairs --keep-going
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "tools" / "baselines" / "family_trainability.json"
ALL_ROBOTS = ("unitree_go2", "unitree_go1", "unitree_b2", "deeprobotics_lite3",
              "deeprobotics_m20", "unitree_b2w", "unitree_go2w", "zex-w")


def _family_of(robot_id: str) -> str | None:
    from backend.family_readiness import readiness

    return readiness(ROOT / "assets" / "robots" / robot_id).get("family")


def _terrains_for(robot_id: str) -> list[str]:
    from backend.family_readiness import readiness

    return list(readiness(ROOT / "assets" / "robots" / robot_id).get("trainable_terrain_profiles") or [])


def _task_for(terrain: str) -> str | None:
    """地形档 → 任务（技能 = 地形档 × 奖励档）：取任务表里**声明了该地形**的任务。

    任务表 = `registry/skills/velocity_base.json#tasks`（`backend.skill_registry.task_variants`）。
    族 Kit 提供的地形档（障碍释放 / 竞赛）在通用路径没有任务载体 ⇒ 返回 None（矩阵里记跳过，不记失败）。
    """
    from backend.skill_registry import task_variants

    for task_id, spec in task_variants().items():
        if str((spec or {}).get("terrain") or "") == terrain:
            return str(task_id)
    return None


def run_one(robot_id: str, terrain: str) -> dict:
    """走通用任务路径真跑一次；返回逐项判据。"""
    task = _task_for(terrain)
    if task is None:
        return {"robot": robot_id, "terrain": terrain, "ok": True, "skipped": True,
                "reason": "该地形档由族 Kit 提供（通用任务路径无任务载体），跳过",
                "returncode": None, "effective_matches_preview": None,
                "onnx_exported": None, "resolved_terrain": None,
                "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "tail": ""}
    # 判据链的**唯一实现**在 backend/trainability_check.py（导入后自动冒烟也调它）；
    # 本工具只是逐格调用并把结论摊成矩阵。`write_record=False`：别往 assets 源树里写记录。
    from backend import trainability_check

    record = trainability_check.check(
        ROOT / "assets" / "robots" / robot_id, terrain=terrain, task=task,
        timeout_s=1200, write_record=False,
    )
    return {
        "robot": robot_id, "terrain": terrain, "task": task, "skipped": False,
        "returncode": record["returncode"],
        "effective_matches_preview": record["effective_matches_preview"],
        "onnx_exported": record["onnx_exported"],
        "resolved_terrain": record["resolved_terrain"],
        "ok": record["status"] == "passed",
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "tail": record.get("tail", ""),
    }


def merge_baseline(results: list[dict]) -> tuple[list[dict], int]:
    """把本次跑出的行并入既有基线：本次覆盖到的 (机型, 地形档) 换新，其余原样保留。

    单机型复跑（`--robot X`，例如新导入一台机器后）不该把别的机型行抹掉——否则基线会退化成
    "最后一次跑的子集"，而它承担的是"全族 8 台逐档能不能训"的对照真值。保留行带各自
    `checked_at`，陈旧一眼可见（行数也打印出来）。返回 (全部行, 本次刷新的行数)。
    """
    merged: dict[tuple[str, str], dict] = {}
    if BASELINE.is_file():
        try:
            previous = json.loads(BASELINE.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        for row in previous.get("results") or []:
            key = (str(row.get("robot")), str(row.get("terrain")))
            merged[key] = {**row, "checked_at": row.get("checked_at") or previous.get("generated_at")}
    refreshed = 0
    for row in results:
        key = (str(row["robot"]), str(row["terrain"]))
        refreshed += 1
        merged[key] = {k: v for k, v in row.items() if k != "tail"}
    order = {robot: index for index, robot in enumerate(ALL_ROBOTS)}
    fallback_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ordered = [merged[key] for key in sorted(merged, key=lambda item: (order.get(item[0], 99), item[1]))]
    # 每行都要有日期：留着"没有 checked_at"的行，等于让读者分不清新证据与陈年行。
    return [{**row, "checked_at": row.get("checked_at") or fallback_date} for row in ordered], refreshed


def main() -> int:
    parser = argparse.ArgumentParser(description="族通用可训矩阵（通用任务路径真跑）")
    parser.add_argument("--robot", action="append", help="只跑这些机型（可重复；默认 8 台内置）")
    parser.add_argument("--terrains", type=str, default="", help="逗号分隔的地形档；默认取该机型本族 ready 档")
    parser.add_argument("--keep-going", action="store_true", help="单格失败也继续跑完再退出非零")
    args = parser.parse_args()

    robots = tuple(args.robot) if args.robot else ALL_ROBOTS
    pinned = [t.strip() for t in args.terrains.split(",") if t.strip()]
    results: list[dict] = []
    for robot_id in robots:
        terrains = pinned or _terrains_for(robot_id)
        family = _family_of(robot_id)
        print(f"[{robot_id}] family={family} 计划档={terrains}")
        for terrain in terrains:
            row = run_one(robot_id, terrain)
            results.append(row)
            if row.get("skipped"):
                print(f"  [SKIP] {terrain:18s} {row['reason']}")
                continue
            mark = "OK " if row["ok"] else "FAIL"
            print(f"  [{mark}] {terrain:18s} task={row.get('task')} rc={row['returncode']} "
                  f"生效==预览={row['effective_matches_preview']} onnx={row['onnx_exported']} "
                  f"resolved={row['resolved_terrain']}")
            if not row["ok"] and row["tail"]:
                print("        " + row["tail"].replace("\n", "\n        ")[-500:])
            if not row["ok"] and not args.keep_going:
                break

    failed = [row for row in results if not row["ok"]]
    skipped = [row for row in results if row.get("skipped")]
    rows, refreshed = merge_baseline(results)
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps({
        "schema": "family-trainability-1.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "scope": {"robots": list(robots), "terrains": pinned or "各机型本族 ready 档"},
        "note": "通用任务路径（不带档案）逐（机型 × 地形档）真跑矩阵；判据见本工具 docstring。"
                "规模 = smoke（2 envs × 1 iter），只作「能不能训」的证据，不代表训练质量。"
                "行按 (机型, 地形档) 合并：本次没跑到的行原样保留，其 checked_at 即上次实测日期。",
        "results": rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    graded = len(results) - len(skipped)
    print(f"\n矩阵：真跑 {graded - len(failed)}/{graded} 格通过，跳过 {len(skipped)} 格（族 Kit 档，"
          f"通用任务路径无载体）；基线 {BASELINE.relative_to(ROOT)} 更新 {refreshed} 行 / 共 {len(rows)} 行")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
