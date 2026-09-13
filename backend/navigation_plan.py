"""导航 Scenario 的「计划 + 判据」装配（H3 的**唯一实现**）。

**为什么要有这个模块**：`command_source=planner` 的导航要被两处执行——
浏览器 sim2sim（WASM，离线）与服务端会话（`/api/simulation/sessions`）。
如果两边各写一份规划与到达判据，就会重演 H10 修过的老问题（同一件事两套口径）。
所以装配只做一次，两个入口共用：

* ``POST /api/navigation/plan``        浏览器侧取计划；
* ``POST /api/simulation/sessions``    服务端会话在 ``command_source=planner`` 时附带同一份计划。

规则：

1. **规划复用** ``map_editor_api.plan_map_route``（栅格化 + 分段 A*/Dijkstra），不另起实现；
2. **到达容差**默认取 ``registry/arrival_criteria.json``（H10 单一真值）；只有场景**显式**写了
   某个航点的 ``tolerance`` 才用它，并在载荷里标注 ``tolerance_source``；
3. **不静默兜底**：无路可走时直接抛 400，而不是回退成"直线穿过障碍"。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.arrival_criteria import waypoint_spec
from backend.map_editor_api import PlanRequest, plan_map_route
from backend.scenario_maps import MAPS

#: 判据来源标识（写进载荷，便于前端显示与追溯）
ARRIVAL_SOURCE = "registry/arrival_criteria.json"


def _waypoint_fields(waypoint: Any) -> tuple[float, float, bool, float | None]:
    """兼容三种形态，返回 ``(x, y, 是否显式给了容差, 容差)``：

    * 裸 ``[x, y]`` / ``[x, y, tolerance]``（HTTP 端点收的形状）；
    * ``{"x":…, "y":…, "tolerance":…}``；
    * ``contracts.scenario_contract.Waypoint`` 模型（用 ``model_fields_set`` 区分
      "显式写了 tolerance" 与"吃了模型默认值"——默认值不算真值来源）。
    """
    if isinstance(waypoint, dict):
        return (
            float(waypoint["x"]),
            float(waypoint["y"]),
            "tolerance" in waypoint,
            waypoint.get("tolerance"),
        )
    if isinstance(waypoint, (list, tuple)):
        values = list(waypoint)
        explicit = len(values) > 2 and values[2] is not None
        return (
            float(values[0]),
            float(values[1]),
            explicit,
            float(values[2]) if explicit else None,
        )
    declared = getattr(waypoint, "model_fields_set", set())
    return float(waypoint.x), float(waypoint.y), "tolerance" in declared, getattr(waypoint, "tolerance", None)


async def build_navigation_payload(
    map_id: str,
    waypoints: list[Any],
    *,
    algorithm: str = "astar",
    diagonal: bool = True,
    obstacles: list[list[float]] | None = None,
) -> dict[str, Any]:
    """装配导航载荷：``{waypoints, plan, arrival, ...}``。

    抛 ``HTTPException``：未知地图 404 / 航点不足 400 / 无可达路径 400。
    """
    if map_id not in MAPS:
        raise HTTPException(status_code=404, detail=f"Unknown simulation map: {map_id}")
    if len(waypoints) < 2:
        raise HTTPException(status_code=400, detail="导航至少需要两个航点（起点与目标）")

    spec = waypoint_spec()
    registry_tolerance = float(spec["tolerance_m"])
    stable_ticks = int(spec["stable_ticks"])

    points: list[list[float]] = []
    waypoint_payload: list[dict[str, Any]] = []
    for waypoint in waypoints:
        x, y, explicit, tolerance = _waypoint_fields(waypoint)
        effective = float(tolerance) if (explicit and tolerance is not None) else registry_tolerance
        points.append([x, y])
        waypoint_payload.append(
            {
                "x": x,
                "y": y,
                "tolerance_m": round(effective, 4),
                "tolerance_source": "scenario" if (explicit and tolerance is not None) else ARRIVAL_SOURCE,
            }
        )

    where = list(obstacles if obstacles is not None else (MAPS[map_id].get("obstacles") or []))
    plan = await plan_map_route(
        PlanRequest(map_id=map_id, obstacles=where, waypoints=points, algorithm=algorithm, diagonal=diagonal)
    )
    path = plan.get("combined_path") or []
    if len(path) < 2:  # pragma: no cover - plan_map_route 已保证，双保险
        raise HTTPException(status_code=400, detail="规划结果为空：无可达路径")

    return {
        "command_source": "planner",
        "map_id": map_id,
        "bounds": MAPS[map_id].get("bounds"),
        "obstacles": where,
        "waypoints": waypoint_payload,
        "plan": {
            "combined_path": path,
            "segments": plan.get("segments") or [],
            "total_cost_m": plan.get("total_cost_m"),
            "resolution": plan.get("resolution"),
            "algorithm": "dijkstra" if algorithm.lower() == "dijkstra" else "astar",
            "diagonal": bool(plan.get("diagonal", diagonal)),
        },
        "arrival": {"tolerance_m": registry_tolerance, "stable_ticks": stable_ticks, "source": ARRIVAL_SOURCE},
    }
