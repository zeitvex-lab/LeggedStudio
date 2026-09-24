"""族级技能的接触/步态原语与"关节序、足端"解析。

来源：`go2_skills/shared/contacts.py` 与 `.../jump/mdp/observations.py` 的公共段。

**与源实现的差异只有三处**（都是"把机型常量换成声明驱动的解析"）：

1. `joint_ids(env)`：源实现写死 12 个 go2 关节名；这里**从动作项取名序**——
   动作项的目标名由机型绑定按契约 `action.joint_order`（`preserve_order=True`）建立，
   于是"观测/奖励里的关节序"与"策略动作维"是同一个序（见 `skills/__init__` 说明）；
2. 足端接触：源实现按写死的 `FL/FR/RL/RR_foot_collision` 重排 sensor 槽位；这里直接用
   足端传感器自己的槽位顺序 —— 该顺序由绑定按契约 `leg_ids` 传入（四足族 = FL/FR/RL/RR），
   对 go2 与源实现**逐位相同**，且不再需要技能层知道任何几何名；
3. 足端高度：源实现写死 `find_sites(("FL","FR","RL","RR"))`；这里站点优先、几何回退
   （go1 没有足端 site）。
"""

from __future__ import annotations

import math

import torch
from mjlab.entity import Entity
from mjlab.sensor import ContactSensor
from mjlab.utils.lab_api.math import euler_xyz_from_quat

from .sensors import FEET_SENSOR

#: 族级技能的动作项名（关节序的真值来源）。
ACTION_TERM = "joint_pos"


def joint_names(env) -> tuple[str, ...]:
    """族级技能使用的关节序 = 动作项声明的目标关节名序（= 契约 `action.joint_order`）。"""
    name = ACTION_TERM
    if name not in env.action_manager.active_terms:
        raise RuntimeError(
            f"动作项 {name!r} 不在环境里（实际：{sorted(env.action_manager.active_terms)}）—— "
            "族级技能要求动作项存在：关节序由它声明，观测/奖励据此取序"
        )
    return tuple(env.action_manager.get_term(name).cfg.actuator_names)


def joint_ids_named(robot: Entity, names: tuple[str, ...] | list[str]) -> list[int]:
    """按给定名序解析关节 id；**顺序即布局**，缺名即报错（不静默错位）。"""
    ids, resolved = robot.find_joints(names, preserve_order=True)
    if tuple(resolved) != tuple(names):
        raise RuntimeError(f"关节序解析不一致：请求 {tuple(names)}，得到 {tuple(resolved)}")
    return ids


def joint_ids(env) -> list[int]:
    """族级技能统一入口：按动作项名序解析关节 id。"""
    return joint_ids_named(env.scene["robot"], joint_names(env))


def source_contact(sensor: ContactSensor, threshold: float) -> torch.Tensor:
    """Contacts in the sensor's own slot order (= 绑定按契约腿序传入的顺序)."""
    force = sensor.data.force
    assert force is not None
    return torch.linalg.vector_norm(force, dim=-1) > threshold


def source_vertical_contact(sensor: ContactSensor, threshold: float) -> torch.Tensor:
    """Isaac Gym-equivalent upward foot force from mjlab's opposite-signed wrench.

    With the foot as primary and terrain as secondary, mjlab reports the
    primary-to-secondary wrench: supporting ground contact therefore has
    negative world Z. Isaac Gym's rigid-body force uses the opposite sign.
    """
    force = sensor.data.force
    assert force is not None
    return -force[:, :, 2] > threshold


def foot_legs(env, sensor_name: str = FEET_SENSOR) -> tuple[str, ...]:
    """足端顺序里的腿标记（从足端传感器的 primary 名里取，不写死机型）。"""
    sensor = env.scene[sensor_name]
    return tuple(str(name).split("_")[0] for name in sensor.primary_names)


def foot_heights(env, sensor_name: str = FEET_SENSOR) -> torch.Tensor:
    """各足端的世界系 z（站点优先，退化到足端几何）。

    站点优先：足端 site 与足端几何同腿前缀时用它（go2 的 FL/FR/RL/RR；
    源实现同样用 site）。没有足端 site 的机型（go1）回退到足端几何自身位姿 ——
    足端几何按定义就在足端，语义与 site 同族，且**不需要改 MJCF**。
    """
    robot: Entity = env.scene["robot"]
    legs = foot_legs(env, sensor_name)
    site_ids: list[int] = []
    for leg in legs:
        try:
            ids, resolved = robot.find_sites((leg,), preserve_order=True)
        except ValueError:
            site_ids = []
            break
        if len(ids) != 1 or resolved[0] != leg:
            site_ids = []
            break
        site_ids.append(ids[0])
    if site_ids:
        return robot.data.site_pos_w[:, site_ids, 2]
    sensor = env.scene[sensor_name]
    geom_ids, resolved = robot.find_geoms(tuple(sensor.primary_names), preserve_order=True)
    if tuple(resolved) != tuple(sensor.primary_names):
        raise RuntimeError(
            f"足端几何在实体上解析不一致：传感器 {tuple(sensor.primary_names)} vs 实体 {tuple(resolved)}"
        )
    return robot.data.geom_pose_w[:, geom_ids, 2]


def phase(env, cycle_time: float) -> torch.Tensor:
    return torch.remainder(env.episode_length_buf * env.step_dt, cycle_time) / cycle_time


def stance_mask(env, cycle_time: float) -> torch.Tensor:
    gait_phase = phase(env, cycle_time)
    return torch.stack((gait_phase < 0.5, gait_phase > 0.5), dim=1).float()


def root_euler(robot: Entity) -> torch.Tensor:
    return torch.stack(euler_xyz_from_quat(robot.data.root_link_quat_w), dim=1)


def phase_command(env, command_name: str, cycle_time: float) -> torch.Tensor:
    command = env.command_manager.get_command(command_name)
    assert command is not None
    gait_phase = phase(env, cycle_time)
    return torch.cat(
        (
            torch.sin(2.0 * math.pi * gait_phase).unsqueeze(1),
            torch.cos(2.0 * math.pi * gait_phase).unsqueeze(1),
            command[:, :2] * 2.0,
            command[:, 2:3] * 0.25,
        ),
        dim=1,
    )
