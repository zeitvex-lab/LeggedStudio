"""Route replay API for the Contract-driven MuJoCo policy loop."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from adapters.mjlab_new.algorithms.ppo import PPOAlgorithm, PPOConfig
from adapters.mjlab_new.mujoco_env import ContractMujocoEnv
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
    agent = PPOAlgorithm(
        num_obs=task.contract.observation.dimension,
        num_actions=task.contract.action.dimension,
        config=PPOConfig(learning_rate=float(config.get("learning_rate", 3e-4))),
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
                    for leg in range(max(1, task.contract.action.dimension // 3)):
                        offset = 0.0 if leg % 2 == 0 else np.pi
                        base = leg * 3
                        if base + 2 >= len(action):
                            break
                        action[base] = np.clip(0.08 * vy + 0.06 * wz, -1.0, 1.0)
                        action[base + 1] = np.clip(0.20 * vx * np.sin(phase + offset), -1.0, 1.0)
                        action[base + 2] = np.clip(-0.25 * abs(vx) * max(0.0, np.sin(phase + offset)), -1.0, 1.0)
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
