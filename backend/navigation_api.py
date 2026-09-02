"""Route replay API for the Contract-driven MuJoCo policy loop."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from adapters.mjlab.algorithms.registry import create_algorithm
from adapters.mjlab.mujoco_env import ContractMujocoEnv
from contracts.policy_artifact import PolicyArtifact
from backend.simulation_api import MAPS, _scene_geoms


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
    """Replay a trained policy through a waypoint route in Contract-MuJoCo."""
    task = _task(request.task_id)
    if task.config.get("backend") == "native_mjlab":
        return await _run_native_navigation(task, request)
    if request.map_id not in MAPS:
        raise HTTPException(status_code=404, detail=f"Unknown simulation map: {request.map_id}")
    artifact_path = task.task_dir / "artifact.json"
    model_path = task.task_dir / "model_final.pt"
    if not artifact_path.exists() or not model_path.exists():
        raise HTTPException(status_code=400, detail="Training artifact or model is not ready")

    artifact = PolicyArtifact.from_json_file(str(artifact_path))
    config = task.config
    env = ContractMujocoEnv(
        task.contract,
        num_envs=1,
        episode_length_s=float(config.get("episode_length_s", 20.0)),
        reward_scales=config.get("reward_scales", {}),
        scene_geoms=_scene_geoms(request.map_id),
    )
    agent = create_algorithm(
        name=str(config.get("algorithm", "PPO")),
        num_obs=task.contract.observation.dimension,
        num_actions=task.contract.action.dimension,
        config=config,
        device="cpu",
    )
    try:
        try:
            agent.load(str(model_path))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Model checkpoint is not compatible: {exc}") from exc

        route = np.asarray(request.waypoints, dtype=np.float32)
        episode_results: list[dict] = []
        for _ in range(request.episodes):
            obs = env.reset()
            waypoint_index = 0
            steps = 0
            total_reward = 0.0
            start = np.asarray([0.0, 0.0], dtype=np.float32)
            while steps < (request.max_steps or env.max_steps):
                if request.control_mode == "manual":
                    command = request.manual_commands[min(steps, len(request.manual_commands) - 1)] if request.manual_commands else {}
                    vx = float(np.clip(command.get("vx", 0.0), -1.0, 1.0))
                    vy = float(np.clip(command.get("vy", 0.0), -1.0, 1.0))
                    wz = float(np.clip(command.get("wz", 0.0), -1.0, 1.0))
                    action = np.zeros(task.contract.action.dimension, dtype=np.float32)
                    phase = steps * 0.25
                    joint_order = list(task.contract.action.joint_order)
                    for index, joint_name in enumerate(joint_order):
                        name = joint_name.lower()
                        leg = index // 4 if len(joint_order) >= 16 else index // 3
                        offset = 0.0 if leg % 2 == 0 else np.pi
                        if "wheel" in name:
                            action[index] = np.clip(0.55 * vx + 0.15 * vy + 0.1 * wz, -1.0, 1.0)
                        elif name.endswith("hip_joint"):
                            action[index] = np.clip(0.08 * vy + 0.06 * wz, -1.0, 1.0)
                        elif name.endswith("thigh_joint"):
                            action[index] = np.clip(0.20 * vx * np.sin(phase + offset), -1.0, 1.0)
                        else:
                            action[index] = np.clip(-0.25 * abs(vx) * max(0.0, np.sin(phase + offset)), -1.0, 1.0)
                else:
                    action, _ = agent.act(obs, deterministic=True)
                obs, reward, done, info = env.step(action)
                position = np.asarray(info["base_position"][0][:2], dtype=np.float32)
                total_reward += float(reward[0])
                steps += 1
                if waypoint_index < len(route):
                    target = route[waypoint_index]
                    if float(np.linalg.norm(position - target)) <= request.waypoint_tolerance:
                        waypoint_index += 1
                if bool(done[0]):
                    break
            final_position = np.asarray(info["base_position"][0][:2], dtype=np.float32)
            route_distance = float(np.linalg.norm(final_position - start))
            episode_results.append({
                "steps": steps,
                "waypoints_reached": waypoint_index,
                "route_completion": waypoint_index / len(route),
                "distance_travelled": route_distance,
                "reward": total_reward,
                "final_position": final_position.tolist(),
            })

        result = {
            "task_id": task.task_id,
            "artifact_id": artifact.artifact_id,
            "robot": task.contract.family,
            "evaluated_env": "contract-mujoco-navigation",
            "map_id": request.map_id,
            "control_mode": request.control_mode,
            "waypoints": route.tolist(),
            "episodes": request.episodes,
            "route_completion": float(np.mean([item["route_completion"] for item in episode_results])),
            "waypoints_reached": int(np.mean([item["waypoints_reached"] for item in episode_results])),
            "avg_distance_travelled": float(np.mean([item["distance_travelled"] for item in episode_results])),
            "avg_reward": float(np.mean([item["reward"] for item in episode_results])),
            "episode_results": episode_results,
        }
        (task.task_dir / "navigation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"success": True, "result": result}
    finally:
        env.close()


async def _run_native_navigation(task, request: NavigationRequest):
    """Run waypoint following with a native MJLab/RSL-RL checkpoint."""
    from adapters.mjlab.launcher import TrainingLauncher
    from adapters.mjlab.native_adapter import DEFAULT_EXTENSION, DEFAULT_SOURCE

    artifact_path = task.task_dir / "artifact.json"
    checkpoints = sorted(task.task_dir.glob("model_*.pt"))
    if not artifact_path.exists() or not checkpoints:
        raise HTTPException(status_code=400, detail="Native artifact or checkpoint is not ready")
    config = dict(task.config)
    default_task = "Unitree-Go2W-Flat" if task.contract.robot_id == "unitree_go2w" else "Unitree-Go2-Flat"
    config.update({"mode": "navigation", "episodes": request.episodes, "max_steps": request.max_steps or 500, "waypoints": request.waypoints, "waypoint_tolerance": request.waypoint_tolerance, "checkpoint": str(checkpoints[-1].resolve()), "native_task_id": config.get("native_task_id", default_task)})
    config_path = task.task_dir / "native_navigation_config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    launcher = TrainingLauncher(workspace_dir=str(task.task_dir.parent))
    try:
        python_exe = launcher._select_python(config)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    worker = Path(__file__).resolve().parents[1] / "adapters" / "mjlab" / "native_worker.py"
    result = subprocess.run([str(python_exe), str(worker), "--source", str(DEFAULT_SOURCE), "--extension-root", str(DEFAULT_EXTENSION), "--config", str(config_path), "--output", str(task.task_dir)], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=300)
    navigation_file = task.task_dir / "navigation.json"
    if result.returncode != 0 or not navigation_file.exists():
        detail = result.stderr.strip()[-2000:] or result.stdout.strip()[-2000:] or f"native navigation exited with code {result.returncode}"
        raise HTTPException(status_code=500, detail=detail)
    return {"success": True, "result": json.loads(navigation_file.read_text(encoding="utf-8"))}
