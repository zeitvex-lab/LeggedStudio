"""Route replay API for the native MJLab policy loop."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.arrival_criteria import waypoint_spec
from backend.scenario_maps import MAPS


router = APIRouter(prefix="/api/navigation", tags=["navigation"])

#: H10：航点到达容差的单一真值（registry/arrival_criteria.json）。
#: 此前这里自持 0.35、相机投影侧自持 0.3，同一件事两套口径；现在统一取注册表。
#: 注册表缺失时**直接报错**（不做静默兜底）——静默回退正是口径漂移的成因。
WAYPOINT_TOLERANCE_M = float(waypoint_spec()["tolerance_m"])


class NavigationRequest(BaseModel):
    task_id: str
    map_id: str = "warehouse"
    control_mode: str = Field(default="auto", pattern="^(auto|manual)$")
    waypoints: list[list[float]] = Field(
        default_factory=lambda: [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
        min_length=2,
    )
    # 地图感知自动规划（Feature 3 在线闭环增量）：提供 obstacles 时，
    # 由后端用 A*/Dijkstra 规划出绕障路径作为实际跟踪路线，替代仅手填航点。
    obstacles: list[list[float]] = Field(
        default_factory=list,
        description="地图障碍，格式 [cx, cy, half_w, half_h]（world 米，轴对齐矩形）",
    )
    algorithm: str = Field(default="astar", pattern="^(astar|dijkstra)$")
    use_planner: bool = Field(default=True, description="是否用 A*/Dijkstra 对 obstacles 自动规划绕障路径")
    diagonal: bool = True
    use_avoidance: bool = Field(default=True, description="是否启用反应式避障闭环（叠加势场斥力）")
    episodes: int = Field(default=1, ge=1, le=20)
    max_steps: int | None = Field(default=None, ge=1, le=10000)
    # H10：默认值来自 registry/arrival_criteria.json（单一真值），不再硬编码 0.35。
    waypoint_tolerance: float = Field(default=WAYPOINT_TOLERANCE_M, gt=0.0, le=5.0)
    manual_commands: list[dict[str, float]] = Field(default_factory=list)

    @field_validator("obstacles")
    @classmethod
    def validate_obstacles(cls, value: list[list[float]]) -> list[list[float]]:
        for obstacle in value:
            if len(obstacle) != 4:
                raise ValueError("each obstacle must be [cx, cy, half_w, half_h]")
            if any(not np.isfinite(c) for c in obstacle):
                raise ValueError("obstacles must contain finite coordinates")
        return value

    @field_validator("waypoints")
    @classmethod
    def validate_waypoints(cls, value: list[list[float]]) -> list[list[float]]:
        if any(len(point) != 2 for point in value):
            raise ValueError("each waypoint must be [x, y]")
        if any(not all(np.isfinite(coordinate) for coordinate in point) for point in value):
            raise ValueError("waypoints must contain finite coordinates")
        return value


def _task(task_id: str):
    from backend.training_manager import get_training_manager

    task = get_training_manager().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@router.post("/run")
async def run_navigation(request: NavigationRequest):
    """Replay a trained policy through a waypoint route in native MJLab."""
    task = _task(request.task_id)
    if task.config.get("backend", "native_mjlab") != "native_mjlab":
        raise HTTPException(status_code=400, detail="Training task is not a native MJLab task")
    if request.map_id not in MAPS:
        raise HTTPException(status_code=404, detail=f"Unknown simulation map: {request.map_id}")
    return await _run_native_navigation(task, request)


async def _plan_obstacle_route(request: NavigationRequest) -> list[list[float]]:
    """通过地图障碍数据用 A*/Dijkstra 规划绕障路径（Feature 3 在线闭环）。

    复用 backend.map_editor_api 的栅格化 / 分步规划逻辑，返回世界坐标折线路径；
    若地图不存在或障碍使起终点落在障碍内则抛 HTTPException。
    """
    from backend.map_editor_api import plan_map_route, PlanRequest

    if len(request.waypoints) < 2:
        raise HTTPException(status_code=400, detail="At least two waypoints required for planning")
    plan_req = PlanRequest(
        map_id=request.map_id,
        obstacles=request.obstacles,
        waypoints=request.waypoints,
        algorithm=request.algorithm,
        diagonal=request.diagonal,
    )
    result = await plan_map_route(plan_req)
    return result.get("combined_path") or list(request.waypoints)


async def _run_native_navigation(task, request: NavigationRequest):
    """Run waypoint following with a native MJLab/RSL-RL checkpoint."""
    from adapters.mjlab.launcher import TrainingLauncher
    from adapters.mjlab.native_adapter import DEFAULT_SOURCE

    artifact_path = task.task_dir / "artifact.json"
    checkpoints = sorted(task.task_dir.glob("model_*.pt"))
    if not artifact_path.exists() or not checkpoints:
        raise HTTPException(status_code=400, detail="Native artifact or checkpoint is not ready")
    # Feature 3 在线闭环：提供 obstacles 且开启 use_planner 时，用 A*/Dijkstra 自动规划
    # 绕障路径作为实际跟踪路线，替代仅手填航点的回放。规划失败则回退到手填 waypoints。
    route = list(request.waypoints)
    if request.use_planner and request.obstacles:
        try:
            planned = await _plan_obstacle_route(request)
            if planned:
                route = planned
        except HTTPException:
            raise
        except Exception:
            # 规划失败不阻断导航，回退手填航点，交由 worker 的容错处理。
            route = list(request.waypoints)
    config = dict(task.config)
    config.update({"mode": "navigation", "episodes": request.episodes, "max_steps": request.max_steps or 500, "waypoints": route, "waypoint_tolerance": request.waypoint_tolerance, "checkpoint": str(checkpoints[-1].resolve()), "generic_task": True, "obstacles": [list(o[:4]) for o in (request.obstacles or [])], "use_avoidance": getattr(request, "use_avoidance", True)})
    config_path = task.task_dir / "native_navigation_config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    launcher = TrainingLauncher(workspace_dir=str(task.task_dir.parent))
    try:
        python_exe = launcher._select_python(config)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    worker = Path(__file__).resolve().parents[1] / "adapters" / "mjlab" / "native_worker.py"
    result = subprocess.run([str(python_exe), str(worker), "--source", str(DEFAULT_SOURCE), "--config", str(config_path), "--output", str(task.task_dir)], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=300)
    navigation_file = task.task_dir / "navigation.json"
    if result.returncode != 0 or not navigation_file.exists():
        detail = result.stderr.strip()[-2000:] or result.stdout.strip()[-2000:] or f"native navigation exited with code {result.returncode}"
        raise HTTPException(status_code=500, detail=detail)
    nav_result = json.loads(navigation_file.read_text(encoding="utf-8"))
    _record_navigation_evaluation(task, nav_result, request)
    return {"success": True, "result": nav_result}


def _record_navigation_evaluation(task, nav_result: dict, request: NavigationRequest) -> None:
    """将结构化的导航评估（路径完成率/跟踪误差/碰撞/稳定性）回写 PolicyArtifact。

    让策略档案真正可追溯：基础回放验证策略正确性，此处补充感知-决策闭环落档。
    若任务尚无 artifact 或字段缺失，则静默跳过，不阻断导航主流程。
    """
    from contracts.policy_artifact import NavigationEvaluation, PolicyArtifact

    artifact_path = task.task_dir / "artifact.json"
    if not artifact_path.exists():
        return
    try:
        artifact = PolicyArtifact.from_json_file(str(artifact_path))
        artifact.navigation_evaluation = NavigationEvaluation(
            map_id=request.map_id,
            waypoints=request.waypoints,
            episodes=request.episodes,
            route_completion=float(nav_result.get("route_completion", 0.0)),
            mean_tracking_error=float(nav_result.get("mean_tracking_error", 0.0)),
            collision_count=int(nav_result.get("collision_count", 0)),
            stability_score=float(nav_result.get("stability_score", 0.0)),
            evaluated_env=str(nav_result.get("evaluated_env", "native_mjlab_navigation")),
            use_avoidance=bool(nav_result.get("use_avoidance", False)),
            avoidance_engagement=nav_result.get("avoidance_engagement"),
            min_obstacle_distance_m=nav_result.get("min_obstacle_distance_m"),
        )
        artifact.to_json_file(str(artifact_path))
    except Exception:  # pragma: no cover - best-effort writeback
        return


class NavigationPlanRequest(BaseModel):
    """H3：planner 命令来源的计划请求（浏览器 sim2sim 用）。"""

    map_id: str = "warehouse"
    waypoints: list[list[float]] = Field(default_factory=list)
    obstacles: list[list[float]] | None = Field(
        default=None,
        description="省略时取地图自带障碍（MAPS[map_id].obstacles）",
    )
    algorithm: str = Field(default="astar", pattern="^(astar|dijkstra)$")
    diagonal: bool = True

    @field_validator("waypoints")
    @classmethod
    def validate_plan_waypoints(cls, value: list[list[float]]) -> list[list[float]]:
        if any(len(point) != 2 for point in value):
            raise ValueError("each waypoint must be [x, y]")
        if any(not all(np.isfinite(coordinate) for coordinate in point) for point in value):
            raise ValueError("waypoints must contain finite coordinates")
        return value


@router.post("/plan")
async def plan_navigation(request: NavigationPlanRequest):
    """装配导航计划（规划 + 到达判据）。

    **单一实现**：与 ``POST /api/simulation/sessions``（服务端会话）共用
    ``backend.navigation_plan.build_navigation_payload``——浏览器与服务端因此跑的是
    同一份路径与同一份容差，不会各算一套。
    """
    from backend.navigation_plan import build_navigation_payload

    payload = await build_navigation_payload(
        request.map_id,
        request.waypoints,
        algorithm=request.algorithm,
        diagonal=request.diagonal,
        obstacles=request.obstacles,
    )
    return {"success": True, **payload}
