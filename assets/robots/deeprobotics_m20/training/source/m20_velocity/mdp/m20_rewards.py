"""Deeprobotics M20-specific reward terms and command sampling.

Ported from the official DeepRoboticsLab IsaacLab training configuration
(BSD-3-Clause) so the M20 velocity task keeps the source training semantics
on the shared mjlab 1.6 runtime.  Standard terms (tracking, orientation,
torque/acc penalties, ...) resolve from mjlab's built-in mdp; only terms
that mjlab does not ship live here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

import torch

from mjlab.entity import Entity
from mjlab.managers.command_manager import CommandTerm
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.tasks.velocity.mdp import UniformVelocityCommand, UniformVelocityCommandCfg

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.sim import Simulation


##
# Observations
##

def joint_pos_rel_zero_wheel(env, all_cfg, wheel_cfg):
    """16-joint position relative to default, wheel slots forced to zero.

    Matches the source deployment observation layout: wheel positions carry no
    meaning for the policy (wheels are velocity-driven), so their slots are
    zeroed while the wheel velocity slots remain.
    """
    asset = env.scene[all_cfg.name]
    pos = asset.data.joint_pos[:, all_cfg.joint_ids] - asset.data.default_joint_pos[:, all_cfg.joint_ids]
    pos = pos.clone()
    pos[:, wheel_cfg.joint_ids] = 0.0
    return pos


##
# Command sampling
##

class UniformThresholdVelocityCommandM20(UniformVelocityCommand):
    """Uniform SE(2) velocity command; small linear commands snap to zero.

    The source configuration resamples every 10 s with a fixed anti-forgetting
    mixture (zero-velocity 20%, pure-turn 20%, pure-x 2%, pure-y 2%), applied by
    the caller through ``ranges``; this class only enforces the dead-zone.
    """

    def _resample_command(self, env_ids: Sequence[int]) -> None:
        super()._resample_command(env_ids)
        small = torch.norm(self.vel_command_b[env_ids, :2], dim=1) < 0.2
        self.vel_command_b[env_ids, 0] *= small
        self.vel_command_b[env_ids, 1] *= small


##
# Reward terms
##

def joint_power(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Penalize |joint_vel * applied_torque| (electrical power proxy)."""
    asset: Entity = env.scene[asset_cfg.name]
    return torch.sum(
        torch.abs(asset.data.joint_vel[:, asset_cfg.joint_ids] * asset.data.applied_torque[:, asset_cfg.joint_ids]),
        dim=1,
    )


def joint_pos_penalty(
    env: ManagerBasedRlEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    stand_still_scale: float,
    velocity_threshold: float,
    command_threshold: float,
) -> torch.Tensor:
    """L1 joint position deviation; amplified when standing (no cmd / no motion)."""
    asset: Entity = env.scene[asset_cfg.name]
    cmd = torch.linalg.vector_norm(env.command_manager.get_command(command_name), dim=1)
    body_vel = torch.linalg.vector_norm(asset.data.root_link_lin_vel_b[:, :2], dim=1)
    running = torch.linalg.vector_norm(
        asset.data.joint_pos[:, asset_cfg.joint_ids] - asset.data.default_joint_pos[:, asset_cfg.joint_ids], dim=1
    )
    return torch.where(
        torch.logical_or(cmd > command_threshold, body_vel > velocity_threshold),
        running,
        stand_still_scale * running,
    )


def joint_mirror(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg,
    mirror_joints: list[list[str]],
) -> torch.Tensor:
    """Penalize pose asymmetry between diagonal leg pairs (gated by upright stance)."""
    asset: Entity = env.scene[asset_cfg.name]
    cache_key = "joint_mirror_joints_cache"
    if not hasattr(env, cache_key) or getattr(env, cache_key) is None:
        setattr(env, cache_key, [
            [asset.find_joints(joint_name) for joint_name in joint_pair]
            for joint_pair in mirror_joints
        ])
    cache = getattr(env, cache_key)
    reward = torch.zeros(env.num_envs, device=env.device)
    for joint_pair in cache:
        diff = torch.sum(
            torch.square(asset.data.joint_pos[:, joint_pair[0][0]] - asset.data.joint_pos[:, joint_pair[1][0]]),
            dim=-1,
        )
        reward += diff
    reward *= 1 / len(mirror_joints) if mirror_joints else 0
    reward *= torch.clamp(-asset.data.projected_gravity_b[:, 2], 0, 0.7) / 0.7
    return reward


def feet_contact_without_cmd(
    env: ManagerBasedRlEnv,
    command_name: str,
    sensor_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Reward wheel ground contact while the velocity command is small."""
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    contact = contact_sensor.compute_first_contact(env.step_dt)[:, sensor_cfg.body_ids]
    reward = torch.sum(contact, dim=-1).float()
    reward *= torch.linalg.vector_norm(env.command_manager.get_command(command_name), dim=1) < 0.5
    return reward


def stand_still_joint_deviation_l1(
    env: ManagerBasedRlEnv,
    command_name: str,
    command_threshold: float = 0.06,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Penalize joint deviation from default when the command is nearly zero."""
    command = env.command_manager.get_command(command_name)
    asset: Entity = env.scene[asset_cfg.name]
    angle = asset.data.joint_pos[:, asset_cfg.joint_ids] - asset.data.default_joint_pos[:, asset_cfg.joint_ids]
    return torch.sum(torch.abs(angle), dim=1) * (torch.norm(command, dim=1) < command_threshold)


def upward(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    """Reward keeping the base upright: (1 - gravity_z)^2."""
    asset = env.scene[asset_cfg.name]
    return torch.square(1 - asset.data.projected_gravity_b[:, 2])


def base_height_l2(
    env: ManagerBasedRlEnv,
    target_height: float,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    sensor_cfg: SceneEntityCfg | None = None,
) -> torch.Tensor:
    """Penalize base height deviation from target (L2 squared)."""
    asset = env.scene[asset_cfg.name]
    adjusted_target_height = target_height
    if sensor_cfg is not None:
        sensor = env.scene.sensors[sensor_cfg.name]
        ray_hits = sensor.data.ray_hits_w[..., 2]
        if torch.isnan(ray_hits).any() or torch.isinf(ray_hits).any() or torch.max(torch.abs(ray_hits)) > 1e6:
            adjusted_target_height = asset.data.root_link_pos_w[:, 2]
        else:
            adjusted_target_height = target_height + torch.mean(ray_hits, dim=1)
    return torch.square(asset.data.root_link_pos_w[:, 2] - adjusted_target_height)


def lin_vel_z_l2(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    """Penalize base vertical velocity (L2 squared)."""
    asset = env.scene[asset_cfg.name]
    return torch.square(asset.data.root_link_lin_vel_b[:, 2])


def ang_vel_xy_l2(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    """Penalize base angular velocity in xy (L2 squared)."""
    asset = env.scene[asset_cfg.name]
    return torch.sum(torch.square(asset.data.root_link_ang_vel_b[:, :2]), dim=1)


def flat_orientation_l2(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    """Penalize non-flat base orientation (projected gravity xy, L2 squared)."""
    asset = env.scene[asset_cfg.name]
    return torch.sum(torch.square(asset.data.projected_gravity_b[:, :2]), dim=1)


def undesired_contacts(
    env: ManagerBasedRlEnv, threshold: float, sensor_cfg: SceneEntityCfg
) -> torch.Tensor:
    """Penalize contact on the given sensor bodies above a force threshold."""
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    contact = contact_sensor.data.net_forces_w_history[:, 0, :, :][:, sensor_cfg.body_ids, :]
    return torch.sum(
        torch.max(torch.norm(contact, dim=-1) - threshold, torch.tensor(0.0, device=env.device)),
        dim=1,
    )


def contact_forces(
    env: ManagerBasedRlEnv, threshold: float, sensor_cfg: SceneEntityCfg
) -> torch.Tensor:
    """Penalize contact forces above the threshold (L2 norm of the excess)."""
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    contact = contact_sensor.data.net_forces_w_history[:, 0, :, :][:, sensor_cfg.body_ids, :]
    norm = torch.linalg.vector_norm(contact, dim=-1)
    return torch.sum(torch.square(torch.clamp(norm - threshold, min=0.0)), dim=1)
