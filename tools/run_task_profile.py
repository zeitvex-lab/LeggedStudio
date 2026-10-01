#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_task_profile.py — 任务档运行器（高级仿真 = 任务插件运行时，2026-10-01）。

**定位**（用户 2026-09-30）：高级仿真的意义 = 任务作为机器人的插件，在基础仿真里
组装调试，换实机调试时间。本工具是任务档（registry/tasks/profiles.json）的 CLI 端：
选任务 → 解析装配（地图/航点/控制器）→ 跑 → 按该档判据出 verdict。

导航类任务走与 route_regression 同一条积分器/到达判据（tools/dwa_ab_check.simulate，
三端口径同源）；越障类走 validate_traversal_progress；跟随类浏览器专属（headless 判据
待建，本工具如实报 not_runnable）。

用法：
  python tools/run_task_profile.py --task goal_nav_warehouse [--controller follow|dwa|geometric|mpc]
  python tools/run_task_profile.py --list
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REGISTRY = ROOT / "registry" / "tasks" / "profiles.json"


def load_task(task_id: str) -> dict:
    data = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
    for p in data["profiles"]:
        if p["task_id"] == task_id:
            return p
    raise SystemExit(f"任务档不存在: {task_id}（可用 --list 查看）")


def run_navigation(task: dict, controller: str) -> dict:
    from backend.scenario_maps import MAPS
    from tools.dwa_ab_check import simulate

    w = MAPS[task["assembly"]["map_id"]]
    waypoints = w["default_waypoints"]
    obstacles = [list(o) for o in (w.get("obstacles") or [])]
    from tools.route_regression import reference_path
    from tools.dwa_ab_check import DwaParams
    from backend.runtime_registry import load_registry

    spec = load_registry("motion_commands")
    turn_gain = float((spec.get("follow_controller") or {}).get("kp_yaw", 1.8))
    path = reference_path(task["assembly"]["map_id"], waypoints, obstacles)
    result = simulate(
        controller,
        waypoints,
        path,
        obstacles,
        dt=0.1,
        max_steps=3000,
        tolerance=0.2,
        params=DwaParams.from_registry(),
        turn_gain=turn_gain,
    )
    crit = task["criteria"]
    arrived = bool(result.get("reached"))
    collisions = int(result.get("collision_steps", 0))
    ok = arrived and collisions <= crit["collision_max"]
    return {
        "task_id": task["task_id"],
        "controller": controller,
        "map": task["assembly"]["map_id"],
        "waypoints": waypoints,
        "arrived": arrived,
        "collisions": collisions,
        "steps": result.get("steps"),
        "verdict": "pass" if ok else "fail",
        "criteria": {k: crit[k] for k in ("arrival_rate_min", "collision_max")},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="任务档运行器（高级仿真 CLI 端）")
    ap.add_argument("--task", default=None)
    ap.add_argument("--controller", default=None, help="导航类任务可换控制器（follow/dwa/geometric/mpc）")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list or not args.task:
        data = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
        for p in data["profiles"]:
            print(f"  {p['task_id']:28s} [{p['class']:10s}] {p['display_name']} — {p['summary']}")
        return 0

    task = load_task(args.task)
    cls = task["class"]
    if cls in ("navigation",):
        controller = args.controller or task["assembly"]["controller"] or "follow"
        report = run_navigation(task, controller)
    elif cls == "traversal":
        print("越障类任务请用: adapters/mjlab/.venv/Scripts/python.exe tools/validate_traversal_progress.py --profile <档案>")
        return 3
    else:
        print(f"任务类 {cls!r} 的 headless 判据未建（{task['task_id']} 当前端口: {task['availability']}）")
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
