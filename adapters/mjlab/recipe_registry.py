"""Task/recipe registry inspired by RoboLab TaskSpec and MJLab managers."""

from __future__ import annotations

from typing import Any

from contracts.scenario_contract import TrainingRecipe
from adapters.mjlab.env_factory import get_reward_preset, get_reward_terms


TASKS: dict[str, dict[str, Any]] = {
    "forward_walk": {"label": "Forward walk", "terrain": "plane", "control": "velocity"},
    "trot": {"label": "Trot", "terrain": "plane", "control": "velocity"},
    "rough_terrain": {"label": "Rough terrain", "terrain": "rough", "control": "velocity"},
    "stairs": {"label": "Stairs", "terrain": "stairs", "control": "velocity"},
}

REWARD_ALIASES = {
    "tracking_lin_vel": "track_linear_velocity",
    "tracking_ang_vel": "track_angular_velocity",
    "orientation": "body_orientation_l2",
    "torques": "joint_torques_l2",
    "dof_vel": "joint_vel_l2",
    "dof_acc": "joint_acc_l2",
    "action_rate": "action_rate_l2",
    "feet_air_time": "air_time",
}


def resolve_recipe(config: dict[str, Any]) -> TrainingRecipe:
    task_name = str(config.get("task_name", "forward_walk"))
    if task_name not in TASKS:
        raise ValueError(f"unknown task {task_name}; available: {', '.join(sorted(TASKS))}")
    algorithm = str(config.get("algorithm", "PPO")).upper()
    if algorithm not in {"PPO", "SAC", "TD3"}:
        raise ValueError(f"unknown algorithm {algorithm}")
    rewards = {REWARD_ALIASES.get(str(key), str(key)): float(value) for key, value in get_reward_preset(task_name).items()}
    rewards.update({str(key): float(value) for key, value in config.get("reward_scales", {}).items()})
    rewards = {key: value for key, value in rewards.items() if value is not None}
    environment = {
        "num_envs": int(config.get("num_envs", 4096)),
        "episode_length_s": float(config.get("episode_length_s", 20.0)),
        "terrain_type": str(config.get("terrain_type", TASKS[task_name]["terrain"])),
        "terrain": dict(config.get("terrain", {})),
        "command_ranges": dict(config.get("command_ranges", {})),
        "noise": dict(config.get("noise", {})),
        "curriculum": dict(config.get("curriculum", {})),
        "reward_params": dict(config.get("reward_params", {})),
    }
    algorithm_config = {key: value for key, value in config.items() if key not in {"task_name", "algorithm", "reward_scales", "num_envs", "episode_length_s", "terrain_type"}}
    backend = str(config.get("backend", "native_mjlab"))
    if backend != "native_mjlab":
        raise ValueError("Legged Studio training supports only the native_mjlab backend")
    return TrainingRecipe(task_name=task_name, algorithm=algorithm, backend=backend, reward_scales=rewards, environment=environment, algorithm_config=algorithm_config, seed=int(config.get("seed", 0)))


def list_tasks() -> list[dict[str, Any]]:
    return [{"id": key, **value, "reward_terms": list(get_reward_terms())} for key, value in TASKS.items()]
