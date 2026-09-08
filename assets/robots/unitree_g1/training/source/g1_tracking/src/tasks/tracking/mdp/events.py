"""Startup / reset event terms for the motion-tracking task."""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.managers.scene_entity_config import SceneEntityCfg

from src.tasks.tracking.motion_loader import TrackingMotionManager

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def init_tracking_motion(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor | None,
    motion_dir: str,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> None:
    """Startup event: load reference motions and resolve robot-side indices."""
    manager = TrackingMotionManager.get(motion_dir, env)
    manager.resolve_robot_layout(env, asset_cfg.name)
    manager.init_envs(env)


def reset_from_reference_motion(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor | None,
    motion_dir: str,
    rsi_prob: float = 0.7,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> None:
    """Reset event: reference state initialization (RSI).

    Samples a random (clip, frame) reference clock per env and, with
    probability ``rsi_prob``, teleports the robot onto that reference state
    (root pose / velocity + joint state). Envs without RSI keep the default
    init state but still track the sampled clock, matching the upstream
    ``reference_state_initialization_prob = 0.7`` behaviour.
    """
    if env_ids is None:
        env_ids = torch.arange(env.num_envs, device=env.device, dtype=torch.long)
    TrackingMotionManager.get(motion_dir, env).reset_envs(
        env, env_ids, rsi_prob, asset_cfg
    )
