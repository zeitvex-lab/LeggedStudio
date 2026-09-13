#!/usr/bin/env python3
"""H11 A/B —— 同一条路线上「势场」vs「DWA」两种局部策略的对照。

**为什么要做这个 A/B**：任务清单 H11 的验收到此为止只写了"我们只有 A*/势场"。势场
（``adapters/mjlab/nav_avoidance.compute_avoidance_command``）是"吸引 + 斥力"的**反应式**控制器，
DWA（``backend.dwa_planner.plan_local``）是"采样择优"的**预测式**规划器。两者在同一张地图、
同一组航点、同一套障碍下各跑一遍纯运动学仿真，用同一组指标（是否到达 / 最小净空 / 碰撞步数）
对比——报告是数据，不是说法。

**口径**：
* 参考路径（仅 DWA 用）来自 ``map_editor_api.plan_map_route``（与全局规划同一实现）；
* DWA 参数来自 ``registry/motion_commands.json#local_planner``（唯一真值）；
* 势场转向增益取 ``registry/motion_commands.json#follow_controller.kp_yaw``（同源，不硬编码）；
* 到达容差取 ``registry/arrival_criteria.json``（H10 单一真值）；
* 运动学：两侧都用**差速**积分（势场的世界系速度先转成"期望朝向 + 前向速度"），避免"一个全向一个差速"的不公平对比。

用法：
    python tools/dwa_ab_check.py                 # 默认地图，人类可读
    python tools/dwa_ab_check.py --json          # 机器可读
    python tools/dwa_ab_check.py --map open_field --waypoints "0,0;1,-2;3,-2"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.dwa_planner import (  # noqa: E402
    DwaParams,
    min_clearance,
    normalize_angle,
    plan_local,
)
from backend.scenario_maps import MAPS  # noqa: E402

#: 「几何跟踪」第三侧 = ``backend/geometric_tracker.py``（参数与控制律逐项取自
#: ``00_resources/jie_3d_nav/octo_planner/src/d1_controller.cpp``）。A/B 用**同一实现**，
#: 不在这里另抄一份——避免"对照用的"与"产品用的"两套代码（H10/H12 修过的老问题）。
from backend.geometric_tracker import (  # noqa: E402
    GeometricParams,
    command_from_target,
    select_tracking_target,
)

#: 「产品默认」第四侧 = ``backend/follow_controller.py``（H12）。加它是因为回归原先只测
#: 三个"算法候选"，而浏览器实际跑的是这个状态机 —— 不测产品实际执行器，回归就没有意义。
from backend.follow_controller import FollowController  # noqa: E402


def _parse_waypoints(text: str | None, map_id: str) -> list[list[float]]:
    if text:
        return [[float(a), float(b)] for a, b in (pair.split(",") for pair in text.split(";"))]
    defaults = MAPS.get(map_id, {}).get("default_waypoints") or []
    if len(defaults) >= 2:
        return [[float(p[0]), float(p[1])] for p in defaults]
    return [[-3.0, -3.0], [3.0, 3.0]]


def reference_path(
    map_id: str, waypoints: list[list[float]], obstacles: list[list[float]]
) -> list[list[float]]:
    """用全局规划器（A*）求参考折线——DWA 用它算 progress。"""
    from backend.map_editor_api import PlanRequest, plan_map_route

    result = asyncio.run(
        plan_map_route(
            PlanRequest(map_id=map_id, obstacles=obstacles, waypoints=waypoints, algorithm="astar")
        )
    )
    path = result.get("combined_path") or []
    return path if len(path) >= 2 else list(waypoints)


def simulate(
    mode: str,
    waypoints: list[list[float]],
    path: list[list[float]],
    obstacles: list[list[float]],
    *,
    dt: float,
    max_steps: int,
    tolerance: float,
    params: DwaParams,
    turn_gain: float,
    trace_every: int = 0,
) -> dict[str, Any]:
    """纯运动学跑一条路线；两侧共用同一积分器与同一到达判据。"""
    from adapters.mjlab.nav_avoidance import compute_avoidance_command

    x, y, yaw = float(waypoints[0][0]), float(waypoints[0][1]), 0.0
    index = 1
    track_index = 0  # 几何跟踪在参考路径上的追踪点下标
    collisions = 0
    min_clear = float("inf")
    reached = False
    step = 0
    trace: list[list[float]] = []
    prev_v, prev_wz = 0.0, 0.0  # 上一拍速度 → 喂进 DWA 动态窗口（真实闭环：窗口绕当前速度开）
    geo_params = GeometricParams.from_registry() if mode == "geometric" else None
    # ``follow`` = **产品实际默认执行器**（H12 ``backend/follow_controller.py``）。它自带到达判定
    # 与终止原因，但这里**只取它的 cmd**，到达仍用本函数的统一判据 —— 否则"自带判据"的 follow
    # 与"统一判据"的其它控制器不可比，回归数字就是假的。
    #
    # **必须喂参考路径、而不是手填航点**：产品浏览器侧 ``navigation.js#targetPoint`` 跟的就是
    # ``plan.combined_path``（``tick()`` 里的 ``waypoints[waypointIndex]`` 只是**到达判定**）。
    # 本函数第一版误喂了手填航点，于是"跟随器"退化成"直线奔向航点"，在 warehouse 上必然穿障
    # （实测 clr −0.797 / 碰撞 30 步）——那是**测法错误**，不是产品行为。
    follow_controller = (
        FollowController(path if len(path) >= 2 else waypoints) if mode == "follow" else None
    )

    for step in range(1, max_steps + 1):
        target = waypoints[min(index, len(waypoints) - 1)]
        decision = ""
        if mode == "potential":
            cmd = compute_avoidance_command(
                (x, y), (float(target[0]), float(target[1])), obstacles
            )
            world_vx, world_vy = cmd["command"]
            speed = math.hypot(world_vx, world_vy)
            if speed > 1e-6:
                desired = math.atan2(world_vy, world_vx)
                error = normalize_angle(desired - yaw)
                wz = max(-params.max_wz, min(params.max_wz, turn_gain * error))
                v = speed * math.cos(error) if abs(error) < math.pi / 2 else 0.0
            else:
                v, wz = 0.0, 0.0
        elif mode == "geometric":
            # 追踪点推进 + 基座系误差 × 增益（产品实现 backend/geometric_tracker.py）
            track_index, target_point = select_tracking_target(
                [x, y], path, track_index, geo_params.lookahead_tolerance_m
            )
            result = command_from_target([x, y, yaw], target_point, geo_params)
            v, wz = result["cmd"][0], result["cmd"][2]
        elif mode == "follow":
            # 产品默认执行器（H12 状态机）：前视点 + 转向滞回 + 卡死恢复，逐拍喂时间
            follow_step = follow_controller.update([x, y, yaw], (step - 1) * dt)
            v, wz = follow_step.cmd[0], follow_step.cmd[2]
            decision = f"state={follow_step.state} wp={follow_step.waypoint_index}"
        else:
            plan = plan_local(
                [x, y, yaw], [prev_v, 0.0, prev_wz], path, obstacles, params=params
            )
            v, wz = plan.cmd[0], plan.cmd[2]
            decision = (
                f"{plan.reason} d_path={plan.metrics.get('path_distance_m')}"
                f" d_goal={plan.metrics.get('goal_distance_m')}"
                f" valid={plan.metrics.get('candidates_valid')}"
            )
        prev_v, prev_wz = v, wz

        x += v * math.cos(yaw) * dt
        y += v * math.sin(yaw) * dt
        yaw = normalize_angle(yaw + wz * dt)

        clearance = min_clearance(x, y, obstacles)
        min_clear = min(min_clear, clearance)
        if clearance < 0.0:
            collisions += 1
        if trace_every and step % trace_every == 0:
            entry: list[Any] = [
                step, round(x, 3), round(y, 3), round(yaw, 3), round(v, 3), round(wz, 3)
            ]
            if decision:
                entry.append(decision)
            trace.append(entry)

        while index < len(waypoints) - 1 and math.hypot(
            float(waypoints[index][0]) - x, float(waypoints[index][1]) - y
        ) <= tolerance:
            index += 1
        goal = waypoints[-1]
        if math.hypot(float(goal[0]) - x, float(goal[1]) - y) <= tolerance:
            reached = True
            break
        if collisions >= 30:  # 已经穿墙太久，不必再跑
            break

    goal = waypoints[-1]
    result = {
        "mode": mode,
        "reached": reached,
        "steps": step,
        "time_s": round(step * dt, 2),
        "min_clearance_m": round(min_clear, 4) if math.isfinite(min_clear) else None,
        "collision_steps": collisions,
        "final_distance_m": round(math.hypot(float(goal[0]) - x, float(goal[1]) - y), 4),
        "final_pose": [round(x, 3), round(y, 3), round(yaw, 3)],
    }
    if trace:
        result["trace"] = trace
    return result


def run_ab(
    map_id: str,
    waypoints: list[list[float]],
    *,
    dt: float = 0.05,
    max_steps: int = 2000,
    tolerance: float | None = None,
    trace_every: int = 0,
) -> dict[str, Any]:
    """跑两侧并给出结论（势场 vs DWA）。"""
    from backend.arrival_criteria import waypoint_spec
    from backend.motion_commands import follow_controller_spec

    if map_id not in MAPS:
        raise SystemExit(f"未知地图 {map_id}；可选：{', '.join(sorted(MAPS))}")
    obstacles = [list(o[:4]) for o in (MAPS[map_id].get("obstacles") or [])]
    if tolerance is None:
        tolerance = float(waypoint_spec()["tolerance_m"])
    params = DwaParams.from_registry()
    turn_gain = float(follow_controller_spec()["kp_yaw"])
    path = reference_path(map_id, waypoints, obstacles)

    common = dict(
        dt=dt,
        max_steps=max_steps,
        tolerance=tolerance,
        params=params,
        turn_gain=turn_gain,
        trace_every=trace_every,
    )
    potential = simulate("potential", waypoints, path, obstacles, **common)
    dwa = simulate("dwa", waypoints, path, obstacles, **common)
    geometric = simulate("geometric", waypoints, path, obstacles, **common)
    follow = simulate("follow", waypoints, path, obstacles, **common)
    return {
        "map_id": map_id,
        "waypoints": waypoints,
        "obstacle_count": len(obstacles),
        "reference_path_points": len(path),
        "dt": dt,
        "tolerance_m": tolerance,
        "potential_field": potential,
        "dwa": dwa,
        "geometric": geometric,
        "follow": follow,
        "verdict": _verdict(
            {
                "potential_field": potential,
                "dwa": dwa,
                "geometric": geometric,
                "follow": follow,
            }
        ),
    }


def _verdict(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def score(result: dict[str, Any]) -> tuple[int, int, float]:
        clear = result["min_clearance_m"]
        return (
            1 if result["reached"] else 0,
            0 if result["collision_steps"] == 0 else -1,
            float(clear) if clear is not None else float("inf"),
        )

    ranked = sorted(results, key=lambda name: score(results[name]), reverse=True)
    winner = ranked[0]
    if len(ranked) > 1 and score(results[ranked[0]]) == score(results[ranked[1]]):
        winner = "tie"
    return {
        "winner": winner,
        "ranking": ranked,
        "criterion": "(到达优先, 无碰撞优先, 最小净空大者优先)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="H11：势场 vs DWA 同路线 A/B")
    parser.add_argument("--map", default="warehouse", help="地图 id（默认 warehouse）")
    parser.add_argument("--waypoints", default=None, help='"x,y;x,y;..."（默认取地图航点）')
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument("--trace", type=int, default=0, metavar="EVERY",
                        help="每 N 步记录一个轨迹点（0 = 不记录）")
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    args = parser.parse_args()

    waypoints = _parse_waypoints(args.waypoints, args.map)
    report = run_ab(
        args.map, waypoints, dt=args.dt, max_steps=args.max_steps, trace_every=args.trace
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("=" * 68)
    print(f"H11 A/B：势场 vs DWA（map={report['map_id']}，障碍 {report['obstacle_count']} 个）")
    print("-" * 68)
    for key, label in (
        ("potential_field", "势场 (potential field)"),
        ("dwa", "DWA (采样择优)"),
        ("geometric", "几何跟踪 (d1_controller)"),
        ("follow", "跟随状态机 (H12 产品默认)"),
    ):
        result = report[key]
        print(
            f"  {label:<24} 到达={result['reached']!s:<5} "
            f"用时={result['time_s']:>6.2f}s 最小净空={result['min_clearance_m']} "
            f"碰撞步={result['collision_steps']}"
        )
    print("-" * 68)
    print(f"  胜者：{report['verdict']['winner']}（{report['verdict']['criterion']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
