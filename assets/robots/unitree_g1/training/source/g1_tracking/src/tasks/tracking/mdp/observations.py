"""Observation terms exposing the current reference-motion frame."""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.utils.lab_api.math import quat_apply_inverse

from src.tasks.tracking.motion_loader import TrackingMotionManager

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv


def _motion(env: ManagerBasedRlEnv, motion_dir: str) -> TrackingMotionManager:
    return TrackingMotionManager.get(motion_dir, env)


def ref_dof_pos(env: ManagerBasedRlEnv, motion_dir: str) -> torch.Tensor:
    """Reference joint positions at the env's current frame (robot order)."""
    return _motion(env, motion_dir).get_ref_dof_pos(env)


def ref_dof_vel(env: ManagerBasedRlEnv, motion_dir: str) -> torch.Tensor:
    """Reference joint velocities at the env's current frame (robot order)."""
    return _motion(env, motion_dir).get_ref_dof_vel(env)


def ref_base_quat(env: ManagerBasedRlEnv, motion_dir: str) -> torch.Tensor:
    """Reference root orientation (wxyz)."""
    return _motion(env, motion_dir).get_ref_base_quat(env)


def ref_base_lin_vel_b(env: ManagerBasedRlEnv, motion_dir: str) -> torch.Tensor:
    """Reference root linear velocity in the reference body frame."""
    motion = _motion(env, motion_dir)
    return quat_apply_inverse(motion.get_ref_base_quat(env), motion.get_ref_base_lin_vel_w(env))


def ref_base_ang_vel_b(env: ManagerBasedRlEnv, motion_dir: str) -> torch.Tensor:
    """Reference root angular velocity in the reference body frame."""
    motion = _motion(env, motion_dir)
    return quat_apply_inverse(motion.get_ref_base_quat(env), motion.get_ref_base_ang_vel_w(env))
