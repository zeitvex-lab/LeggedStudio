"""Periodic Reward Framework (Walk-These-Ways style) MDP terms for Go2.

Ported from LeggedGym-Ex ``legged_gym/envs/go2/go2_wtw/go2_wtw.py``
(BSD-3-Clause).  A global gait phase ``phi`` advances every control step;
per-leg offsets ``theta`` select the gait pattern (trot / pronk / pace /
bound, resampled on reset); each leg's swing/stance expectation is a
step indicator over ``(phi + theta) % 1`` that penalizes foot speed while
swinging and foot contact force while in stance.

All state lives on the env instance (created lazily on first use) so the
terms stay stateless functions per the mjlab reward-term contract.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from typing import TYPE_CHECKING

from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

_THETA_TABLE = {
    # gait: (theta_fl, theta_fr, theta_rl, theta_rr)
    "trot": (0.0, 0.5, 0.5, 0.0),
    "pronk": (0.0, 0.0, 0.0, 0.0),
    "pace": (0.5, 0.5, 0.0, 0.0),
    "bound": (0.0, 0.5, 0.5, 0.5),
}
_THETA_LISTS = {
    # theta lists as in the source go2_wtw config (per-env resample pool)
    "fl": [0.0, 0.0, 0.5, 0.0],
    "fr": [0.5, 0.0, 0.0, 0.0],
    "rl": [0.5, 0.0, 0.5, 0.5],
    "rr": [0.0, 0.0, 0.0, 0.5],
}



@dataclass(frozen=True)
class ContactSensorRef:
    """Reference to a scene contact sensor: name plus sensor-data columns."""

    name: str
    body_ids: tuple | None = None


def _cols(sensor_cfg: ContactSensorRef):
    return slice(None) if sensor_cfg.body_ids is None else sensor_cfg.body_ids



def _state(env: ManagerBasedRlEnv):
    state = getattr(env, "_wtw_state", None)
    if state is None:
        state = {
            "phi": torch.zeros(env.num_envs, 1, device=env.device),
            "gait_time": torch.zeros(env.num_envs, 1, device=env.device),
            "theta": torch.zeros(env.num_envs, 4, device=env.device),
            "clock": torch.zeros(env.num_envs, 8, device=env.device),
            "gait_period": torch.full((env.num_envs, 1), 0.45, device=env.device),
            "foot_clearance_target": torch.full((env.num_envs, 1), 0.08, device=env.device),
            "base_height_target": torch.full((env.num_envs, 1), 0.27, device=env.device),
            "pitch_target": torch.zeros(env.num_envs, 1, device=env.device),
            "num_gaits": 1,
        }
        env._wtw_state = state
    return state


def resample_behavior_params(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    gait_period_range: tuple[float, float] = (0.3, 0.6),
    foot_clearance_range: tuple[float, float] = (0.04, 0.12),
    base_height_range: tuple[float, float] = (0.2, 0.34),
    pitch_range: tuple[float, float] = (-0.3, 0.3),
) -> None:
    """Resample theta (gait pattern) and behavior params for reset envs."""
    state = _state(env)
    lists = [_THETA_LISTS["fl"], _THETA_LISTS["fr"], _THETA_LISTS["rl"], _THETA_LISTS["rr"]]
    num_gaits = max(1, min(state["num_gaits"], len(lists[0])))
    idx = torch.randint(0, num_gaits, (len(env_ids),))
    for i, leg in enumerate(("fl", "fr", "rl", "rr")):
        values = torch.tensor([lists[i][k] for k in idx.tolist()], device=env.device)
        state["theta"][env_ids, i] = values
    state["gait_period"][env_ids] = torch.empty(len(env_ids), 1, device=env.device).uniform_(*gait_period_range)
    state["foot_clearance_target"][env_ids] = torch.empty(len(env_ids), 1, device=env.device).uniform_(*foot_clearance_range)
    state["base_height_target"][env_ids] = torch.empty(len(env_ids), 1, device=env.device).uniform_(*base_height_range)
    state["pitch_target"][env_ids] = torch.empty(len(env_ids), 1, device=env.device).uniform_(*pitch_range)
    # pronk / bound gait identification (all-zero / half-zero theta rows)
    pronk = (state["theta"][env_ids] == 0.0).all(dim=1)
    bound = (state["theta"][env_ids, 0] == 0.0) & (state["theta"][env_ids, 1] == 0.0) & (
        state["theta"][env_ids, 2] == 0.5) & (state["theta"][env_ids, 3] == 0.5)
    if pronk.any():
        state["gait_time"][env_ids[pronk]] = 0.0


def advance_phase(env: ManagerBasedRlEnv, dt: float) -> None:
    """Advance the gait phase after reward computation (call once per step)."""
    state = _state(env)
    state["gait_time"] += dt
    over = state["gait_time"] >= (state["gait_period"] - dt / 2)
    state["gait_time"][over] = 0.0
    state["phi"] = state["gait_time"] / state["gait_period"]
    _calc_clock(env)


def _calc_clock(env: ManagerBasedRlEnv) -> None:
    state = _state(env)
    for i in range(4):
        phase = state["phi"] + state["theta"][:, i].unsqueeze(1)
        state["clock"][:, i] = torch.sin(2 * torch.pi * phase).squeeze(-1)
        state["clock"][:, i + 4] = torch.cos(2 * torch.pi * phase).squeeze(-1)


##
# Observations
##


def clock_observation(env: ManagerBasedRlEnv, dt: float = 0.02) -> torch.Tensor:
    """8-dim sin/cos gait clock (4 legs x [sin, cos]).

    Advances the phase as a side effect: the source advances phi after
    reward computation and before observation recalculation, and mjlab
    computes observations after rewards, giving the same ordering.
    """
    advance_phase(env, dt)
    _calc_clock(env)
    return _state(env)["clock"].clone()


def behavior_params_observation(env: ManagerBasedRlEnv) -> torch.Tensor:
    """4-dim behavior parameters: gait_period, base_height, foot_clearance, pitch."""
    state = _state(env)
    return torch.cat([
        state["gait_period"],
        state["base_height_target"],
        state["foot_clearance_target"],
        state["pitch_target"],
    ], dim=1)


def theta_observation(env: ManagerBasedRlEnv) -> torch.Tensor:
    """4-dim per-leg gait offsets."""
    return _state(env)["theta"].clone()


##
# Rewards
##


def _feet_state(env: ManagerBasedRlEnv, sensor_cfg: SceneEntityCfg, asset_cfg: SceneEntityCfg):
    asset: Entity = env.scene[asset_cfg.name]
    sensor = env.scene.sensors[sensor_cfg.name]
    force = sensor.data.force[:, _cols(sensor_cfg), :]
    feet_force_norm = torch.norm(force, dim=-1)
    feet_vel = asset.data.body_link_lin_vel_w[:, asset_cfg.body_ids, :]
    feet_vel_norm = torch.norm(feet_vel, dim=-1)
    return feet_force_norm, feet_vel_norm


def _uniped_periodic_gait(
    env: ManagerBasedRlEnv,
    state: dict,
    leg_idx: int,
    feet_force_norm: torch.Tensor,
    feet_vel_norm: torch.Tensor,
    a_swing: float,
    b_swing: float,
):
    phi = (state["phi"] + state["theta"][:, leg_idx].unsqueeze(1)) % 1.0 * 2 * torch.pi
    exp_c_frc = torch.zeros(env.num_envs, 1, device=env.device)
    exp_c_spd = torch.zeros(env.num_envs, 1, device=env.device)
    swing = (phi >= a_swing) & (phi < b_swing)
    stance = (phi >= b_swing) & (phi < 2 * torch.pi)
    exp_c_frc[swing] = -1.0
    exp_c_spd[swing] = 0.0
    exp_c_frc[stance] = 0.0
    exp_c_spd[stance] = -1.0
    quad = exp_c_spd * feet_vel_norm[:, leg_idx].unsqueeze(1) + exp_c_frc * feet_force_norm[:, leg_idx].unsqueeze(1)
    return quad, exp_c_spd, exp_c_frc


def quad_periodic_gait(
    env: ManagerBasedRlEnv,
    sensor_cfg: SceneEntityCfg,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    a_swing: float = 0.0,
    b_swing: float = 0.5,
) -> torch.Tensor:
    """exp(sum_leg expected_C_spd * foot_speed + expected_C_frc * foot_force)."""
    state = _state(env)
    feet_force_norm, feet_vel_norm = _feet_state(env, sensor_cfg, asset_cfg)
    total = torch.zeros(env.num_envs, device=env.device)
    for leg_idx in range(4):
        quad, _, _ = _uniped_periodic_gait(env, state, leg_idx, feet_force_norm, feet_vel_norm, a_swing, b_swing)
        total = total + quad.flatten()
    return torch.exp(total)


def tracking_base_height(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    sigma: float = 0.01,
) -> torch.Tensor:
    state = _state(env)
    base_height = env.scene[asset_cfg.name].data.root_link_pos_w[:, 2]
    return torch.exp(-torch.square(base_height - state["base_height_target"].squeeze(1)) / sigma)


def tracking_orientation(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    sigma: float = 0.1,
) -> torch.Tensor:
    state = _state(env)
    gravity = env.scene[asset_cfg.name].data.projected_gravity_b
    roll_error = torch.square(gravity[:, 1])  # roll via gravity y
    pitch_error = torch.square(gravity[:, 0] - state["pitch_target"].squeeze(1) * -1.0)
    return torch.exp(-(roll_error + pitch_error) / sigma)


def tracking_foot_clearance(
    env: ManagerBasedRlEnv,
    sensor_cfg: SceneEntityCfg,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    sigma: float = 0.01,
    foot_height_offset: float = 0.022,
) -> torch.Tensor:
    """Swing-phase foot height tracking with horizontal-velocity weighting."""
    del sensor_cfg
    state = _state(env)
    asset: Entity = env.scene[asset_cfg.name]
    foot_vel_xy = torch.norm(asset.data.body_link_lin_vel_w[:, asset_cfg.body_ids, :2], dim=-1)
    clearance_error = torch.sum(
        foot_vel_xy
        * torch.square(asset.data.body_link_pos_w[:, asset_cfg.body_ids, 2] - state["foot_clearance_target"] - foot_height_offset),
        dim=-1,
    )
    return torch.exp(-clearance_error / sigma)


def hip_pos(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset: Entity = env.scene[asset_cfg.name]
    hip_ids = [i for i in range(asset.num_joints) if "hip" in (
        asset.joint_names[i] if hasattr(asset, "joint_names") else "")]
    if not hip_ids:
        return torch.zeros(env.num_envs, device=env.device)
    return torch.sum(
        torch.square(asset.data.joint_pos[:, hip_ids] - asset.data.default_joint_pos[:, hip_ids]), dim=-1
    )


##
# Standard penalties (mjlab envs.mdp lacks a few of these shapes).
##


def lin_vel_z_l2(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset: Entity = env.scene[asset_cfg.name]
    return torch.square(asset.data.root_link_lin_vel_b[:, 2])


def ang_vel_xy_l2(env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset: Entity = env.scene[asset_cfg.name]
    return torch.sum(torch.square(asset.data.root_link_ang_vel_b[:, :2]), dim=1)


def action_smoothness(env: ManagerBasedRlEnv) -> torch.Tensor:
    """Second-order action difference (a - 2a' + a'')."""
    prev = getattr(env, "_wtw_prev_action", None)
    prev2 = getattr(env, "_wtw_prev2_action", None)
    action = env.action_manager.action
    if prev is None or prev2 is None:
        env._wtw_prev2_action = action.clone()
        env._wtw_prev_action = action.clone()
        return torch.zeros(env.num_envs, device=env.device)
    smooth = torch.sum(torch.square(action - 2 * prev + prev2), dim=1)
    env._wtw_prev2_action.copy_(prev)
    env._wtw_prev_action.copy_(action)
    return smooth


def foot_landing_vel(
    env: ManagerBasedRlEnv,
    sensor_cfg: SceneEntityCfg,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    vel_threshold: float = 0.0,
) -> torch.Tensor:
    """Penalize vertical foot velocity while about to land (low height, descending, no contact)."""
    asset: Entity = env.scene[asset_cfg.name]
    sensor = env.scene.sensors[sensor_cfg.name]
    force = sensor.data.force[:, _cols(sensor_cfg), :]
    in_contact = force.norm(dim=-1) > 1.0
    foot_vel_z = asset.data.body_link_lin_vel_w[:, asset_cfg.body_ids, 2]
    descending = foot_vel_z < vel_threshold
    return torch.sum(torch.square(foot_vel_z) * (~in_contact) * descending, dim=1)


def undesired_contacts(
    env: ManagerBasedRlEnv, threshold: float, sensor_cfg: SceneEntityCfg
) -> torch.Tensor:
    """Penalize contact on non-foot bodies above a force threshold."""
    sensor = env.scene.sensors[sensor_cfg.name]
    force = sensor.data.force[:, _cols(sensor_cfg), :]
    return torch.sum(
        torch.max(torch.norm(force, dim=-1) - threshold, torch.tensor(0.0, device=env.device)),
        dim=1,
    )
