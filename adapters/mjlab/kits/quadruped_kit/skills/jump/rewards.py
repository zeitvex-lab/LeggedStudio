"""Jump 技能的奖励方程（族级）。

来源：`go2_skills/jump/mdp/rewards.py`，除以下去机型化改动外逐字一致：

* 关节序 → `joint_ids(env)`（动作项声明），不再写死 12 个 go2 关节名；
* 足端帧 → `foot_heights(env)`（站点优先、几何回退），不再写死 `("FL","FR","RL","RR")` 的 site；
* 足端受力 → 直接用足端传感器自己的槽位顺序，不再写死 4 个几何名；
* 髋关节位置 → 族角色解析，不再写死 `(0, 3, 6, 9)`。
"""

import torch
from mjlab.entity import Entity
from mjlab.managers import RewardTermCfg
from mjlab.sensor import ContactSensor

from ..family import DEFAULT_FAMILY_ID, joint_indices_by_role
from ..mdp import rl as shared
from ..mdp.contacts import foot_heights, joint_ids, joint_names, source_vertical_contact
from ..mdp.observations import jump_stance_mask

absolute_torques = shared.absolute_torques
action_rate = shared.action_rate
collision = shared.collision
contact_without_command = shared.contact_without_command
default_pos = shared.default_pos
stand_still = shared.stand_still


def jump_tracking_lin_vel(env, command_name: str, sigma: float) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    cmd = shared.command(env, command_name)
    is_moving = torch.linalg.vector_norm(cmd[:, :3], dim=1) > 0.1
    error = torch.square(cmd[:, :2] - robot.data.root_link_lin_vel_b[:, :2]).sum(dim=1)
    return (
        torch.exp(-error / sigma) * is_moving
        + torch.exp(
            -torch.linalg.vector_norm(robot.data.root_link_lin_vel_b[:, :2], dim=1) / sigma
        )
        * ~is_moving
    )


def jump_tracking_ang_vel(env, command_name: str, sigma: float) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    cmd = shared.command(env, command_name)
    is_moving = torch.linalg.vector_norm(cmd[:, :3], dim=1) > 0.1
    error = torch.square(cmd[:, 2] - robot.data.root_link_ang_vel_b[:, 2])
    return (
        torch.exp(-error / sigma) * is_moving
        + torch.exp(-torch.abs(robot.data.root_link_ang_vel_b[:, 2]) / sigma) * ~is_moving
    )


def jump_lin_vel_z(env) -> torch.Tensor:
    return torch.exp(-torch.abs(env.scene["robot"].data.root_link_lin_vel_b[:, 2]))


def jump_ang_vel_xy(env) -> torch.Tensor:
    return torch.exp(
        -torch.linalg.vector_norm(
            torch.abs(env.scene["robot"].data.root_link_ang_vel_b[:, :2]), dim=1
        )
    )


def jump_orientation(env) -> torch.Tensor:
    return torch.exp(
        -10.0
        * torch.linalg.vector_norm(
            env.scene["robot"].data.projected_gravity_b[:, :2], dim=1
        )
    )


def jump_base_height(env, command_name: str, target_height: float) -> torch.Tensor:
    return torch.exp(
        -10.0 * torch.abs(env.scene["robot"].data.root_link_pos_w[:, 2] - target_height)
    ) * ~shared.moving(env, command_name)


class JointVelocityDifference:
    """Jump source acceleration term omits division by policy dt."""

    def __init__(self, cfg: RewardTermCfg, env) -> None:
        del cfg
        self._last_velocity = torch.zeros(
            env.num_envs, len(joint_ids(env)), device=env.device
        )

    def __call__(self, env) -> torch.Tensor:
        robot: Entity = env.scene["robot"]
        velocity = robot.data.joint_vel[:, joint_ids(env)]
        value = torch.square(self._last_velocity - velocity).sum(dim=1)
        self._last_velocity.copy_(velocity)
        return value

    def reset(self, env_ids=None) -> None:
        self._last_velocity[env_ids] = 0.0


def jump_contact_match(
    env, sensor_name: str, command_name: str, cycle_time: float
) -> torch.Tensor:
    sensor: ContactSensor = env.scene[sensor_name]
    contact = source_vertical_contact(sensor, 5.0)
    all_equal = (
        (contact[:, 0] == contact[:, 1])
        & (contact[:, 1] == contact[:, 2])
        & (contact[:, 2] == contact[:, 3])
    )
    return (
        all_equal
        & (contact[:, 3] == jump_stance_mask(env, cycle_time)[:, 0].bool())
        & shared.moving(env, command_name)
    )


def jump_feet_clearance(
    env, command_name: str, cycle_time: float, max_height: float
) -> torch.Tensor:
    height = (foot_heights(env) - 0.02).clamp(min=0.0, max=max_height)
    return (height * (1.0 - jump_stance_mask(env, cycle_time)[:, :1])).sum(
        dim=1
    ) * shared.moving(env, command_name)


def jump_default_hip_pos(env) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    hips = joint_indices_by_role(joint_names(env), "hip_abduction", DEFAULT_FAMILY_ID)
    error = torch.abs(robot.data.joint_pos[:, joint_ids(env)][:, hips]).sum(dim=1)
    return torch.exp(-4.0 * error)


class FeetAirTime:
    def __init__(self, cfg: RewardTermCfg, env) -> None:
        del cfg
        self._num_envs = env.num_envs
        self._device = env.device
        # 缓冲按**足端数**（= 传感器槽数）在首次调用时建，不再写死 4。
        self._air_time: torch.Tensor | None = None
        self._last_contact: torch.Tensor | None = None

    def _ensure_buffers(self, feet: int) -> None:
        if self._air_time is not None:
            return
        self._air_time = torch.zeros((self._num_envs, feet), device=self._device)
        self._last_contact = torch.zeros(
            (self._num_envs, feet), dtype=torch.bool, device=self._device
        )

    def __call__(self, env, sensor_name: str, command_name: str) -> torch.Tensor:
        contact = source_vertical_contact(env.scene[sensor_name], 1.0)
        self._ensure_buffers(int(contact.shape[1]))
        assert self._air_time is not None and self._last_contact is not None
        filtered = contact | self._last_contact
        self._last_contact.copy_(contact)
        first_contact = (self._air_time > 0.0) & filtered
        self._air_time += env.step_dt
        reward = ((self._air_time - 0.5) * first_contact).sum(dim=1) * shared.moving(
            env, command_name
        )
        self._air_time *= ~filtered
        return reward

    def reset(self, env_ids=None) -> None:
        if self._air_time is None or self._last_contact is None:
            return
        self._air_time[env_ids] = 0.0
        self._last_contact[env_ids] = False


def feet_contact_forces(
    env, sensor_name: str, max_contact_force: float
) -> torch.Tensor:
    sensor: ContactSensor = env.scene[sensor_name]
    force = sensor.data.force
    assert force is not None
    return (
        (torch.linalg.vector_norm(force, dim=-1) - max_contact_force)
        .clamp(min=0.0)
        .sum(dim=1)
    )
