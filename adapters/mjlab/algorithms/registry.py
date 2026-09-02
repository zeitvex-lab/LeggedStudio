"""Algorithm capability registry shared by API, Web and CLI."""

from __future__ import annotations

from typing import Any

ALGORITHM_REGISTRY: dict[str, dict[str, Any]] = {
    "PPO": {
        "label": "PPO",
        "family": "on_policy",
        "available": True,
        "description": "稳定的 on-policy 基线，适合速度跟踪和快速验证",
        "config_fields": ["learning_rate", "num_steps", "num_minibatches", "gamma", "gae_lambda", "clip_param", "entropy_coef"],
    },
    "SAC": {
        "label": "SAC",
        "family": "off_policy",
        "available": True,
        "description": "带熵正则的连续动作 off-policy 算法，适合样本复用",
        "config_fields": ["learning_rate", "gamma", "tau", "batch_size", "replay_size", "alpha"],
    },
    "TD3": {
        "label": "TD3",
        "family": "off_policy",
        "available": True,
        "description": "双 Q 网络连续动作算法，适合低噪声精调",
        "config_fields": ["learning_rate", "gamma", "tau", "batch_size", "replay_size", "policy_delay", "exploration_noise"],
    },
}


def list_algorithms() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in ALGORITHM_REGISTRY.items()]


def create_algorithm(name: str, num_obs: int, num_actions: int, config: dict[str, Any], device: str):
    # Keep registry discovery available in the lightweight control-plane
    # environment.  Training dependencies are loaded only when a run starts.
    from adapters.mjlab.algorithms.off_policy import OffPolicyConfig, SACAlgorithm, TD3Algorithm
    from adapters.mjlab.algorithms.ppo import PPOAlgorithm, PPOConfig
    normalized = name.upper()
    if normalized not in ALGORITHM_REGISTRY:
        raise ValueError(f"unknown algorithm {name}; available: {', '.join(ALGORITHM_REGISTRY)}")
    if normalized == "PPO":
        return PPOAlgorithm(
            num_obs=num_obs,
            num_actions=num_actions,
            config=PPOConfig(**{key: value for key, value in config.items() if key in PPOConfig.__annotations__}),
            device=device,
        )
    off_policy = OffPolicyConfig(**{key: value for key, value in config.items() if key in OffPolicyConfig.__annotations__})
    cls = SACAlgorithm if normalized == "SAC" else TD3Algorithm
    return cls(num_obs=num_obs, num_actions=num_actions, config=off_policy, device=device)


__all__ = ["ALGORITHM_REGISTRY", "create_algorithm", "list_algorithms"]
