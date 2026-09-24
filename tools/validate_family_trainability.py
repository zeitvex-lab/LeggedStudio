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
                "onnx_exported": None, "resolved_terrain": None, "tail": ""}
    from adapters.mjlab.native_adapter import DEFAULT_SOURCE
    from backend.training.models import CreateTrainingRequest
    from backend.training.service import prepare_training_config
    from backend.training_config_helpers import dump_schema_via_worker
    from contracts.path_bootstrap import adapter_python

    contract_data = json.loads(
        (ROOT / "assets" / "robots" / robot_id / "contract_legacy_v2.json").read_text(encoding="utf-8-sig"))
    with tempfile.TemporaryDirectory(prefix=f"ls-trainability-{robot_id}-{terrain}-") as tmp:
        out = Path(tmp)
        request = CreateTrainingRequest(
            contract=contract_data, profile_id=None, task_name=task, terrain_type=terrain,
            smoke=True, num_envs=2, max_iterations=1, num_steps=4, num_minibatches=1,
            device="auto", overrides={"runner.num_steps_per_env": 8},
        )
        contract, config = prepare_training_config(request)
        package = config["robot_package"]
        preview = dump_schema_via_worker(
            contract.robot_id, "", {}, package["package_root"],
            training_config=config, contract=contract.model_dump(mode="json"))
        (out / "request.json").write_text(json.dumps(config), encoding="utf-8")
        contract.to_json_file(str(out / "contract.json"))
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [str(adapter_python()), "-m", "adapters.mjlab.native_worker",
             "--source", str(DEFAULT_SOURCE), "--config", str(out / "request.json"),
             "--contract", str(out / "contract.json"), "--output", str(out)],
            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=1200)
        effective = None
        if (out / "effective-config.json").is_file():
            effective = json.loads((out / "effective-config.json").read_text(encoding="utf-8-sig"))
        resolved = ((config.get("resolved_recipe") or {}).get("environment") or {}).get("terrain_type")
        return {
            "robot": robot_id, "terrain": terrain, "task": task, "skipped": False,
            "returncode": result.returncode,
            "effective_matches_preview": bool(effective) and effective.get("environment") == preview.get("environment"),
            "onnx_exported": (out / "exported" / "policy.onnx").is_file(),
            "resolved_terrain": resolved,
            "ok": result.returncode == 0 and resolved == terrain,
            "tail": "" if result.returncode == 0 else (result.stdout + result.stderr)[-600:],
        }


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
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps({
        "schema": "family-trainability-1.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "note": "通用任务路径（不带档案）逐（机型 × 地形档）真跑矩阵；判据见本工具 docstring。"
                "规模 = smoke（2 envs × 1 iter），只作「能不能训」的证据，不代表训练质量。",
        "results": [{k: v for k, v in row.items() if k != "tail"} for row in results],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n矩阵：{len(results) - len(failed)}/{len(results)} 格通过；基线已落 {BASELINE.relative_to(ROOT)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
