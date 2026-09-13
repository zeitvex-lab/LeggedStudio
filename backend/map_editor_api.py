"""Interactive map editor API (Feature 4).

Bridges the A*/Dijkstra route planner (backend/route_planner.py) with the
scenario map library (backend/scenario_maps.py) so the Web workbench can draw
obstacles + waypoints in world coordinates, rasterise them to a grid, and ask
for an automatically-planned route.

The obstacle record format comes from scenario_maps.py:
    [cx, cy, half_width, half_height]   (world metres, axis-aligned rectangle)

Grid rasterisation uses a per-map resolution so the editor can render a
moderately sized grid (e.g. 48x48) regardless of the world bounds.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.route_planner import plan_route
from backend.scenario_maps import MAPS

router = APIRouter(prefix="/api/navigation", tags=["navigation"])

DEFAULT_RESOLUTION = 48  # cells along the longer world axis


def _bounds(map_id: str) -> list[float]:
    return list(MAPS[map_id]["bounds"]) if map_id in MAPS else [-5.0, 5.0, -5.0, 5.0]


def _resolution(map_id: str, requested: int | None) -> int:
    if requested is not None and requested > 0:
        return min(max(requested, 8), 160)
    return DEFAULT_RESOLUTION


def _grid_dims(bounds: list[float], res: int) -> tuple[int, int]:
    """Return (cols, rows) for a square-cell grid over the map bounds."""
    x0, x1, y0, y1 = bounds
    span = max(x1 - x0, y1 - y0)
    cols = max(1, int(round((x1 - x0) / span * res)))
    rows = max(1, int(round((y1 - y0) / span * res)))
    return cols, rows


def _world_to_cell(x: float, y: float, bounds: list[float], res: int) -> tuple[int, int]:
    x0, x1, y0, y1 = bounds
    cols, rows = _grid_dims(bounds, res)
    cx = min(cols - 1, max(0, int((x - x0) / (x1 - x0) * cols)))
    cy = min(rows - 1, max(0, int((y - y0) / (y1 - y0) * rows)))
    return cx, cy


def _cell_to_world(cx: int, cy: int, bounds: list[float], res: int) -> list[float]:
    x0, x1, y0, y1 = bounds
    cols, rows = _grid_dims(bounds, res)
    wx = x0 + (cx + 0.5) / cols * (x1 - x0)
    wy = y0 + (cy + 0.5) / rows * (y1 - y0)
    return [round(wx, 3), round(wy, 3)]


def _grid_from_obstacles(map_id: str, obstacles: list[list[float]], resolution: int) -> dict[str, Any]:
    bounds = _bounds(map_id)
    x0, x1, y0, y1 = bounds
    cols, rows = _grid_dims(bounds, resolution)
    grid = [[0] * cols for _ in range(rows)]

    def fill(cx: int, cy: int) -> None:
        if 0 <= cx < cols and 0 <= cy < rows:
            grid[cy][cx] = 1

    for obstacle in obstacles:
        if len(obstacle) < 4:
            continue
        cx, cy, half_w, half_h = obstacle[:4]
        left, right = cx - half_w, cx + half_w
        bottom, top = cy - half_h, cy + half_h
        # Rasterise the rectangle by iterating the covered cell span.
        min_cx = min(cols - 1, max(0, int((left - x0) / (x1 - x0) * cols)))
        max_cx = min(cols - 1, max(0, int((right - x0) / (x1 - x0) * cols)))
        min_cy = min(rows - 1, max(0, int((bottom - y0) / (y1 - y0) * rows)))
        max_cy = min(rows - 1, max(0, int((top - y0) / (y1 - y0) * rows)))
        for yy in range(min_cy, max_cy + 1):
            for xx in range(min_cx, max_cx + 1):
                fill(xx, yy)
    return {"cols": cols, "rows": rows, "grid": grid, "bounds": bounds, "resolution": resolution}


class PlanRequest(BaseModel):
    map_id: str
    obstacles: list[list[float]] = Field(default_factory=list)
    waypoints: list[list[float]] = Field(default_factory=list, min_length=2)
    algorithm: str = Field(default="astar", pattern="^(astar|dijkstra)$")
    diagonal: bool = True
    resolution: int | None = Field(default=None, ge=8, le=160)

    @field_validator("waypoints")
    @classmethod
    def validate_waypoints(cls, value: list[list[float]]) -> list[list[float]]:
        if any(len(point) != 2 for point in value):
            raise ValueError("each waypoint must be [x, y]")
        return value

    @field_validator("obstacles")
    @classmethod
    def validate_obstacles(cls, value: list[list[float]]) -> list[list[float]]:
        for obstacle in value:
            if len(obstacle) != 4:
                raise ValueError("each obstacle must be [cx, cy, half_w, half_h]")
        return value


class MapSave(BaseModel):
    map_id: str
    obstacles: list[list[float]] = Field(default_factory=list)
    waypoints: list[list[float]] = Field(default_factory=list)
    label: str | None = None


@router.get("/maps")
async def list_maps():
    """List the map library catalog (with default obstacle/waypoint data)."""
    entries = []
    for map_id, meta in MAPS.items():
        entries.append({
            "id": map_id,
            "label": meta.get("label", map_id),
            "kind": meta.get("kind"),
            "mode": meta.get("mode"),
            "description": meta.get("description"),
            "bounds": meta.get("bounds"),
            "obstacles": meta.get("obstacles", []),
            "default_waypoints": meta.get("default_waypoints", []),
        })
    return {"success": True, "maps": entries}


@router.post("/maps/plan")
async def plan_map_route(request: PlanRequest):
    """Rasterise obstacles and plan a route through the waypoint sequence.

    Consecutive waypoint pairs are planned independently; obstacles are shared.
    Returns ordered polyline segments plus a combined path.
    """
    if request.map_id not in MAPS:
        raise HTTPException(status_code=404, detail=f"Unknown map: {request.map_id}")
    if len(request.waypoints) < 2:
        raise HTTPException(status_code=400, detail="At least two waypoints required")

    resolution = _resolution(request.map_id, request.resolution)
    raster = _grid_from_obstacles(request.map_id, request.obstacles, resolution)
    grid = raster["grid"]
    bounds = raster["bounds"]
    cols, rows = raster["cols"], raster["rows"]

    segments = []
    combined = [request.waypoints[0]]
    for index in range(len(request.waypoints) - 1):
        start_world = request.waypoints[index]
        goal_world = request.waypoints[index + 1]
        start_cell = _world_to_cell(start_world[0], start_world[1], bounds, resolution)
        goal_cell = _world_to_cell(goal_world[0], goal_world[1], bounds, resolution)
        if grid[start_cell[1]][start_cell[0]]:
            raise HTTPException(status_code=400, detail=f"Waypoint {index} falls inside an obstacle")
        if grid[goal_cell[1]][goal_cell[0]]:
            raise HTTPException(status_code=400, detail=f"Waypoint {index + 1} falls inside an obstacle")
        try:
            result = plan_route(grid, (start_cell[1], start_cell[0]), (goal_cell[1], goal_cell[0]), algorithm=request.algorithm, diagonal=request.diagonal)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        segment_path = [start_world] + [
            _cell_to_world(cx, cy, bounds, resolution) for (cy, cx) in result.path[1:-1]
        ] + [goal_world]
        segments.append({
            "from_index": index,
            "to_index": index + 1,
            "algorithm": result.algorithm,
            "cost_m": result.cost,
            "expanded": result.expanded,
            "path": segment_path,
        })
        if index > 0:
            combined.extend(segment_path[1:])
        else:
            combined = segment_path
    # H13 规划后处理：简化 → 转角混合 → **净空四级**（判据/参数出处见 backend/route_postprocess.py）。
    # 评审里的 path 是处理后的路径，segments 逐段带 status，summary.blocked 表示必须拒绝下发。
    from backend.route_postprocess import postprocess_route

    route_review = postprocess_route(combined, request.obstacles)

    return {
        "success": True,
        "map_id": request.map_id,
        "algorithm": request.algorithm,
        "diagonal": request.diagonal,
        "resolution": resolution,
        "raster": raster,
        "segments": segments,
        "combined_path": combined,
        "route_review": route_review,
        "total_cost_m": round(sum(seg["cost_m"] for seg in segments), 3),
    }


def _user_maps_dir() -> Path:
    from backend.settings_api import _data_dir
    return _data_dir() / "maps"


@router.get("/maps/{map_id}")
async def get_map(map_id: str):
    """Return catalog metadata plus any user-saved edits for the map."""
    if map_id not in MAPS:
        raise HTTPException(status_code=404, detail=f"Unknown map: {map_id}")
    meta = MAPS[map_id]
    saved = {}
    path = _user_maps_dir() / f"{map_id}.json"
    if path.exists():
        try:
            import json
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            saved = {}
    return {
        "success": True,
        "map": {
            "id": map_id,
            "label": meta.get("label", map_id),
            "bounds": meta.get("bounds"),
            "obstacles": saved.get("obstacles", meta.get("obstacles", [])),
            "waypoints": saved.get("waypoints", meta.get("default_waypoints", [])),
        },
    }


@router.put("/maps/{map_id}")
async def save_map(map_id: str, save: MapSave):
    """Persist custom obstacle/waypoint edits for a map in the user data dir."""
    if map_id not in MAPS:
        raise HTTPException(status_code=404, detail=f"Unknown map: {map_id}")
    import json
    path = _user_maps_dir() / f"{map_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "map_id": map_id,
        "obstacles": save.obstacles,
        "waypoints": save.waypoints,
        "label": save.label,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"success": True, "map_id": map_id}
