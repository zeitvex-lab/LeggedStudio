"""族级技能的观测帧与历史缓冲。

来源：`go2_skills/trot/mdp/observations.py`（与 `.../jump/mdp/observations.py` 逐字相同，
两技能共用一份）。**只保留 trot / jump 用到的部分**：姿态类技能（hand_stand / rear_stand）
的帧与它们的域随机化标签是 go2 独占实现，未上移，仍留在 go2 包内。

与源实现的差异只有两处，都是"去掉机型常量"：

1. 关节序：`joint_ids(env)` 取自动作项（= 契约 `action.joint_order`），不再写死 12 个 go2 关节名；
2. 帧宽不再写死（源实现 `frame_dim = 47 / 68 / 70`）：首次成帧时按**实际帧宽**建缓冲，
   于是"帧宽声明"和"帧实现"不可能漂移（声明仍在 profile 的 `actor_frame_dim` 里留档）。
   `history_length` 是技能级常量（源配方就这么多帧），保留为类属性。
"""

import math

import torch
from mjlab.entity import Entity
from mjlab.managers import ObservationTermCfg
from mjlab.sensor import ContactSensor

from .contacts import (
    joint_ids,
    phase,
    phase_command,
    root_euler,
    source_contact,
    source_vertical_contact,
    stance_mask,
)


def contact_observation(env, sensor_name: str, threshold: float = 5.0) -> torch.Tensor:
    sensor: ContactSensor = env.scene[sensor_name]
    return source_contact(sensor, threshold).float()


def actor_frame(env, command_name: str, cycle_time: float) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = joint_ids(env)
    return torch.cat(
        (
            phase_command(env, command_name, cycle_time),
            robot.data.root_link_ang_vel_b * 0.25,
            root_euler(robot),
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
        ),
        dim=1,
    )


def critic_frame(
    env, command_name: str, sensor_name: str, cycle_time: float
) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = joint_ids(env)
    return torch.cat(
        (
            phase_command(env, command_name, cycle_time),
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
            robot.data.root_link_lin_vel_b * 2.0,
            robot.data.root_link_ang_vel_b * 0.25,
            root_euler(robot),
            stance_mask(env, cycle_time),
            contact_observation(env, sensor_name),
        ),
        dim=1,
    )


class _SourceHistory:
    """Frame-major, oldest-to-newest history with source-style zero reset."""

    history_length: int

    def __init__(self, cfg: ObservationTermCfg, env) -> None:
        del cfg
        self._history: torch.Tensor | None = None
        self._frame_dim: int | None = None
        self._num_envs = env.num_envs
        self._device = env.device

    def _append(self, frame: torch.Tensor) -> torch.Tensor:
        if self._history is None:
            self._frame_dim = int(frame.shape[-1])
            self._history = torch.zeros(
                self._num_envs, self.history_length, self._frame_dim, device=self._device
            )
        self._history = torch.roll(self._history, shifts=-1, dims=1)
        self._history[:, -1] = frame
        return self._history.reshape(frame.shape[0], -1)

    def reset(self, env_ids=None) -> None:
        if self._history is not None:
            self._history[env_ids] = 0.0


class TrotActorHistory(_SourceHistory):
    history_length = 10

    def __call__(
        self, env, command_name: str, cycle_time: float, add_noise: bool
    ) -> torch.Tensor:
        frame = actor_frame(env, command_name, cycle_time)
        if add_noise:
            _, upper = single_frame_noise_bounds(frame.shape[-1])
            amplitude = torch.tensor(upper, device=env.device)
            frame = frame + (2.0 * torch.rand_like(frame) - 1.0) * amplitude
        return self._append(frame)


class TrotCriticHistory(_SourceHistory):
    history_length = 3

    def __call__(
        self, env, command_name: str, sensor_name: str, cycle_time: float
    ) -> torch.Tensor:
        return self._append(critic_frame(env, command_name, sensor_name, cycle_time))


def jump_phase(env, cycle_time: float) -> torch.Tensor:
    """Unwrapped source Jump phase (the stance transition happens only once)."""
    return env.episode_length_buf * env.step_dt / cycle_time


def jump_stance_mask(env, cycle_time: float) -> torch.Tensor:
    gait_phase = jump_phase(env, cycle_time)
    return torch.stack((gait_phase < 0.6, gait_phase > 0.6), dim=1).float()


def jump_phase_command(env, command_name: str, cycle_time: float) -> torch.Tensor:
    gait_phase = jump_phase(env, cycle_time)
    command = env.command_manager.get_command(command_name)
    assert command is not None
    return torch.cat(
        (
            torch.sin(2.0 * math.pi * gait_phase).unsqueeze(1),
            torch.cos(2.0 * math.pi * gait_phase).unsqueeze(1),
            command[:, :2] * 2.0,
            command[:, 2:3] * 0.25,
        ),
        dim=1,
    )


def jump_actor_frame(env, command_name: str, cycle_time: float) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = joint_ids(env)
    return torch.cat(
        (
            jump_phase_command(env, command_name, cycle_time),
            robot.data.root_link_ang_vel_b * 0.25,
            root_euler(robot),
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
        ),
        dim=1,
    )


def jump_critic_frame(
    env, command_name: str, sensor_name: str, cycle_time: float
) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = joint_ids(env)
    sensor: ContactSensor = env.scene[sensor_name]
    # The source samples one friction bucket per environment and applies it to all
    # robot shapes. Reading the first robot geom therefore recovers the label.
    friction = robot.data.model.geom_friction[:, robot.indexing.geom_ids[0], 0].unsqueeze(
        1
    )
    # Go2_Jump allocates body_mass but never writes to it; its critic observes zero.
    source_body_mass = torch.zeros((env.num_envs, 1), device=env.device)
    return torch.cat(
        (
            jump_phase_command(env, command_name, cycle_time),
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
            robot.data.root_link_lin_vel_b * 2.0,
            robot.data.root_link_ang_vel_b * 0.25,
            root_euler(robot),
            friction,
            source_body_mass,
            jump_stance_mask(env, cycle_time),
            source_vertical_contact(sensor, 5.0).float(),
        ),
        dim=1,
    )


class JumpActorHistory(_SourceHistory):
    history_length = 10

    def __call__(
        self, env, command_name: str, cycle_time: float, add_noise: bool
    ) -> torch.Tensor:
        frame = jump_actor_frame(env, command_name, cycle_time)
        if add_noise:
            _, upper = single_frame_noise_bounds(frame.shape[-1])
            amplitude = torch.tensor(upper, device=env.device)
            frame = frame + (2.0 * torch.rand_like(frame) - 1.0) * amplitude
        return self._append(frame)


class JumpCriticHistory(_SourceHistory):
    history_length = 3

    def __call__(
        self, env, command_name: str, sensor_name: str, cycle_time: float
    ) -> torch.Tensor:
        return self._append(jump_critic_frame(env, command_name, sensor_name, cycle_time))


def single_frame_noise_bounds(
    frame_dim: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """源配方的逐段噪声幅度（按帧布局展开）。

    帧布局 = 相位 5 段 + 角速度 3 维 + 欧拉角 3 维 + 关节位置 n + 关节速度 n + 动作 n，
    故只有关节类的三段宽度随族关节数变化 —— 这里按实际帧宽反推 n，
    不再写死 `[0.01] * 12`（换关节数不会静默错位）。
    """
    non_joint = 5 + 3 + 3
    if frame_dim < non_joint or (frame_dim - non_joint) % 3 != 0:
        raise ValueError(
            f"帧宽 {frame_dim} 与族级帧布局（5 相位 + 3 角速度 + 3 欧拉 + 3×关节数）不符"
        )
    joints = (frame_dim - non_joint) // 3
    amplitudes = (
        [0.0] * 5
        + [0.2 * 0.25] * 3
        + [0.1] * 3
        + [0.01] * joints
        + [1.5 * 0.05] * joints
        + [0.0] * joints
    )
    return tuple(-value for value in amplitudes), tuple(amplitudes)
