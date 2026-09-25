"""弹簧跳的状态机与源奖励方程。

来源：`go2_skills/spring_jump/mdp/rewards.py`（逐式上移）。去机型化改动：

* `joint_ids` → 族级 `..mdp.contacts`（动作项序）；
* 髋外展列 `(0,3,6,9)` → `hip_columns` 参数（config 从绑定派生）；
* 足端 site 名 `("FL","FR","RL","RR")` → `foot_sites` 参数（config 从绑定派生）；
* 几何目标（飞行 0.47 / 站姿 0.35 / 下限 0.2 / 落地最小高度 0.42 / 起跳姿态角 0.6 /
  足端目标 0.20 / 速度增益 1.6）与阈值（30 / 150）→ 技能 profile；
* 状态机自身常量（`p = max(8 - steps//1200, 0)/10`、起跳冲量 1.5~2.2 m/s）是算法
  配方，就地保留。
"""

from __future__ import annotations

import torch
from mjlab.entity import Entity
from mjlab.managers import RewardTermCfg
from mjlab.utils.lab_api.math import quat_apply_inverse

from ..mdp import contacts as shared_contacts
from .observations import _state, root_euler


class SpringJumpState:
    """源实现的每环境状态机（从起跳到落地的一次性事件）。"""

    def __init__(self, env) -> None:
        self.was_in_flight = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
        self.has_jumped = torch.zeros_like(self.was_in_flight)
        self.last_contacts = torch.zeros((env.num_envs, 4), dtype=torch.bool, device=env.device)
        self.landing_pos = torch.zeros((env.num_envs, 2), device=env.device)
        self.start_pos = torch.zeros_like(self.landing_pos)
        self.max_height = torch.zeros(env.num_envs, device=env.device)
        self.pushed_up = torch.zeros_like(self.was_in_flight)
        self.steps = 0
        self.last_step = -1

    def update(self, env, command_name: str, sensor_name: str) -> None:
        step = int(env.common_step_counter)
        if step == self.last_step:
            return
        self.last_step = step
        self.steps += 1
        robot: Entity = env.scene["robot"]
        command = env.command_manager.get_command(command_name)
        assert command is not None
        contact = shared_contacts.source_vertical_contact(env.scene[sensor_name], 1.0)
        filtered = contact | self.last_contacts
        self.last_contacts.copy_(contact)
        flight = ~filtered.any(dim=1) & (command[:, 2] > 0)
        self.was_in_flight |= flight
        landed = filtered.any(dim=1) & self.was_in_flight
        new_landing = landed & ~self.has_jumped
        self.landing_pos[new_landing] = robot.data.root_link_pos_w[new_landing, :2]
        self.has_jumped |= landed
        self.max_height = torch.maximum(self.max_height, robot.data.root_link_pos_w[:, 2])
        # 源实现的训练期辅助：起跳时一次性给根速度一个上限冲量，
        # 概率 p = max(8 - steps//1200, 0)/10。
        should_push = (~self.pushed_up) & (~self.has_jumped) & (command[:, 2] > 0)
        probability = max(8 - self.steps // 1200, 0) / 10.0
        ids = torch.nonzero(
            should_push & (torch.rand(env.num_envs, device=env.device) < probability)
        ).squeeze(1)
        if len(ids):
            velocity = robot.data.root_link_vel_w[ids].clone()
            velocity[:, 2].uniform_(1.5, 2.2)
            robot.write_root_link_velocity_to_sim(velocity, env_ids=ids)
        self.pushed_up |= should_push

    def reset(self, env, env_ids=None) -> None:
        if env_ids is None:
            env_ids = torch.arange(env.num_envs, device=env.device)
        robot: Entity = env.scene["robot"]
        self.was_in_flight[env_ids] = False
        self.has_jumped[env_ids] = False
        self.last_contacts[env_ids] = False
        self.landing_pos[env_ids] = robot.data.root_link_pos_w[env_ids, :2]
        self.start_pos[env_ids] = robot.data.root_link_pos_w[env_ids, :2]
        self.max_height[env_ids] = 0.0
        self.pushed_up[env_ids] = False


class _SpringReward:
    def __init__(self, cfg: RewardTermCfg, env) -> None:
        del cfg
        self.env = env
        self.state = _state(env)

    def reset(self, env_ids=None) -> None:
        self.state.reset(self.env, env_ids)


class BeforeSetting(_SpringReward):
    """起跳前的"保持初始姿"奖励（同时驱动状态机推进）。"""

    def __call__(self, env, command_name: str, sensor_name: str) -> torch.Tensor:
        self.state.update(env, command_name, sensor_name)
        robot: Entity = env.scene["robot"]
        ids = shared_contacts.joint_ids(env)
        command = env.command_manager.get_command(command_name)
        assert command is not None
        return torch.exp(
            -torch.abs(
                robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids]
            ).sum(1)
            / 2.0
        ) * (command[:, 2] == 0)


def _u(env, command_name: str, sensor_name: str) -> SpringJumpState:
    current = _state(env)
    current.update(env, command_name, sensor_name)
    return current


def line_z(env, command_name: str, sensor_name: str) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    robot: Entity = env.scene["robot"]
    command = env.command_manager.get_command(command_name)
    assert command is not None
    vertical = robot.data.root_link_vel_w[:, 2]
    return (vertical > 0) * vertical * ~current.has_jumped * (command[:, 2] == 1)


def flight(env, command_name: str, sensor_name: str) -> torch.Tensor:
    return _u(env, command_name, sensor_name).was_in_flight.float()


def base_height_flight(
    env, command_name: str, sensor_name: str, target_height: float
) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    height = env.scene["robot"].data.root_link_pos_w[:, 2]
    return (
        torch.exp(-torch.abs(height - target_height) * 5)
        * current.was_in_flight
        * ~current.has_jumped
        * 6
    )


def base_height_stance(
    env, command_name: str, sensor_name: str, target_height: float, min_height: float
) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    height = env.scene["robot"].data.root_link_pos_w[:, 2]
    return torch.exp(-torch.abs(height - target_height) * 5) * current.has_jumped * (height > min_height)


def land_pos(
    env,
    command_name: str,
    sensor_name: str,
    *,
    min_flight_height: float,
    max_landing_tilt: float,
) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    command = env.command_manager.get_command(command_name)
    assert command is not None
    robot: Entity = env.scene["robot"]
    return (
        torch.exp(-torch.abs(current.start_pos + command[:, :2] - current.landing_pos).sum(1))
        * current.has_jumped
        * (root_euler(robot).sum(1) < max_landing_tilt)
        * (current.max_height > min_flight_height)
    )


def dof_pos(env) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = shared_contacts.joint_ids(env)
    return torch.abs(robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids]).sum(1)


def hip_pos(env, hip_columns: tuple[int, ...]) -> torch.Tensor:
    """髋外展关节偏离默认姿的惩罚（列号由绑定派生）。"""
    robot: Entity = env.scene["robot"]
    ids = shared_contacts.joint_ids(env)
    deviation = torch.abs(robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids])
    return deviation[:, hip_columns].sum(1)


def orientation(env) -> torch.Tensor:
    return torch.exp(-torch.abs(root_euler(env.scene["robot"])).sum(1))


def ang_vel_xy(env) -> torch.Tensor:
    return torch.abs(env.scene["robot"].data.root_link_ang_vel_b).sum(1)


def torques(env) -> torch.Tensor:
    return torch.abs(
        env.scene["robot"].data.qfrc_actuator[:, shared_contacts.joint_ids(env)]
    ).sum(1)


def action_rate(env) -> torch.Tensor:
    return torch.square(env.action_manager.action - env.action_manager.prev_action).sum(1)


def collision(env, sensor_name: str) -> torch.Tensor:
    return (torch.linalg.vector_norm(env.scene[sensor_name].data.force, dim=-1) > 0.1).sum(1)


def dof_vel(env) -> torch.Tensor:
    return torch.square(
        env.scene["robot"].data.joint_vel[:, shared_contacts.joint_ids(env)]
    ).sum(1)


def dof_vel_limits(env, max_abs_joint_vel: float) -> torch.Tensor:
    return (
        torch.abs(env.scene["robot"].data.joint_vel[:, shared_contacts.joint_ids(env)])
        - max_abs_joint_vel
    ).clamp(min=0).sum(1)


def tracking_lin_vel(
    env, command_name: str, sensor_name: str, gain: float, sensor_name_key: str = ""
) -> torch.Tensor:
    """起跳前的前进速度跟踪（源配方 `exp(-(gain·cmd_x − v_x)²)`，只在飞行前生效）。"""
    del sensor_name_key
    current = _u(env, command_name, sensor_name)
    command = env.command_manager.get_command(command_name)
    assert command is not None
    forward = env.scene["robot"].data.root_link_lin_vel_b[:, 0]
    return (
        torch.exp(-torch.square(command[:, 0] * gain - forward))
        * current.was_in_flight
        * ~current.has_jumped
        * 5
    )


def line_vel_stance(env, command_name: str, sensor_name: str) -> torch.Tensor:
    current = _u(env, command_name, sensor_name)
    return (
        torch.abs(env.scene["robot"].data.root_link_lin_vel_b[:, :2]).sum(1)
        * current.has_jumped
    )


def dof_pos_limits(env) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = shared_contacts.joint_ids(env)
    limits = robot.data.soft_joint_pos_limits
    assert limits is not None
    position = robot.data.joint_pos[:, ids]
    return (
        -(position - limits[:, ids, 0]).clamp(max=0.0)
        + (position - limits[:, ids, 1]).clamp(min=0.0)
    ).sum(1)


def feet_contact_forces(env, sensor_name: str, max_contact_force: float) -> torch.Tensor:
    force = env.scene[sensor_name].data.force
    assert force is not None
    return (
        torch.linalg.vector_norm(force, dim=-1) - max_contact_force
    ).clamp(min=0.0).sum(1)


def foot_clearance(
    env, command_name: str, sensor_name: str, foot_sites: tuple[str, ...], target_height: float
) -> torch.Tensor:
    """飞行段足端离地高度（按机身坐标系的 z 分量，目标 `target_height`）。"""
    current = _u(env, command_name, sensor_name)
    robot: Entity = env.scene["robot"]
    ids, _ = robot.find_sites(foot_sites, preserve_order=True)
    root_to_foot = robot.data.site_pos_w[:, ids] - robot.data.root_link_pos_w[:, None, :]
    quat = robot.data.root_link_quat_w[:, None, :].expand(-1, len(ids), -1)
    height = quat_apply_inverse(
        quat.reshape(-1, 4), root_to_foot.reshape(-1, 3)
    ).reshape(-1, len(ids), 3)[..., 2]
    return (
        torch.abs(height + target_height).sum(1)
        * current.was_in_flight
        * ~current.has_jumped
        * 6
    )


def below_reset_height(env, reset_height: float = 0.15) -> torch.Tensor:
    return env.scene["robot"].data.root_link_pos_w[:, 2] <= reset_height
