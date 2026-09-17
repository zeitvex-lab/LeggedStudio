#!/usr/bin/env python3
r"""H19 批量路线回归：N 条路线 × 控制器 → 通过率 / 最小净空 / 超时报告（离线、无 GPU）。

**为什么要有它**：H11 的 A/B、H13 的净空评审都只在**一条**路线上看过结论（warehouse 默认
航点）。单条路线的结论可能只是"这条恰好"——回归要的是**分布**，而且要在每次提交时自动跑。

**口径（全部复用既有唯一实现，不另抄一份）**：
* 路线集 = 地图默认航点（`full`）+ 逐段（`leg_i_j`）+ **固定 seed 随机起终点**
  （``00_resources/tdt-nav-kit`` 的随机起终点范式；seed 固定 ⇒ 可复现，不是"每次抽新题"）；
* 参考路径 = ``map_editor_api.plan_map_route``（A\*）——与全局规划**同一实现**；
* 净空评审 = ``backend.route_postprocess.review_route``（H13；判据与参数唯一真值在
  ``registry/motion_commands.json#route_postprocess``）；
* 控制器 = ``tools/dwa_ab_check.simulate``（**同一个**积分器与到达判据），三侧
  `potential` / `geometric` / `dwa`；
* 到达容差 = ``registry/arrival_criteria.json``。

**门禁语义（同 ``tools/sim2sim_headless.py``）**：只守"不许退化"——通过率下降、最小净空
下降、新增超时/碰撞、或 H13 后处理不再能消掉净空违规 ⇒ exit 2。绝对值的刷新用
``--write-baseline``，退化与刷新**必须**是两次不同的动作，避免"顺手就把基线改绿"。

用法：
    python tools/route_regression.py                        # 跑并对比基线
    python tools/route_regression.py --json                 # 机器可读
    python tools/route_regression.py --write-baseline       # 刷新基线（需显式）
    python tools/route_regression.py --routes 6 --with-dwa # 本地更重的回归
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scenario_maps import MAPS  # noqa: E402

#: 复用 H11 的仿真器与参考路径求法——回归与 A/B 必须是**同一套**运动学与判据，
#: 否则"回归过了"不代表"A/B 的结论还在"。
from tools.dwa_ab_check import reference_path, simulate  # noqa: E402

BASELINE_PATH = ROOT / "tools/baselines/route_regression_baseline.json"
#: ``mpc`` = H14 可选对照（LightNav-0 vln_mpc 简化版，backend/mpc_tracker.py）——
#: 定位是「可选对照项」，不进默认控制器集合（默认 = follow/geometric/potential）。
ALL_CONTROLLERS = ("follow", "geometric", "potential", "dwa", "mpc")
LEVELS = ("OK", "TIGHT", "VIOLATION", "INTERSECT")


# ---------------------------------------------------------------------------
# 路线集
# ---------------------------------------------------------------------------
def build_routes(
    map_id: str,
    *,
    random_count: int = 3,
    seed: int = 20260913,
    waypoints: list[list[float]] | None = None,
) -> list[dict[str, Any]]:
    """地图默认航点 + 逐段 + 固定 seed 随机起终点。"""
    from backend.route_postprocess import PostprocessParams, clearance_gradient

    entry = MAPS[map_id]
    bounds = [float(v) for v in entry["bounds"]]
    obstacles = [list(o[:4]) for o in (entry.get("obstacles") or [])]
    defaults = [[float(p[0]), float(p[1])] for p in (waypoints or entry.get("default_waypoints") or [])]

    routes: list[dict[str, Any]] = []
    if len(defaults) >= 2:
        routes.append({"name": "full", "kind": "map_default", "waypoints": defaults})
        for index in range(len(defaults) - 1):
            routes.append(
                {
                    "name": f"leg_{index}_{index + 1}",
                    "kind": "map_leg",
                    "waypoints": [defaults[index], defaults[index + 1]],
                }
            )

    # 随机起终点：必须**两端都在障碍外且有富余**，否则等于在测"起点就在墙里"。
    p = PostprocessParams.from_registry()
    min_clearance = p.required_clearance_m + 0.2
    rng = random.Random(seed)
    guard = 0
    while len([r for r in routes if r["kind"] == "random"]) < random_count and guard < random_count * 400:
        guard += 1
        x0 = rng.uniform(bounds[0] + 0.6, bounds[1] - 0.6)
        y0 = rng.uniform(bounds[2] + 0.6, bounds[3] - 0.6)
        x1 = rng.uniform(bounds[0] + 0.6, bounds[1] - 0.6)
        y1 = rng.uniform(bounds[2] + 0.6, bounds[3] - 0.6)
        if math.hypot(x1 - x0, y1 - y0) < 2.0:
            continue
        if clearance_gradient(x0, y0, obstacles)[0] < min_clearance:
            continue
        if clearance_gradient(x1, y1, obstacles)[0] < min_clearance:
            continue
        routes.append(
            {
                "name": f"random_{len([r for r in routes if r['kind'] == 'random']) + 1}",
                "kind": "random",
                "waypoints": [[round(x0, 3), round(y0, 3)], [round(x1, 3), round(y1, 3)]],
            }
        )
    return routes


# ---------------------------------------------------------------------------
# 单条路线
# ---------------------------------------------------------------------------
def clearance_review(path: list[list[float]], obstacles: list[list[float]]) -> dict[str, Any]:
    """H13 净空评审：原始 A* 路径 vs 后处理之后（后者应把 VIOLATION 消掉）。"""
    from backend.route_postprocess import review_route

    raw = review_route(path, obstacles)
    post = review_route(path, obstacles, simplify=True, blend=True, relax=True)
    return {
        "raw": {level: raw["summary"][level] for level in LEVELS},
        "post": {level: post["summary"][level] for level in LEVELS},
        "raw_blocked": bool(raw["summary"]["blocked"]),
        "post_blocked": bool(post["summary"]["blocked"]),
        "raw_worst": raw["summary"]["worst_status"],
        "post_worst": post["summary"]["worst_status"],
        "raw_points": len(path),
        "post_points": len(post["path"]),
    }


def run_route(
    route: dict[str, Any],
    map_id: str,
    obstacles: list[list[float]],
    *,
    controllers: tuple[str, ...],
    dt: float,
    max_steps: int,
    tolerance: float,
) -> dict[str, Any]:
    from backend.dwa_planner import DwaParams
    from backend.motion_commands import follow_controller_spec

    waypoints = route["waypoints"]
    path = reference_path(map_id, waypoints, obstacles)
    review = clearance_review(path, obstacles)
    params = DwaParams.from_registry()
    turn_gain = float(follow_controller_spec()["kp_yaw"])

    runs: dict[str, Any] = {}
    for controller in controllers:
        started = time.perf_counter()
        result = simulate(
            controller,
            waypoints,
            path,
            obstacles,
            dt=dt,
            max_steps=max_steps,
            tolerance=tolerance,
            params=params,
            turn_gain=turn_gain,
        )
        runs[controller] = {
            "reached": result["reached"],
            "time_s": result["time_s"],
            "min_clearance_m": result["min_clearance_m"],
            "collision_steps": result["collision_steps"],
            "final_distance_m": result["final_distance_m"],
            "timed_out": (not result["reached"]) and result["steps"] >= max_steps,
            "wall_time_s": round(time.perf_counter() - started, 3),
        }
    return {
        "name": route["name"],
        "kind": route["kind"],
        "waypoints": waypoints,
        "reference_points": len(path),
        "clearance": review,
        "controllers": runs,
    }


# ---------------------------------------------------------------------------
# 汇总与门禁
# ---------------------------------------------------------------------------
def summarize(routes: list[dict[str, Any]], controllers: tuple[str, ...]) -> dict[str, Any]:
    from backend.route_postprocess import PostprocessParams

    # 「到达」只看机器人中心，**不能**代表本体没压到障碍：中心净空 < 足迹半径即本体已侵入。
    # 实测（warehouse 7 条路线）geometric 通过率 1.00 却最小净空 0.1697 m < 足迹 0.21 m——
    # 只报 reached 会把这种"贴着墙走完"当成完全成功。这条指标就是为它加的。
    footprint = PostprocessParams.from_registry().footprint_radius_m
    per_controller: dict[str, Any] = {}
    for controller in controllers:
        runs = [route["controllers"][controller] for route in routes]
        clearances = [r["min_clearance_m"] for r in runs if r["min_clearance_m"] is not None]
        reached = [r for r in runs if r["reached"]]
        per_controller[controller] = {
            "runs": len(runs),
            "reached": len(reached),
            "pass_rate": round(len(reached) / len(runs), 4) if runs else 0.0,
            "min_clearance_m": round(min(clearances), 4) if clearances else None,
            "routes_below_footprint": sum(
                1 for r in runs if r["min_clearance_m"] is not None and r["min_clearance_m"] < footprint
            ),
            "timeouts": sum(1 for r in runs if r["timed_out"]),
            "collision_steps": sum(r["collision_steps"] for r in runs),
            "mean_time_s": round(sum(r["time_s"] for r in reached) / len(reached), 3) if reached else None,
        }
    raw_violations = sum(route["clearance"]["raw"]["VIOLATION"] for route in routes)
    post_violations = sum(route["clearance"]["post"]["VIOLATION"] for route in routes)
    raw_intersects = sum(route["clearance"]["raw"]["INTERSECT"] for route in routes)
    post_intersects = sum(route["clearance"]["post"]["INTERSECT"] for route in routes)
    return {
        "route_count": len(routes),
        "per_controller": per_controller,
        "footprint_radius_m": footprint,
        "clearance": {
            "raw_violation_segments": raw_violations,
            "post_violation_segments": post_violations,
            "raw_intersect_segments": raw_intersects,
            "post_intersect_segments": post_intersects,
            # 后处理**应该**把 VIOLATION 消掉；消不掉说明 H13 在更宽的场景集上失效
            "post_blocked_routes": sum(1 for route in routes if route["clearance"]["post_blocked"]),
            "raw_blocked_routes": sum(1 for route in routes if route["clearance"]["raw_blocked"]),
        },
    }


def compare_to_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """返回退化项（空列表 = 通过）。只守退化，不守绝对值。"""
    problems: list[str] = []
    base_by_controller = (baseline or {}).get("per_controller") or {}
    for name, stats in report["per_controller"].items():
        base = base_by_controller.get(name)
        if not base:
            problems.append(f"{name}: 基线里没有这个控制器（新增控制器不算退化，但需刷新基线）")
            continue
        if stats["pass_rate"] < base["pass_rate"] - 1e-9:
            problems.append(f"{name}: 通过率 {base['pass_rate']:.4f} → {stats['pass_rate']:.4f}")
        if stats["timeouts"] > base["timeouts"]:
            problems.append(f"{name}: 超时 {base['timeouts']} → {stats['timeouts']}")
        if stats["collision_steps"] > base["collision_steps"]:
            problems.append(f"{name}: 碰撞步 {base['collision_steps']} → {stats['collision_steps']}")
        if stats.get("routes_below_footprint", 0) > base.get("routes_below_footprint", 0):
            problems.append(
                f"{name}: 本体侵入障碍的路线 {base.get('routes_below_footprint', 0)} → "
                f"{stats['routes_below_footprint']}"
                f"（中心净空 < 足迹半径 {report.get('footprint_radius_m')} m）"
            )
        base_clearance, clearance = base.get("min_clearance_m"), stats.get("min_clearance_m")
        if base_clearance is not None and clearance is not None and clearance < base_clearance - 1e-6:
            problems.append(f"{name}: 最小净空 {base_clearance} → {clearance}")

    base_clear = (baseline or {}).get("clearance") or {}
    clear = report["clearance"]
    if clear["post_blocked_routes"] > base_clear.get("post_blocked_routes", 0):
        problems.append(
            f"H13 后处理: 仍有违规的路线 {base_clear.get('post_blocked_routes', 0)} → "
            f"{clear['post_blocked_routes']}（后处理应把 VIOLATION 消掉）"
        )
    if clear["post_violation_segments"] > base_clear.get("post_violation_segments", 0):
        problems.append(
            f"H13 后处理: VIOLATION 段 {base_clear.get('post_violation_segments', 0)} → "
            f"{clear['post_violation_segments']}"
        )
    return problems


def run_suite(
    map_id: str,
    *,
    routes: int,
    seed: int,
    controllers: tuple[str, ...],
    dt: float,
    max_steps: int,
    waypoints: list[list[float]] | None = None,
) -> dict[str, Any]:
    from backend.arrival_criteria import waypoint_spec

    if map_id not in MAPS:
        raise SystemExit(f"未知地图 {map_id}；可选：{', '.join(sorted(MAPS))}")
    obstacles = [list(o[:4]) for o in (MAPS[map_id].get("obstacles") or [])]
    tolerance = float(waypoint_spec()["tolerance_m"])
    route_list = build_routes(map_id, random_count=routes, seed=seed, waypoints=waypoints)
    started = time.perf_counter()
    results = [
        run_route(
            route,
            map_id,
            obstacles,
            controllers=controllers,
            dt=dt,
            max_steps=max_steps,
            tolerance=tolerance,
        )
        for route in route_list
    ]
    return {
        "map_id": map_id,
        "dt": dt,
        "max_steps": max_steps,
        "tolerance_m": tolerance,
        "controllers": list(controllers),
        "seed": seed,
        "wall_time_s": round(time.perf_counter() - started, 2),
        "routes": results,
        **summarize(results, controllers),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="H19 批量路线回归（离线、无 GPU）")
    parser.add_argument("--map", default="warehouse")
    parser.add_argument("--routes", type=int, default=3, help="随机起终点路线条数")
    parser.add_argument("--seed", type=int, default=20260913)
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--max-steps", type=int, default=1200)
    parser.add_argument(
        "--controllers",
        default="follow,geometric,potential",
        help=f"逗号分隔，可选 {','.join(ALL_CONTROLLERS)}"
        "（默认含 follow = 产品实际默认执行器，不含 dwa/mpc：较慢的可选对照，用 --with-dwa 或显式列入）",
    )
    parser.add_argument("--with-dwa", action="store_true", help="临时把 dwa 加进控制器集合")
    parser.add_argument("--waypoints", default=None, help='"x,y;x,y"（覆盖地图默认航点）')
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--write-baseline", action="store_true", help="刷新基线（显式动作）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    controllers = tuple(c.strip() for c in args.controllers.split(",") if c.strip())
    unknown = [c for c in controllers if c not in ALL_CONTROLLERS]
    if unknown:
        raise SystemExit(f"未知控制器 {unknown}；可选 {ALL_CONTROLLERS}")
    if args.with_dwa and "dwa" not in controllers:
        controllers = (*controllers, "dwa")

    waypoints = None
    if args.waypoints:
        waypoints = [[float(a), float(b)] for a, b in (p.split(",") for p in args.waypoints.split(";"))]

    report = run_suite(
        args.map,
        routes=args.routes,
        seed=args.seed,
        controllers=controllers,
        dt=args.dt,
        max_steps=args.max_steps,
        waypoints=waypoints,
    )

    if args.write_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        print(f"基线已刷新：{args.baseline}")
        print(json.dumps(report["per_controller"], ensure_ascii=False, indent=2))
        return 0

    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline.exists() else {}
    problems = compare_to_baseline(report, baseline)
    report["regression"] = {"baseline": str(args.baseline), "problems": problems, "passed": not problems}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print(f"H19 路线回归：map={report['map_id']} 路线 {report['route_count']} 条 "
              f"（{report['wall_time_s']}s，dt={report['dt']}，max_steps={report['max_steps']}）")
        print("-" * 72)
        for route in report["routes"]:
            flags = []
            for name, run in route["controllers"].items():
                mark = "√" if run["reached"] else "×"
                flags.append(f"{name}={mark}({run['time_s']:.1f}s)")
            clearance = route["clearance"]
            print(
                f"  {route['name']:<12} {' '.join(flags):<46} "
                f"净空 VIOLATION {clearance['raw']['VIOLATION']}→{clearance['post']['VIOLATION']}"
            )
        print("-" * 72)
        for name, stats in report["per_controller"].items():
            print(
                f"  {name:<10} 通过率 {stats['pass_rate']:.2f} ({stats['reached']}/{stats['runs']}) "
                f"最小净空 {stats['min_clearance_m']} 超时 {stats['timeouts']} "
                f"碰撞步 {stats['collision_steps']} "
                f"本体侵入 {stats['routes_below_footprint']}/{stats['runs']}"
                f"（<足迹 {report['footprint_radius_m']}）"
            )
        clear = report["clearance"]
        print(
            f"  H13 净空   VIOLATION 段 {clear['raw_violation_segments']} → "
            f"{clear['post_violation_segments']}；违规路线 {clear['raw_blocked_routes']} → "
            f"{clear['post_blocked_routes']}"
        )
        print("-" * 72)
        if not baseline:
            print(f"  [SKIP] 无基线（{args.baseline}）：只报告不判红，刷新用 --write-baseline")
        elif problems:
            print("  退化：")
            for problem in problems:
                print(f"    - {problem}")
        else:
            print("  与基线一致：无退化")
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
