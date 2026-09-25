"""后空翻的状态机与源奖励方程。

来源：`go2_skills/backflip/mdp/rewards.py`（逐式上移）。去机型化改动：

* `joint_ids` → 族级 `..mdp.contacts`（动作项序）；
* 髋外展列的写死下标 `(0,3,6,9)` → 绑定的角色位置（`role_joint_indices("hip_abduction")`）；
* `reshape(-1,4,3)` 的四腿三关节 → `(-1, legs, roles)`（腿×角色从绑定派生）；
* 镜像腿对下标（写死 `1,3`）→ 技能 profile 的 `mirror_leg_indices`；
* 几何目标（0.6 / 0.35 / 0.2）与速度上限（30）→ 技能 profile；
* 状态机自身的常量（`p = max(8 - steps//1200, 0)/10`、起跳/翻滚的冲量区间、
  阈值 `7` 等）是**算法配方**，就地保留。

四条奖励/终止核按名引用族级传感器（`FEET_SENSOR` / `PENALIZED_SENSOR` / `BASE_SENSOR`）。
"""

from __future__ import annotations

import torch
from mjlab.entity import Entity
from mjlab.managers import RewardTermCfg
from mjlab.utils.lab_api.math import euler_xyz_from_quat

from ..mdp import contacts as shared_contacts


class State:
    """源实现的每环境状态机（flight / landed / 起跳与翻滚尝试）。"""

    def __init__(self, env, *, takeoff_impulse=(2.0, 3.5), rotation_impulse=(2.0, 2.5)) -> None:
        n, device = env.num_envs, env.device
        self.flight = torch.zeros(n, dtype=torch.bool, device=device)
        self.landed = torch.zeros_like(self.flight)
        self.last_contact = torch.zeros((n, 4), dtype=torch.bool, device=device)
        self.max_pitch_rate = torch.zeros(n, device=device)
        self.start_pos = torch.zeros((n, 2), device=device)
        self.up_attempted = torch.zeros_like(self.flight)
        self.rot_attempted = torch.zeros_like(self.flight)
        self.steps = 0
        self.last_step = -1
        self._takeoff_impulse = takeoff_impulse
        self._rotation_impulse = rotation_impulse

    def update(self, env, command_name: str, sensor_name: str) -> None:
        if self.last_step == int(env.common_step_counter):
            return
        self.last_step = int(env.common_step_counter)
        self.steps += 1
        robot: Entity = env.scene["robot"]
        command = env.command_manager.get_command(command_name)
        assert command is not None
        contact = shared_contacts.source_vertical_contact(env.scene[sensor_name], 1.0)
        filtered = contact | self.last_contact
        self.last_contact.copy_(contact)
        self.flight |= ~filtered.any(1) & (command[:, 2] > 0)
        self.landed |= filtered.any(1) & self.flight
        self.max_pitch_rate = torch.maximum(
            self.max_pitch_rate, torch.abs(robot.data.root_link_ang_vel_b[:, 1])
        )
        # 源实现按 _reward_dof_vel 的计数推进辅助冲量概率：p = max(8 - steps//1200, 0)/10。
        p = max(8 - self.steps // 1200, 0) / 10.0
        first = (~self.up_attempted) & (~self.landed) & (command[:, 2] > 0)
        ids = torch.nonzero(
            first & (torch.rand(env.num_envs, device=env.device) < p)
        ).squeeze(1)
        if len(ids):
            velocity = robot.data.root_link_vel_w[ids].clone()
            low, high = self._takeoff_impulse
            velocity[:, 2] += torch.empty(len(ids), device=env.device).uniform_(low, high)
            robot.write_root_link_velocity_to_sim(velocity, env_ids=ids)
        self.up_attempted |= first
        second = self.up_attempted & self.flight & (~self.rot_attempted)
        ids = torch.nonzero(
            second & (torch.rand(env.num_envs, device=env.device) < p)
        ).squeeze(1)
        if len(ids):
            velocity = robot.data.root_link_vel_w[ids].clone()
            low, high = self._rotation_impulse
            velocity[:, 4] += torch.empty(len(ids), device=env.device).uniform_(low, high)
            robot.write_root_link_velocity_to_sim(velocity, env_ids=ids)
        self.rot_attempted |= second

    def reset(self, env, ids=None) -> None:
        if ids is None:
            ids = torch.arange(env.num_envs, device=env.device)
        self.flight[ids] = False
        self.landed[ids] = False
        self.last_contact[ids] = False
        self.max_pitch_rate[ids] = 0.0
        self.up_attempted[ids] = False
        self.rot_attempted[ids] = False
        self.start_pos[ids] = env.scene["robot"].data.root_link_pos_w[ids, :2]


def state(env) -> State:
    current = getattr(env, "_backflip_state", None)
    if current is None:
        current = State(env)
        setattr(env, "_backflip_state", current)
    return current


def euler(robot: Entity) -> torch.Tensor:
    return torch.stack(euler_xyz_from_quat(robot.data.root_link_quat_w), 1)


class BeforeSetting:
    """起跳前的"保持初始姿"奖励（同时驱动状态机推进）。"""

    def __init__(self, cfg: RewardTermCfg, env) -> None:
        del cfg
        self.env = env
        self.s = state(env)

    def __call__(self, env, command_name: str, sensor_name: str) -> torch.Tensor:
        self.s.update(env, command_name, sensor_name)
        robot: Entity = env.scene["robot"]
        ids = shared_contacts.joint_ids(env)
        command = env.command_manager.get_command(command_name)
        assert command is not None
        return torch.exp(
            -torch.abs(
                robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids]
            ).sum(1)
            / 4
        ) * (command[:, 2] == 0)

    def reset(self, env_ids=None) -> None:
        self.s.reset(self.env, env_ids)


def _u(env, command_name: str, sensor_name: str) -> State:
    current = state(env)
    current.update(env, command_name, sensor_name)
    return current


def line_z(env, command_name: str, sensor_name: str) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    robot: Entity = env.scene["robot"]
    command = env.command_manager.get_command(command_name)
    assert command is not None
    vertical = robot.data.root_link_vel_w[:, 2]
    return (vertical > 0) * vertical * ~current.landed * (command[:, 2] == 1)


def angle_y(env, command_name: str, sensor_name: str) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    rate = env.scene["robot"].data.root_link_ang_vel_b[:, 1]
    command = env.command_manager.get_command(command_name)
    assert command is not None
    return torch.clamp(
        rate * (rate > 0) * (command[:, 2] == 1) * (~current.flight)
        + 3 * rate * (rate > 0) * (current.flight * ~current.landed),
        max=20.0,
    )


def height_flight(env, command_name: str, sensor_name: str, target_height: float) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    height = env.scene["robot"].data.root_link_pos_w[:, 2]
    return torch.exp(-torch.abs(height - target_height) * 5) * current.flight * ~current.landed * 6


def height_stance(
    env, command_name: str, sensor_name: str, target_height: float, min_height: float
) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    height = env.scene["robot"].data.root_link_pos_w[:, 2]
    return torch.exp(-torch.abs(height - target_height) * 5) * current.landed * (height > min_height)


def orientation(env, command_name: str, sensor_name: str) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    return (
        torch.exp(-torch.abs(euler(env.scene["robot"])).sum(1))
        * current.landed
        * (current.max_pitch_rate > 7)
    )


def orientation_before(env, command_name: str) -> torch.Tensor:
    command = env.command_manager.get_command(command_name)
    assert command is not None
    return torch.exp(-torch.abs(euler(env.scene["robot"])).sum(1)) * (command[:, 2] == 0)


def land_pos(env, command_name: str, sensor_name: str) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    return (
        torch.exp(
            -torch.abs(
                current.start_pos - env.scene["robot"].data.root_link_pos_w[:, :2]
            ).sum(1)
        )
        * current.landed
    )


def symmetric_joints(
    env, legs: int, roles: int, abduction_column: int, mirror_leg_indices: tuple[int, ...]
) -> torch.Tensor:
    """左右对称关节的偏差（镜像腿上髋外展取反后比同角色值）。

    参数全部是**可序列化的数**（腿数/每腿角色数/髋外展在腿块内的列号/镜像腿下标），
    `config.py` 从绑定派生后传进来 —— 而不是把绑定对象塞进 reward params。
    """
    robot: Entity = env.scene["robot"]
    ids = shared_contacts.joint_ids(env)
    q = robot.data.joint_pos[:, ids].reshape(-1, legs, roles).clone()
    for index in mirror_leg_indices:
        q[:, index, abduction_column] *= -1
    pairs = [(left, right) for left, right in ((0, 1), (2, 3)) if right < legs]
    return sum(torch.abs(q[:, left] - q[:, right]).sum(1) for left, right in pairs)


def dof_pos(env) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = shared_contacts.joint_ids(env)
    return torch.abs(robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids]).sum(1)


def hip(env, hip_columns: tuple[int, ...]) -> torch.Tensor:
    """髋外展关节偏离零位的惩罚（列号由绑定派生）。"""
    robot: Entity = env.scene["robot"]
    ids = shared_contacts.joint_ids(env)
    return torch.abs(robot.data.joint_pos[:, ids])[:, hip_columns].sum(1)


def ang_xy(env) -> torch.Tensor:
    return torch.abs(env.scene["robot"].data.root_link_ang_vel_b[:, (0, 2)]).sum(1)


def torques(env) -> torch.Tensor:
    return torch.abs(
        env.scene["robot"].data.qfrc_actuator[:, shared_contacts.joint_ids(env)]
    ).sum(1)


def action_rate(env) -> torch.Tensor:
    return torch.square(env.action_manager.action - env.action_manager.prev_action).sum(1)


def collision(env, sensor_name: str) -> torch.Tensor:
    return (torch.linalg.vector_norm(env.scene[sensor_name].data.force, dim=-1) > 0.1).sum(1)


def dof_pos_limits(env) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = shared_contacts.joint_ids(env)
    limits = robot.data.soft_joint_pos_limits
    q = robot.data.joint_pos[:, ids]
    return (
        -(q - limits[:, ids, 0]).clamp(max=0) + (q - limits[:, ids, 1]).clamp(min=0)
    ).sum(1)


def dof_vel(env) -> torch.Tensor:
    return torch.square(
        env.scene["robot"].data.joint_vel[:, shared_contacts.joint_ids(env)]
    ).sum(1)


def dof_vel_limits(env, max_abs_joint_vel: float) -> torch.Tensor:
    return (
        torch.abs(env.scene["robot"].data.joint_vel[:, shared_contacts.joint_ids(env)])
        - max_abs_joint_vel
    ).clamp(min=0).sum(1)


def feet_force(env, sensor_name: str, max_contact_force: float) -> torch.Tensor:
    return (
        torch.linalg.vector_norm(env.scene[sensor_name].data.force, dim=-1) - max_contact_force
    ).clamp(min=0).sum(1)


def line_vel_stance(env) -> torch.Tensor:
    return torch.abs(env.scene["robot"].data.root_link_lin_vel_b).sum(1)

