"""Shared reward-term library for Legged Studio robot packages.

Techniques collected from reference projects (BSD-3-Clause; see
docs/DEEPROBOTICS_PORTING.md for provenance):

- foot_flat            : support-foot orientation level (quaternion based)
- feet_distance_ours   : feet proximity penalty (anti leg-crossing)
- no_fly               : all-feet-off-ground penalty (single-support reward)
- feet_stumble         : lateral-vs-vertical contact force ratio (4:1)
- foot_landing_vel     : descending z-velocity at touchdown (soft landing)
- foot_clearance_swing : swing-phase height tracking weighted by horizontal speed
- feet_air_time_cmd_gated : per-command-component gated air time
- action_smoothness_l2 : second-order action difference

Importable from any training task because ``adapters/mjlab`` is on the
adapter venv's sys.path.  Package-local terms that must survive ZIP export
should stay in the package; use this library for cross-package conventions.
"""

from __future__ import annotations

import torch

from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg


def foot_flat(
    env,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    sigma: float = 0.1,
) -> torch.Tensor:
    """Reward the stance foot keeping its sole level to the world (exp kernel).

    Uses the foot body's world-z axis expressed in body frame via its rotation
    quaternion: flat means the body z axis aligns with world z.
    """
    asset: Entity = env.scene[asset_cfg.name]
    # mjlab 1.6: link-frame attributes are prefixed body_link_* (body_quat_w
    # was the pre-1.6 name).
    quat = asset.data.body_link_quat_w[:, asset_cfg.body_ids, :]
    w = quat[..., 0]
    x = quat[..., 1]
    y = quat[..., 2]
    z = quat[..., 3]
    # world z expressed in body frame z component: 1 - 2(x^2 + y^2)
    world_z_in_body_z = 1.0 - 2.0 * (x * x + y * y)
    return torch.exp(-torch.sum(torch.square(world_z_in_body_z - 1.0), dim=-1) / sigma)


def feet_distance_ours(
    env,
    sensor_cfg: SceneEntityCfg = None,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    min_dist: float = 0.1,
    max_dist: float | None = None,
    weight: float = 100.0,
) -> torch.Tensor:
    """Penalize feet too close together (anti leg-crossing, biped focused)."""
    asset: Entity = env.scene[asset_cfg.name]
    if asset_cfg.body_ids is None or len(asset_cfg.body_ids) < 2:
        return torch.zeros(env.num_envs, device=env.device)
    pos = asset.data.body_link_pos_w[:, asset_cfg.body_ids, :2]
    dist = torch.norm(pos[:, 0] - pos[:, 1], dim=-1)
    penalty = torch.clamp(min_dist - dist, min=0.0)
    if max_dist is not None:
        penalty = penalty + torch.clamp(dist - max_dist, min=0.0)
    return penalty * weight


def no_fly(
    env,
    sensor_cfg: SceneEntityCfg,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    air_time_threshold: float = 0.3,
) -> torch.Tensor:
    """Reward a foot being in contact when its air time exceeded the threshold.

    Equivalent to penalizing "flying" feet (both feet airborne too long on a
    quadruped, or the swing foot lingering on a biped).
    """
    asset: Entity = env.scene[asset_cfg.name]
    sensor = env.scene.sensors[sensor_cfg.name]
    air_time = sensor.data.current_air_time[:, sensor_cfg.body_ids]
    in_air = air_time > air_time_threshold
    return torch.sum(in_air.float(), dim=1)


def feet_stumble(
    env,
    sensor_cfg: SceneEntityCfg,
    ratio_threshold: float = 4.0,
) -> torch.Tensor:
    """Penalize feet contact where lateral force exceeds 4x the vertical force."""
    sensor = env.scene.sensors[sensor_cfg.name]
    force = sensor.data.force[:, sensor_cfg.body_ids, :]
    xy = torch.norm(force[..., :2], dim=-1)
    z = torch.abs(force[..., 2])
    return torch.sum((xy > ratio_threshold * z).float(), dim=1)


def foot_landing_vel(
    env,
    sensor_cfg: SceneEntityCfg,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    height_threshold: float = 0.05,
) -> torch.Tensor:
    """Penalize descending z-velocity of feet about to land (soft landing)."""
    asset: Entity = env.scene[asset_cfg.name]
    sensor = env.scene.sensors[sensor_cfg.name]
    in_contact = sensor.data.force[:, sensor_cfg.body_ids, :].norm(dim=-1) > 1.0
    height_ok = asset.data.body_link_pos_w[:, asset_cfg.body_ids, 2] < height_threshold
    descending = asset.data.body_link_lin_vel_w[:, asset_cfg.body_ids, 2] < 0.0
    return torch.sum(torch.square(asset.data.body_link_lin_vel_w[:, asset_cfg.body_ids, 2]) * (~in_contact) * height_ok * descending, dim=1)


def foot_clearance_swing(
    env,
    sensor_cfg: SceneEntityCfg,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_height: float = 0.08,
    std: float = 0.05,
) -> torch.Tensor:
    """Swing-phase foot height tracking weighted by horizontal speed."""
    asset: Entity = env.scene[asset_cfg.name]
    sensor = env.scene.sensors[sensor_cfg.name]
    in_contact = sensor.data.force[:, sensor_cfg.body_ids, :].norm(dim=-1) > 1.0
    foot_vel_xy = torch.norm(asset.data.body_link_lin_vel_w[:, asset_cfg.body_ids, :2], dim=-1)
    height_error = torch.square(asset.data.body_link_pos_w[:, asset_cfg.body_ids, 2] - target_height)
    return torch.sum(foot_vel_xy * height_error * (~in_contact).float(), dim=1)


def action_smoothness_l2(env) -> torch.Tensor:
    """Second-order action difference: sum (a - 2a' + a'')^2."""
    action = env.action_manager.action
    prev = getattr(env, "_shared_prev_action", None)
    prev2 = getattr(env, "_shared_prev2_action", None)
    if prev is None or prev2 is None:
        return torch.zeros(env.num_envs, device=env.device)
    return torch.sum(torch.square(action - 2 * prev + prev2), dim=1)
