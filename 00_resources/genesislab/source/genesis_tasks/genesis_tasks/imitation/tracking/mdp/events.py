from __future__ import annotations

import torch
from typing import TYPE_CHECKING, Literal

from genesislab.managers import SceneEntityCfg

if TYPE_CHECKING:
    from genesislab.envs import ManagerBasedRlEnv


def randomize_joint_default_pos(
    env: "ManagerBasedRlEnv",
    env_ids: torch.Tensor | None,
    asset_cfg: SceneEntityCfg,
    pos_distribution_params: tuple[float, float] | None = None,
    operation: Literal["add", "scale", "abs"] = "abs",
    distribution: Literal["uniform", "log_uniform", "gaussian"] = "uniform",
):
    """Placeholder for joint default position randomization (no-op on Genesis backend)."""
    _ = (env, env_ids, asset_cfg, pos_distribution_params, operation, distribution)
    return


def randomize_rigid_body_com(
    env: "ManagerBasedRlEnv",
    env_ids: torch.Tensor | None,
    com_range: dict[str, tuple[float, float]],
    asset_cfg: SceneEntityCfg,
):
    """Placeholder for center-of-mass randomization (no-op on Genesis backend)."""
    _ = (env, env_ids, com_range, asset_cfg)
    return

