"""Deeprobotics Lite3-specific reward terms and gait-level curriculum.

Ported from the official DeepRoboticsLab IsaacLab training configuration
(BSD-3-Clause) so the Lite3 velocity task keeps the source training semantics
on the shared mjlab 1.6 runtime:

- global ``gait_level`` curriculum scalar updated from mean terrain level
  (synchronised inside the terrain curriculum term),
- ``GaitReward`` trot-sync term as a stateless function with env-cached
  joint id resolution,
- Bezier swing-trajectory tracking (``phase_foot_trajectory_exp``),
- command-component-gated air-time rewards,
- foot impact velocity, feet slide, joint power/mirror/pos-penalty terms.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

import torch

from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommand, UniformVelocityCommandCfg
from mjlab.utils.lab_api.math import quat_apply_inverse

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

##
# Global gait-level curriculum scalar.
##

gait_level: float = 0.0


def get_gait_level_tensor(env: ManagerBasedRlEnv) -> torch.Tensor:
    """Global gait_level broadcast to the environment batch size."""
    return torch.full((env.num_envs,), gait_level, device=env.device)


def update_gait_level_from_terrain_mean(terrain_level_mean: float | torch.Tensor) -> float:
    """Map mean terrain level to [0, 1] gait level (exp ramp, saturated at 3.0)."""
    global gait_level
    mean_tensor = torch.as_tensor(terrain_level_mean, dtype=torch.float32)
    if mean_tensor.numel() == 0:
        mean_val = 0.0
    else:
        mean_val = float(torch.mean(mean_tensor).item())
    if math.isnan(mean_val) or math.isinf(mean_val):
        mean_val = 0.0
    if mean_val <= 0.0:
        gait_level = 0.0
    elif mean_val < 3.0:
        gait_level = math.exp(mean_val - 3.0)
    else:
        gait_level = 1.0
    return gait_level


def terrain_levels_vel_with_gait(
    env: ManagerBasedRlEnv,
    env_ids,
    command_name: str = "twist",
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """mjlab terrain curriculum with synchronised gait_level update."""
    result = velocity_mdp_terrain_levels(env, env_ids, command_name, asset_cfg)
    update_gait_level_from_terrain_mean(result)
    return result


def velocity_mdp_terrain_levels(
    env: ManagerBasedRlEnv,
    env_ids,
    command_name: str,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Terrain curriculum: move up when the robot walks far, down otherwise."""
    asset: Entity = env.scene[asset_cfg.name]
    terrain = env.scene.terrain
    assert terrain is not None
    terrain_generator = terrain.cfg.terrain_generator
    assert terrain_generator is not None

    command = env.command_manager.get_command(command_name)
    assert command is not None

    distance = torch.norm(
        asset.data.root_link_pos_w[env_ids, :2] - env.scene.env_origins[env_ids, :2], dim=1
    )
    move_up = distance > terrain_generator.size[0] / 2
    move_down = (
        distance < torch.norm(command[env_ids, :2], dim=1) * env.max_episode_length_s * 0.5
    )
    move_down *= ~move_up

    terrain.update_env_origins(env_ids, move_up, move_down)
    return torch.mean(terrain.terrain_levels.float())


##
# GaitReward: trot foot-pair sync / anti-sync (stateless function form).
##


def _resolve_foot_ids(env: ManagerBasedRlEnv, sensor_name: str, body_names: Sequence[str]):
    key = f"_lite3_foot_ids_{sensor_name}"
    cache = getattr(env, key, None)
    if cache is None:
        sensor = env.scene.sensors[sensor_name]
        cache = [sensor.find_bodies([name])[0][0] for name in body_names]
        setattr(env, key, cache)
    return cache


def feet_gait(
    env: ManagerBasedRlEnv,
    command_name: str,
    std: float,
    max_err: float,
    velocity_threshold: float,
    command_threshold: float,
    sensor_cfg: SceneEntityCfg,
    synced_feet_pair_names: list[list[str]],
) -> torch.Tensor:
    """Trot gait reward: synced pairs match contact timing, diagonal pairs anti-match."""
    sensor = env.scene.sensors[sensor_cfg.name]
    foot_ids = _resolve_foot_ids(env, sensor_cfg.name, [n for pair in synced_feet_pair_names for n in pair])
    pairs = [
        (foot_ids[0], foot_ids[3]),  # FL <-> HR
        (foot_ids[1], foot_ids[2]),  # FR <-> HL
    ]

    def sync_reward(foot_0: int, foot_1: int) -> torch.Tensor:
        se_air = torch.clip(
            torch.square(sensor.data.current_air_time[:, foot_0] - sensor.data.current_air_time[:, foot_1]),
            max=max_err**2,
        )
        se_contact = torch.clip(
            torch.square(sensor.data.current_contact_time[:, foot_0] - sensor.data.current_contact_time[:, foot_1]),
            max=max_err**2,
        )
        return torch.exp(-(se_air + se_contact) / std)

    def async_reward(foot_0: int, foot_1: int) -> torch.Tensor:
        se_act_0 = torch.clip(
            torch.square(sensor.data.current_air_time[:, foot_0] - sensor.data.current_contact_time[:, foot_1]),
            max=max_err**2,
        )
        se_act_1 = torch.clip(
            torch.square(sensor.data.current_contact_time[:, foot_0] - sensor.data.current_air_time[:, foot_1]),
            max=max_err**2,
        )
        return torch.exp(-(se_act_0 + se_act_1) / std)

    sync = sync_reward(*pairs[0]) * sync_reward(*pairs[1])
    async_reward = (
        async_reward(pairs[0][0], pairs[1][0])
        * async_reward(pairs[0][1], pairs[1][1])
        * async_reward(pairs[0][0], pairs[1][1])
        * async_reward(pairs[1][0], pairs[0][1])
    )
    cmd = torch.linalg.vector_norm(env.command_manager.get_command(command_name), dim=1)
    body_vel = torch.linalg.vector_norm(env.scene["robot"].data.root_link_lin_vel_b[:, :2], dim=1)
    return torch.where(
        torch.logical_or(cmd > command_threshold, body_vel > velocity_threshold),
        sync * async_reward,
        torch.zeros_like(cmd),
    )


##
# Bezier swing trajectory tracking.
##

def _bernstein_torch(n: int, k: int, t: torch.Tensor) -> torch.Tensor:
    coeff = float(math.comb(n, k))
    return coeff * (1.0 - t) ** (n - k) * t**k


def _bezier_curve_torch(control_points: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
    n = control_points.shape[0] - 1
    out = torch.zeros(*t.shape, 2, device=t.device, dtype=t.dtype)
    for k in range(n + 1):
        out = out + _bernstein_torch(n, k, t).unsqueeze(-1) * control_points[k]
    return out


def _bezier_curve_derivative_torch(control_points: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
    n = control_points.shape[0] - 1
    delta_ctrl = n * (control_points[1:] - control_points[:-1])
    out = torch.zeros(*t.shape, 2, device=t.device, dtype=t.dtype)
    for k in range(n):
        out = out + _bernstein_torch(n - 1, k, t).unsqueeze(-1) * delta_ctrl[k]
    return out


def phase_foot_trajectory_exp(
    env: ManagerBasedRlEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    std: float = 0.1,
    command_threshold: float = 0.1,
    cycle_time: float = 0.4,
    phase_offsets: tuple[float, ...] = (0.0, 1.0, 1.0, 0.0),
    gait_span: float = -0.008,
    gait_psi: float = 0.15,
    gait_delta: float = 0.03,
    x_offset: float = 0.0,
    stance_span: float = 0.20,
    stand_ref_z_offset: float = -0.2,
    velocity_weight: float = 0.5,
) -> torch.Tensor:
    """Track a MuJoCo-style phase foot trajectory in body frame (exp kernel)."""
    asset: Entity = env.scene[asset_cfg.name]
    body_ids = asset_cfg.body_ids
    num_feet = len(body_ids)
    if num_feet == 0:
        return torch.zeros(env.num_envs, device=env.device)
    if len(phase_offsets) != num_feet:
        raise ValueError("phase_offsets length must match tracked feet.")

    if (not hasattr(env, "phase_foot_ref_body")) or (env.phase_foot_ref_body.shape[1] != num_feet):
        rel_foot_pos_w = asset.data.body_pos_w[:, body_ids, :] - asset.data.root_pos_w[:, :].unsqueeze(1)
        foot_pos_b = torch.zeros(env.num_envs, num_feet, 3, device=env.device)
        for i in range(num_feet):
            foot_pos_b[:, i, :] = quat_apply_inverse(asset.data.root_quat_w, rel_foot_pos_w[:, i, :])
        ref = foot_pos_b[0].detach().clone()
        ref[:, 2] += stand_ref_z_offset
        env.phase_foot_ref_body = ref.unsqueeze(0)

    stand_ref_body = env.phase_foot_ref_body.to(env.device).expand(env.num_envs, -1, -1)

    phase_time = env.episode_length_buf.float() * env.step_dt
    phase_offsets_t = torch.tensor(phase_offsets, device=env.device, dtype=phase_time.dtype).unsqueeze(0)
    S = torch.remainder((2.0 * phase_time / max(cycle_time, 1e-6)).unsqueeze(1) + phase_offsets_t, 2.0)

    tau = float(gait_span)
    psi = float(gait_psi)
    delta = float(gait_delta)
    stance_span = min(max(float(stance_span), 1e-6), 2.0 - 1e-6)

    q = torch.zeros_like(S)
    z = torch.zeros_like(S)
    dq_dS = torch.zeros_like(S)
    dz_dS = torch.zeros_like(S)

    stance_mask = S < stance_span
    if stance_mask.any():
        s_stance = S / stance_span
        q = torch.where(stance_mask, tau * (1.0 - 2.0 * s_stance), q)
        z = torch.where(stance_mask, torch.full_like(S, delta), z)
        dq_dS = torch.where(stance_mask, torch.full_like(S, -2.0 * tau / stance_span), dq_dS)

    swing_mask = ~stance_mask
    if swing_mask.any():
        t_bezier = torch.clamp((S - stance_span) / (2.0 - stance_span), 0.0, 1.0)
        ctrl = torch.tensor(
            [
                [-tau, 0.0],
                [-0.95 * tau, 0.80 * psi],
                [-0.55 * tau, 1.00 * psi],
                [0.55 * tau, 1.00 * psi],
                [0.95 * tau, 0.80 * psi],
                [tau, 0.0],
            ],
            device=env.device,
            dtype=S.dtype,
        )
        qz_swing = _bezier_curve_torch(ctrl, t_bezier)
        dqz_dt = _bezier_curve_derivative_torch(ctrl, t_bezier)
        dt_dS = 1.0 / (2.0 - stance_span)
        q = torch.where(swing_mask, qz_swing[..., 0], q)
        z = torch.where(swing_mask, qz_swing[..., 1] + delta, z)
        dq_dS = torch.where(swing_mask, dqz_dt[..., 0] * dt_dS, dq_dS)
        dz_dS = torch.where(swing_mask, dqz_dt[..., 1] * dt_dS, dz_dS)

    dS_dt = 2.0 / max(cycle_time, 1e-6)
    dq_dt = dq_dS * dS_dt
    dz_dt = dz_dS * dS_dt

    ref_pos_b = stand_ref_body + torch.stack([q + float(x_offset), torch.zeros_like(q), z], dim=-1)
    ref_vel_b = torch.stack([dq_dt, torch.zeros_like(dq_dt), dz_dt], dim=-1)

    rel_foot_pos_w = asset.data.body_pos_w[:, body_ids, :] - asset.data.root_pos_w[:, :].unsqueeze(1)
    rel_foot_vel_w = asset.data.body_lin_vel_w[:, body_ids, :] - asset.data.root_lin_vel_w[:, :].unsqueeze(1)
    foot_pos_b = torch.zeros(env.num_envs, num_feet, 3, device=env.device)
    foot_vel_b = torch.zeros(env.num_envs, num_feet, 3, device=env.device)
    for i in range(num_feet):
        foot_pos_b[:, i, :] = quat_apply_inverse(asset.data.root_quat_w, rel_foot_pos_w[:, i, :])
        foot_vel_b[:, i, :] = quat_apply_inverse(asset.data.root_quat_w, rel_foot_vel_w[:, i, :])

    pos_offset = foot_pos_b - ref_pos_b
    vel_offset = foot_vel_b - ref_vel_b
    pos_err = torch.sum(torch.square(pos_offset), dim=1)
    vel_err = torch.sum(torch.square(vel_offset), dim=1)
    total_err = torch.sum(pos_err, dim=1) + float(velocity_weight) * torch.sum(vel_err, dim=1)
    reward = torch.exp(-total_err / max(std, 1e-6) ** 2)

    command = env.command_manager.get_command(command_name)
    gate = torch.linalg.vector_norm(command[:, :3], dim=1) > command_threshold
    return reward * gate.float() * get_gait_level_tensor(env)


##
# Common single-purpose terms.
##


def joint_power(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset: Entity = env.scene[asset_cfg.name]
    return torch.sum(
        torch.abs(asset.data.joint_vel[:, asset_cfg.joint_ids] * asset.data.applied_torque[:, asset_cfg.joint_ids]),
        dim=1,
    )


def joint_mirror(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg, mirror_joints: list[list[str]]) -> torch.Tensor:
    asset: Entity = env.scene[asset_cfg.name]
    key = "_lite3_joint_mirror_cache"
    if not hasattr(env, key) or getattr(env, key) is None:
        setattr(env, key, [
            [asset.find_joints(joint_name) for joint_name in joint_pair] for joint_pair in mirror_joints
        ])
    cache = getattr(env, key)
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


def joint_pos_penalty(
    env: ManagerBasedRlEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    stand_still_scale: float,
    velocity_threshold: float,
    command_threshold: float,
) -> torch.Tensor:
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


def feet_contact_without_cmd(
    env: ManagerBasedRlEnv,
    command_name: str,
    sensor_cfg: SceneEntityCfg,
) -> torch.Tensor:
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    contact = contact_sensor.compute_first_contact(env.step_dt)[:, sensor_cfg.body_ids]
    reward = torch.sum(contact, dim=-1).float()
    reward *= torch.linalg.vector_norm(env.command_manager.get_command(command_name), dim=1) < 0.5
    return reward


def feet_slide(
    env: ManagerBasedRlEnv, sensor_cfg: SceneEntityCfg, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    contacts = contact_sensor.data.force[:, sensor_cfg.body_ids, :].norm(dim=-1) > 1.0
    asset: Entity = env.scene[asset_cfg.name]
    feet_vel = asset.data.body_lin_vel_w[:, asset_cfg.body_ids, :2]
    return torch.sum(torch.norm(feet_vel, dim=-1) * contacts, dim=1)


def foot_impact_velocity(
    env: ManagerBasedRlEnv,
    sensor_cfg: SceneEntityCfg,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    speed_threshold: float = 0.10,
) -> torch.Tensor:
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    asset: Entity = env.scene[asset_cfg.name]
    first_contact = contact_sensor.compute_first_contact(env.step_dt)[:, sensor_cfg.body_ids].float()
    foot_lin_vel = asset.data.body_lin_vel_w[:, asset_cfg.body_ids, :]
    downward_speed = torch.clamp(-foot_lin_vel[:, :, 2], min=0.0)
    downward_speed = torch.clamp(downward_speed - speed_threshold, min=0.0)
    return torch.sum(first_contact * torch.square(downward_speed), dim=1) * get_gait_level_tensor(env)


def feet_air_time_lin_xy_cmd(
    env: ManagerBasedRlEnv,
    command_name: str,
    sensor_cfg: SceneEntityCfg,
    threshold: float,
    cmd_threshold: float = 0.1,
) -> torch.Tensor:
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    first_contact = contact_sensor.compute_first_contact(env.step_dt)[:, sensor_cfg.body_ids]
    last_air_time = contact_sensor.data.last_air_time[:, sensor_cfg.body_ids]
    reward = torch.sum((last_air_time - threshold) * first_contact, dim=1)
    cmd_lin_xy = torch.norm(env.command_manager.get_command(command_name)[:, :2], dim=1)
    reward *= cmd_lin_xy > cmd_threshold
    return reward * get_gait_level_tensor(env)


def feet_air_time_ang_z_cmd_lite3(
    env: ManagerBasedRlEnv,
    command_name: str,
    sensor_cfg: SceneEntityCfg,
    threshold: float,
    cmd_threshold: float = 0.1,
) -> torch.Tensor:
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    first_contact = contact_sensor.compute_first_contact(env.step_dt)[:, sensor_cfg.body_ids]
    last_air_time = contact_sensor.data.last_air_time[:, sensor_cfg.body_ids]
    reward = torch.sum((last_air_time - threshold) * first_contact, dim=1)
    cmd_ang_z = torch.abs(env.command_manager.get_command(command_name)[:, 2])
    reward *= cmd_ang_z > cmd_threshold
    return reward * get_gait_level_tensor(env)


def stand_still_joint_deviation_l1(
    env: ManagerBasedRlEnv,
    command_name: str,
    command_threshold: float = 0.1,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    command = env.command_manager.get_command(command_name)
    asset: Entity = env.scene[asset_cfg.name]
    angle = asset.data.joint_pos[:, asset_cfg.joint_ids] - asset.data.default_joint_pos[:, asset_cfg.joint_ids]
    return torch.sum(torch.abs(angle), dim=1) * (torch.norm(command, dim=1) < command_threshold)


##
# Base-motion penalties (mjlab 1.6 lacks these variants).
##


def lin_vel_z_l2(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset = env.scene[asset_cfg.name]
    return torch.square(asset.data.root_link_lin_vel_b[:, 2])


def ang_vel_xy_l2(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset = env.scene[asset_cfg.name]
    return torch.sum(torch.square(asset.data.root_link_ang_vel_b[:, :2]), dim=1)


def flat_orientation_l2(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset = env.scene[asset_cfg.name]
    return torch.sum(torch.square(asset.data.projected_gravity_b[:, :2]), dim=1)


def base_height_l2(
    env: ManagerBasedRlEnv,
    target_height: float,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    asset = env.scene[asset_cfg.name]
    return torch.square(asset.data.root_link_pos_w[:, 2] - target_height)


def undesired_contacts(
    env: ManagerBasedRlEnv, threshold: float, sensor_cfg: SceneEntityCfg
) -> torch.Tensor:
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    contact = contact_sensor.data.force[:, sensor_cfg.body_ids, :]
    return torch.sum(
        torch.max(torch.norm(contact, dim=-1) - threshold, torch.tensor(0.0, device=env.device)),
        dim=1,
    )


def contact_forces(
    env: ManagerBasedRlEnv, threshold: float, sensor_cfg: SceneEntityCfg
) -> torch.Tensor:
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    contact = contact_sensor.data.force[:, sensor_cfg.body_ids, :]
    norm = torch.linalg.vector_norm(contact, dim=-1)
    return torch.sum(torch.square(torch.clamp(norm - threshold, min=0.0)), dim=1)


##
# Termination
##


def bad_orientation_2(
    env: ManagerBasedRlEnv,
    limit_angle: float,
    gravity_xy_limit: float = 0.7,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Terminate on roll/pitch beyond limit OR strong tilt (gravity_xy)."""
    asset = env.scene[asset_cfg.name]
    gravity = asset.data.projected_gravity_b
    roll_pitch_bad = torch.norm(gravity[:, :2], dim=1) > limit_angle
    strong_tilt = torch.norm(gravity[:, :2], dim=1) > gravity_xy_limit
    combined = roll_pitch_bad | strong_tilt
    gravity_z_bad = gravity[:, 2] > 0.0
    return (combined | gravity_z_bad).float()
