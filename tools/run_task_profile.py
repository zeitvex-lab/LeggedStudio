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
    # 任务插件感知绑定（两层组合）：有 plugin_id 时实例化其 perception/command 声明，
    # readiness 不 ok 就 fail-closed（"声明可跑"不等于"真能跑"）。
    plugin_report = None
    if task.get("plugin_id"):
        from backend.task_plugins import instantiate_task_plugin

        plugin_report = instantiate_task_plugin(task["plugin_id"])
        readiness = plugin_report.get("readiness") or {}
        if not readiness.get("ok", False):
            return {"task_id": task["task_id"], "verdict": "blocked",
                    "reason": f"任务插件 {task['plugin_id']} readiness 不通过",
                    "blockers": readiness.get("blockers")}
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
        "plugin_id": task.get("plugin_id"),
        "plugin_readiness_ok": bool((plugin_report or {}).get("readiness", {}).get("ok")),
        "controller": controller,
        "map": task["assembly"]["map_id"],
        "waypoints": waypoints,
        "arrived": arrived,
        "collisions": collisions,
        "steps": result.get("steps"),
        "verdict": "pass" if ok else "fail",
        "criteria": {k: crit[k] for k in ("arrival_rate_min", "collision_max")},
    }


def run_follow(task: dict, *, seconds: float = 30.0, dt: float = 0.1) -> dict:
    """跟随类任务 headless 判据（2026-10-01）：移动目标 + 距离带随行模型。

    判据 = hold_ratio（距离带 [band_min, band_max] 内拍数占比）≥ 档位阈值。
    模型：目标沿折线匀速走；跟随机朝目标转向，速度 = 目标速度 + 距离误差修正
    （期望距离 = 带中值）——这是"名义跟随能力"的探针：名义模型都守不住带，
    才轮到怀疑策略/控制器；名义模型能守，实机差距归控制器调参。
    """
    import math

    band_min, band_max = task["criteria"]["distance_band_m"]
    hold_min = float(task["criteria"]["hold_ratio_min"])
    desired = (band_min + band_max) / 2.0
    kp = 2.0  # 距离误差 → 速度修正
    max_v = 1.2

    target_route = [(0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (0.0, 3.0), (0.0, 0.0)]
    target_speed = 0.5
    robot_x, robot_y, robot_yaw = 1.5, -1.5, 0.0
    target_t = 0.0
    seg = 0
    tx, ty = target_route[0]
    in_band = 0
    total = int(seconds / dt)
    min_dist = float("inf")
    max_dist = 0.0
    for _ in range(total):
        ax, ay = target_route[seg]
        bx, by = target_route[(seg + 1) % len(target_route)]
        seg_len = math.hypot(bx - ax, by - ay)
        target_t += target_speed * dt
        while target_t >= seg_len:
            target_t -= seg_len
            seg = (seg + 1) % len(target_route)
            ax, ay = target_route[seg]
            bx, by = target_route[(seg + 1) % len(target_route)]
            seg_len = math.hypot(bx - ax, by - ay)
        ratio = target_t / seg_len
        tx, ty = ax + (bx - ax) * ratio, ay + (by - ay) * ratio

        dist = math.hypot(tx - robot_x, ty - robot_y)
        bearing = math.atan2(ty - robot_y, tx - robot_x)
        yaw_err = math.atan2(math.sin(bearing - robot_yaw), math.cos(bearing - robot_yaw))
        # 速度 = 目标速度 + 距离误差修正（远则追、近则让）
        v = max(0.0, min(max_v, target_speed + kp * (dist - desired) * math.cos(yaw_err)))
        wz = max(-1.5, min(1.5, 2.0 * yaw_err))
        robot_yaw += wz * dt
        robot_x += v * math.cos(robot_yaw) * dt
        robot_y += v * math.sin(robot_yaw) * dt

        dist = math.hypot(tx - robot_x, ty - robot_y)
        min_dist = min(min_dist, dist)
        max_dist = max(max_dist, dist)
        if band_min <= dist <= band_max:
            in_band += 1
    hold_ratio = round(in_band / total, 3)
    ok = hold_ratio >= hold_min
    return {
        "task_id": task["task_id"],
        "hold_ratio": hold_ratio,
        "hold_ratio_min": hold_min,
        "distance_band_m": [band_min, band_max],
        "distance_range": [round(min_dist, 2), round(max_dist, 2)],
        "verdict": "pass" if ok else "fail",
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
    elif cls == "follow":
        report = run_follow(task)
    elif cls == "traversal":
        print("越障类任务请用: adapters/mjlab/.venv/Scripts/python.exe tools/validate_traversal_progress.py --profile <档案>")
        return 3
    elif cls == "follow":
        report = run_follow(task)
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if report["verdict"] == "pass" else 1
    else:
        print(f"任务类 {cls!r} 的 headless 判据未建（{task['task_id']} 当前端口: {task['availability']}）")
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())


