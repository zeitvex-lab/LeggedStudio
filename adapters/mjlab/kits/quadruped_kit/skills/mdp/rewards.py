"""族级技能的奖励原语。

来源：`assets/robots/unitree_go2/training/source/local_tasks/robots/unitree/go2/mdp/rewards.py`
的 `go2_dof_power_penalty`（逐字上移，只去掉机型名与机型侧的标定文案）。**不含机型常量**：
`asset_cfg` 由调用方传入（默认场景实体 `robot`），核函数与量纲是族级机制。

为什么是族级机制而不是机型配方：功率 `|tau*v|` 的量纲与"执行器 1:1 驱动关节"的索引约定
是 mjlab 实体层的通用口径（`asset.data.actuator_force * asset.data.joint_vel`），
与评测侧 `adapters/mjlab/quality_metrics.py::dof_power` 同一量纲；**权重**才是任务数值
（由各技能 profile 携带）。

第二段（`# --- 速度跟踪的算法变体核 ---` 起）来源：同一文件里**被 CTS/AMP-CTS/TS/AMP-TS/
TS-学生/HIM/DreamWaQ/AMP-DreamWaQ 八个变体消费**的核（源 LeggedRobot 奖励表）。
去机型化改动：`asset_cfg` 里的关节/几何/body 名一律由调用方从绑定派生（见
`skills/velocity/variants.py`）；核函数本身只有量纲与阈值参数。
"""

from __future__ import annotations

import torch
from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactSensor
from mjlab.sensor.raycast_sensor import RayCastSensor
from mjlab.utils.lab_api.math import quat_apply_inverse

from .sensors import FEET_SENSOR, TERRAIN_SCAN

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def stand_still_penalty(
    env,
    command_name: str,
    command_threshold: float = 0.1,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """命令非零时罚"保持默认姿不动"（lainlab trot 同款；2026-09-28 根因修复引入）。

    背景：速度任务的奖励经济学里，若站着也能从 track 核（exp 松 σ）+ pose/upright
    拿到与走路相当的分，且没有"命令非零却不许站着"的显式罚，"站得住不走"就是
    优势策略（自产 go2/go2w 产物 motion=0.003 实证，见
    `tools/baselines/reward_shaping_experiments.json#v3`）。本项在命令幅值 >
    阈值时按关节与默认姿的绝对偏差之和惩罚，把站着变成亏本策略；命令为零
    （真站立，`rel_standing_envs` 那部分环境）时不罚，站立能力不受影响。
    """
    asset: Entity = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)
    assert command is not None, f"Command '{command_name}' not found."
    magnitude = torch.norm(command[:, :2], dim=1) + torch.abs(command[:, 2])
    deviation = (
        asset.data.joint_pos[:, asset_cfg.joint_ids]
        - asset.data.default_joint_pos[:, asset_cfg.joint_ids]
    ).abs().sum(dim=1)
    return deviation * (magnitude > command_threshold).float()


def dof_power_penalty(
    env,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    kernel: str = "mean_abs",
) -> torch.Tensor:
    """Per-joint mechanical power |tau*v| penalty, aligned with the quality metric.

    口径与评测侧一致：功率 = ``|actuator_force * joint_vel|``（执行器与关节 1:1 同序）。
    kernel：
    * ``mean_abs``（逐关节 |tau*v| 均值，权重可读性好，默认）；
    * ``mean_square`` / ``rms`` 备查。
    """
    asset: Entity = env.scene[asset_cfg.name]
    force = asset.data.actuator_force[:, asset_cfg.joint_ids]
    velocity = asset.data.joint_vel[:, asset_cfg.joint_ids]
    power = (force * velocity).abs()
    if kernel == "mean_square":
        return torch.mean(torch.square(power), dim=-1)
    if kernel == "rms":
        return torch.sqrt(torch.mean(torch.square(power), dim=-1) + 1e-6)
    return torch.mean(power, dim=-1)


# ---------------------------------------------------------------------------
# 速度跟踪的算法变体核（来源：包内 `...go2/mdp/rewards.py` 的对应函数）
#
# 这段只服务 `skills/velocity/variants.py` 的八个算法变体。除按需要把 `asset_cfg` /
# 传感器名参数化（关节与几何名由绑定派生）外，核函数逐字保留源实现。
# ---------------------------------------------------------------------------


def source_tracking_linear_velocity(
    env,
    command_name: str = "twist",
    sigma: float = 0.25,
    trot_gate: bool = False,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """源跟踪核：只对**指令平面速度**取指数误差。"""
    asset: Entity = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)
    assert command is not None
    error = torch.sum(
        torch.square(command[:, :2] - asset.data.root_link_lin_vel_b[:, :2]), dim=-1
    )
    reward = torch.exp(-error / sigma)
    if trot_gate:
        ready = getattr(env, "_source_trot_ready", None)
        if ready is None:
            ready = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
        reward = reward * ready.to(reward.dtype)
    return reward


def source_tracking_angular_velocity(
    env,
    command_name: str = "twist",
    sigma: float = 0.25,
    trot_gate: bool = False,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """源跟踪核：只对**偏航角速度**取指数误差。"""
    asset: Entity = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)
    assert command is not None
    error = torch.square(command[:, 2] - asset.data.root_link_ang_vel_b[:, 2])
    reward = torch.exp(-error / sigma)
    if trot_gate:
        ready = getattr(env, "_source_trot_ready", None)
        if ready is None:
            ready = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
        reward = reward * ready.to(reward.dtype)
    return reward


def collision_penalty(env, sensor_names: tuple[str, ...]) -> torch.Tensor:
    """把非足端接触聚合成源实现的**计数**型项（力超 0.1 计一次）。"""
    penalty = torch.zeros(env.num_envs, device=env.device)
    for sensor_name in sensor_names:
        sensor: ContactSensor = env.scene[sensor_name]
        force = sensor.data.force
        if force is not None:
            if force.shape[-1] != 3:
                raise ValueError(
                    f"{sensor_name} force must end in XYZ, got {tuple(force.shape)}"
                )
            penalty = penalty + (torch.linalg.vector_norm(force, dim=-1) > 0.1).to(
                torch.float32
            ).reshape(env.num_envs, -1).sum(dim=-1)
            continue
        found = sensor.data.found
        assert found is not None
        penalty = penalty + found.to(torch.float32).reshape(env.num_envs, -1).sum(dim=-1)
    return penalty


def linear_velocity_z_penalty(
    env,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """源步态奖励里的竖直基座速度平方惩罚。"""
    asset: Entity = env.scene[asset_cfg.name]
    return torch.square(asset.data.root_link_lin_vel_b[:, 2])


def angular_velocity_xy_penalty(
    env,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """源奖励里的滚转/俯仰角速度平方惩罚。"""
    asset: Entity = env.scene[asset_cfg.name]
    return torch.sum(torch.square(asset.data.root_link_ang_vel_b[:, :2]), dim=-1)


def orientation_penalty(
    env,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """源 rough 任务的投影重力倾斜平方惩罚。"""
    asset: Entity = env.scene[asset_cfg.name]
    return torch.sum(torch.square(asset.data.projected_gravity_b[:, :2]), dim=-1)


def base_height_penalty(
    env,
    target_height: float = 0.4,
    sensor_name: str = TERRAIN_SCAN,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """按射线地形跟踪基座高度（与 Isaac Gym 同口径）。"""
    asset: Entity = env.scene[asset_cfg.name]
    root_z = asset.data.root_link_pos_w[:, 2]
    try:
        sensor = env.scene[sensor_name]
    except KeyError:
        sensor = None
    if isinstance(sensor, RayCastSensor):
        hit_z = sensor.data.hit_pos_w[..., 2]
        distances = sensor.data.distances
        valid_hit_z = torch.where(distances < 0.0, root_z.unsqueeze(-1), hit_z)
        local_height = root_z - valid_hit_z.mean(dim=-1)
    else:
        local_height = root_z - env.scene.env_origins[:, 2]
    return torch.square(local_height - target_height)


def joint_acceleration_penalty(
    env,
    divide_by_dt: bool = True,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """源有限差分关节速度惩罚。

    Isaac Gym 保存的是上一个策略步的速度，并按策略 ``dt`` 求差。源里只有一个特技
    任务刻意省略该除法（由调用方传 ``divide_by_dt=False``）。
    """
    asset: Entity = env.scene[asset_cfg.name]
    current = asset.data.joint_vel[:, asset_cfg.joint_ids]
    previous = getattr(env, "_source_previous_joint_velocity", None)
    if previous is None or previous.shape != current.shape:
        previous = torch.zeros_like(current)
    # The source explicitly clears ``last_dof_vel`` during every environment
    # reset.  At the first post-reset reward step, reproduce that zero state.
    first_step = env.episode_length_buf <= 1
    previous = torch.where(first_step.unsqueeze(-1), torch.zeros_like(previous), previous)
    delta = previous - current
    env.__dict__["_source_previous_joint_velocity"] = current.clone()
    if divide_by_dt:
        delta = delta / env.step_dt
    return torch.sum(torch.square(delta), dim=-1)


def action_smoothness_penalty(env) -> torch.Tensor:
    """源 runner 的二阶原始动作平滑惩罚。"""
    action = env.action_manager.action
    previous = env.action_manager.prev_action
    previous_previous = env.action_manager.prev_prev_action
    acceleration = action - 2.0 * previous + previous_previous
    return torch.sum(torch.square(acceleration), dim=-1)


def stumble_penalty(
    env,
    sensor_name: str = FEET_SENSOR,
    horizontal_ratio: float = 5.0,
) -> torch.Tensor:
    """足端踢到近竖直面（水平接触力 > 5 倍竖直力）的检测。"""
    sensor: ContactSensor = env.scene[sensor_name]
    force = sensor.data.force
    if force is None:
        return torch.zeros(env.num_envs, device=env.device)
    if force.ndim != 3 or force.shape[-1] != 3:
        raise ValueError(
            f"{sensor_name} force must have shape [B, feet, 3], got {tuple(force.shape)}"
        )
    horizontal = torch.linalg.vector_norm(force[..., :2], dim=-1)
    vertical = force[..., 2].abs()
    return (horizontal > horizontal_ratio * vertical).any(dim=-1).to(force.dtype)


def reward_contact_mask(
    sensor: ContactSensor,
    threshold: float,
    vertical_only: bool = False,
) -> torch.Tensor:
    """源口径的足端接触位（优先用测得的力字段，退化到 found）。"""
    force = sensor.data.force
    if force is not None:
        if force.ndim != 3 or force.shape[-1] != 3:
            raise ValueError(f"Contact force must be [B, feet, 3], got {tuple(force.shape)}")
        magnitude = (
            force[..., 2].abs() if vertical_only else torch.linalg.vector_norm(force, dim=-1)
        )
        return magnitude > threshold
    found = sensor.data.found
    if found is None:
        raise ValueError("ContactSensor must expose either force or found fields")
    return found > 0


def source_feet_air_time_reward(
    env,
    sensor_name: str = FEET_SENSOR,
    offset: float = 0.5,
    command_name: str = "twist",
    command_dimensions: int = 3,
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """复现源"首次落地"腾空时间累加器。

    通用 mjlab 项在有界腾空区间内**每帧**给奖励；源只在首个滤波后的落地帧给
    ``air_time - offset``，用竖直力阈值与一帧接触历史判定。
    """
    sensor: ContactSensor = env.scene[sensor_name]
    contact = reward_contact_mask(
        sensor, threshold=contact_threshold, vertical_only=True
    )
    air_time = getattr(env, "_source_feet_air_time", None)
    last_contact = getattr(env, "_source_last_foot_contact", None)
    if air_time is None or air_time.shape != contact.shape:
        air_time = torch.zeros_like(contact, dtype=torch.float32)
    if last_contact is None or last_contact.shape != contact.shape:
        last_contact = torch.zeros_like(contact)
    first_step = env.episode_length_buf <= 1
    air_time = torch.where(first_step.unsqueeze(-1), torch.zeros_like(air_time), air_time)
    last_contact = torch.where(
        first_step.unsqueeze(-1), torch.zeros_like(last_contact), last_contact
    )
    contact_filtered = contact | last_contact
    first_contact = (air_time > 0.0) & contact_filtered
    air_time = air_time + env.step_dt
    reward = ((air_time - offset) * first_contact.to(air_time.dtype)).sum(dim=-1)
    command = env.command_manager.get_command(command_name)
    assert command is not None
    moving = torch.linalg.vector_norm(command[:, :command_dimensions], dim=-1) > 0.1
    env.__dict__["_source_feet_air_time"] = air_time * (~contact_filtered).to(
        air_time.dtype
    )
    env.__dict__["_source_last_foot_contact"] = contact
    return reward * moving


def source_foot_clearance_penalty(
    env,
    target_height: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """源体坐标系足端高度代价，按足端横向速度加权。"""
    asset: Entity = env.scene[asset_cfg.name]
    positions = asset.data.site_pos_w[:, asset_cfg.site_ids]
    velocities = asset.data.site_lin_vel_w[:, asset_cfg.site_ids]
    num_feet = positions.shape[1]
    quaternion = asset.data.root_link_quat_w[:, None, :].expand(-1, num_feet, -1)
    position_b = quat_apply_inverse(
        quaternion.reshape(-1, 4),
        (positions - asset.data.root_link_pos_w.unsqueeze(1)).reshape(-1, 3),
    ).reshape_as(positions)
    velocity_b = quat_apply_inverse(
        quaternion.reshape(-1, 4),
        (velocities - asset.data.root_link_lin_vel_w.unsqueeze(1)).reshape(-1, 3),
    ).reshape_as(velocities)
    height_error = torch.square(position_b[..., 2] - target_height)
    lateral_speed = torch.linalg.vector_norm(velocity_b[..., :2], dim=-1)
    return torch.sum(height_error * lateral_speed, dim=-1)


def hip_position_squared_penalty(
    env,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """源 CTS 奖励用的**外展关节**偏离默认位平方惩罚。"""
    asset: Entity = env.scene[asset_cfg.name]
    joints = asset.data.joint_pos[:, asset_cfg.joint_ids]
    default = asset.data.default_joint_pos[:, asset_cfg.joint_ids]
    return torch.square(joints - default).sum(dim=-1)


def rear_hip_limit_penalty(
    env,
    limit: float = 0.4,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """源 AMP-DreamWaQ 惩罚：任一后髋关节超出 ``limit`` 即计一次。"""
    asset: Entity = env.scene[asset_cfg.name]
    joints = asset.data.joint_pos[:, asset_cfg.joint_ids]
    return ((joints.abs() > limit).any(dim=-1)).to(torch.float32)
