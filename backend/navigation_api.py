"""Route replay API for the native MJLab policy loop."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.scenario_maps import MAPS


router = APIRouter(prefix="/api/navigation", tags=["navigation"])


class NavigationRequest(BaseModel):
    task_id: str
    map_id: str = "warehouse"
    control_mode: str = Field(default="auto", pattern="^(auto|manual)$")
    waypoints: list[list[float]] = Field(
        default_factory=lambda: [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
        min_length=2,
    )
    episodes: int = Field(default=1, ge=1, le=20)
    max_steps: int | None = Field(default=None, ge=1, le=10000)
    waypoint_tolerance: float = Field(default=0.35, gt=0.0, le=5.0)
    manual_commands: list[dict[str, float]] = Field(default_factory=list)

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


async def _run_native_navigation(task, request: NavigationRequest):
    """Run waypoint following with a native MJLab/RSL-RL checkpoint."""
    from adapters.mjlab.launcher import TrainingLauncher
    from adapters.mjlab.native_adapter import DEFAULT_SOURCE

    artifact_path = task.task_dir / "artifact.json"
    checkpoints = sorted(task.task_dir.glob("model_*.pt"))
    if not artifact_path.exists() or not checkpoints:
        raise HTTPException(status_code=400, detail="Native artifact or checkpoint is not ready")
    config = dict(task.config)
    config.update({"mode": "navigation", "episodes": request.episodes, "max_steps": request.max_steps or 500, "waypoints": request.waypoints, "waypoint_tolerance": request.waypoint_tolerance, "checkpoint": str(checkpoints[-1].resolve()), "generic_task": True})
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
    return {"success": True, "result": json.loads(navigation_file.read_text(encoding="utf-8"))}
