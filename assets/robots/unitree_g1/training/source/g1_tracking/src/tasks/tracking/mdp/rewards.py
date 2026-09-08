"""DeepMimic-style tracking reward terms.

Mirrors the upstream LeggedGym-Ex ``g1_deepmimic`` reward family:

- ``tracking_ref_dof_pos``   exp(-sum((q - q_ref)^2) / sigma)
- ``tracking_ref_dof_vel``   exp(-sum|qd - qd_ref| / sigma)
- ``tracking_ref_base_pose`` exp(-(pos_err + 0.1 * rot_err) / sigma)
- ``tracking_ref_base_vel``  exp(-(lin_err + 0.1 * ang_err) / sigma)
- ``tracking_ref_key_pos``   exp(-sum((key_pos_rel - key_ref)^2) / sigma)

Two deliberate deviations from the literal source formulas:
- Orientation error uses the sign-aware quaternion angular error
  (``quat_error_magnitude``) instead of raw component-wise squared
  difference, which double-counts the q / -q symmetry.
- Base velocities are compared in each body's own frame (robot frame vs
  reference frame), matching the source's body-frame comparison while
  staying robust to the yaw offset between envs and the motion clip.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.utils.lab_api.math import quat_apply_inverse, quat_error_magnitude

from src.tasks.tracking.motion_loader import TrackingMotionManager

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def _motion(env: ManagerBasedRlEnv, motion_dir: str) -> TrackingMotionManager:
    return TrackingMotionManager.get(motion_dir, env)


def tracking_ref_dof_pos(
    env: ManagerBasedRlEnv,
    motion_dir: str,
    std: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward for imitating the reference joint positions."""
    asset: Entity = env.scene[asset_cfg.name]
    dof_pos_error = torch.sum(
        torch.square(asset.data.joint_pos - _motion(env, motion_dir).get_ref_dof_pos(env)),
        dim=-1,
    )
    return torch.exp(-dof_pos_error / std)


def tracking_ref_dof_vel(
    env: ManagerBasedRlEnv,
    motion_dir: str,
    std: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward for imitating the reference joint velocities."""
    asset: Entity = env.scene[asset_cfg.name]
    dof_vel_error = torch.sum(
        torch.abs(asset.data.joint_vel - _motion(env, motion_dir).get_ref_dof_vel(env)),
        dim=-1,
    )
    return torch.exp(-dof_vel_error / std)


def tracking_ref_base_pose(
    env: ManagerBasedRlEnv,
    motion_dir: str,
    std: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward for imitating the reference root position and orientation."""
    asset: Entity = env.scene[asset_cfg.name]
    motion = _motion(env, motion_dir)
    base_pos = asset.data.root_link_pos_w
    ref_pos = motion.get_ref_base_pos(env) + env.scene.env_origins
    base_pos_error = torch.sum(torch.square(base_pos - ref_pos), dim=-1)

    base_rot_error = torch.square(
        quat_error_magnitude(asset.data.root_link_quat_w, motion.get_ref_base_quat(env))
    )
    return torch.exp(-(base_pos_error + 0.1 * base_rot_error) / std)


def tracking_ref_base_vel(
    env: ManagerBasedRlEnv,
    motion_dir: str,
    std: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward for imitating the reference root linear/angular velocity."""
    asset: Entity = env.scene[asset_cfg.name]
    motion = _motion(env, motion_dir)

    ref_quat = motion.get_ref_base_quat(env)
    ref_lin_vel_b = quat_apply_inverse(ref_quat, motion.get_ref_base_lin_vel_w(env))
    ref_ang_vel_b = quat_apply_inverse(ref_quat, motion.get_ref_base_ang_vel_w(env))

    base_lin_vel_error = torch.sum(
        torch.square(asset.data.root_link_lin_vel_b - ref_lin_vel_b), dim=-1
    )
    base_ang_vel_w = asset.data.root_link_ang_vel_w
    base_ang_vel_b = quat_apply_inverse(asset.data.root_link_quat_w, base_ang_vel_w)
    base_ang_vel_error = torch.sum(torch.square(base_ang_vel_b - ref_ang_vel_b), dim=-1)

    return torch.exp(-(base_lin_vel_error + 0.1 * base_ang_vel_error) / std)


def tracking_ref_key_pos(
    env: ManagerBasedRlEnv,
    motion_dir: str,
    std: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward for imitating the reference key-body offsets from the root.

    Both sides are world-oriented offsets from their own root, so the env
    spawn translation cancels and global body orientation is what matters —
    same semantics as the upstream reward.
    """
    asset: Entity = env.scene[asset_cfg.name]
    motion = _motion(env, motion_dir)
    key_body_ids = motion.get_key_body_ids()
    key_body_pos_relative_to_base = (
        asset.data.body_link_pos_w[:, key_body_ids, :] - asset.data.root_link_pos_w.unsqueeze(1)
    )
    key_body_pos_error = torch.sum(
        torch.square(key_body_pos_relative_to_base - motion.get_ref_key_body_pos(env)),
        dim=(1, 2),
    )
    return torch.exp(-key_body_pos_error / std)
