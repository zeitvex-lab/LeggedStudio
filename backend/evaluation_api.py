"""Local policy evaluation API for completed Contract-driven training runs."""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from adapters.mjlab_new.algorithms.ppo import PPOAlgorithm, PPOConfig
from adapters.mjlab_new.mujoco_env import ContractMujocoEnv
from contracts.policy_artifact import PolicyArtifact
from contracts.robot_contract_v2 import RobotContractV2


router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


class EvaluationRequest(BaseModel):
    task_id: str
    episodes: int = Field(default=5, ge=1, le=100)
    max_steps: int | None = Field(default=None, ge=1, le=10000)


def _task(task_id: str):
    from backend.training_manager import get_training_manager

    manager = get_training_manager()
    task = manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@router.get("/list")
async def list_evaluable_tasks():
    from backend.training_manager import get_training_manager

    manager = get_training_manager()
    items = []
    for task in manager.tasks.values():
        artifact_path = task.task_dir / "artifact.json"
        model_path = task.task_dir / "model_final.pt"
        if artifact_path.exists() and model_path.exists() and model_path.stat().st_size > 1024:
            items.append({"task_id": task.task_id, "robot": task.contract.family, "status": task.to_dict()["status"], "artifact_path": str(artifact_path)})
    return {"count": len(items), "tasks": items}


@router.post("/run")
async def run_evaluation(request: EvaluationRequest):
    task = _task(request.task_id)
    artifact_path = task.task_dir / "artifact.json"
    model_path = task.task_dir / "model_final.pt"
    if not artifact_path.exists() or not model_path.exists():
        raise HTTPException(status_code=400, detail="Training artifact or model is not ready")

    artifact = PolicyArtifact.from_json_file(str(artifact_path))
    config = task.config
    env = ContractMujocoEnv(task.contract, num_envs=1, episode_length_s=float(config.get("episode_length_s", 20.0)), reward_scales=config.get("reward_scales", {}))
    agent = PPOAlgorithm(
        num_obs=task.contract.observation.dimension,
        num_actions=task.contract.action.dimension,
        config=PPOConfig(learning_rate=float(config.get("learning_rate", 3e-4))),
        device="cpu",
    )
    try:
        try:
            agent.load(str(model_path))
        except (RuntimeError, ValueError, EOFError, ImportError, pickle.UnpicklingError) as exc:
            raise HTTPException(status_code=400, detail=f"Model checkpoint is not compatible with the current PPO adapter: {exc}") from exc
        rewards: list[float] = []
        velocities: list[float] = []
        successes: list[bool] = []
        for _ in range(request.episodes):
            obs = env.reset()
            total_reward = 0.0
            velocity_sum = 0.0
            steps = 0
            limit = request.max_steps or env.max_steps
            while steps < limit:
                action, _ = agent.act(obs, deterministic=True)
                obs, reward, done, info = env.step(action)
                total_reward += float(reward[0])
                velocity_sum += float(info["base_velocity"][0])
                steps += 1
                if bool(done[0]):
                    break
            rewards.append(total_reward)
            velocities.append(velocity_sum / max(1, steps))
            successes.append(bool(steps >= min(limit, env.max_steps) and total_reward > 0))
        result = {
            "task_id": task.task_id,
            "artifact_id": artifact.artifact_id,
            "robot": task.contract.family,
            "episodes": request.episodes,
            "avg_reward": float(np.mean(rewards)),
            "std_reward": float(np.std(rewards)),
            "avg_forward_velocity": float(np.mean(velocities)),
            "success_rate": float(np.mean(successes)),
            "evaluated_env": "contract-mujoco",
        }
        (task.task_dir / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"success": True, "result": result}
    finally:
        env.close()
