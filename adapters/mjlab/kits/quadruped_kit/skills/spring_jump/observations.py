"""弹簧跳的观测帧（源 47 维 actor / 65 维 privileged）与历史。

来源：`go2_skills/spring_jump/mdp/observations.py`。去机型化：`joint_ids` 走族级
`..mdp.contacts`（动作项序）；`root_euler` / `contact_observation` 复用族级
`..mdp.contacts`（与 jump 同一份实现）。
"""

from __future__ import annotations

import torch
from mjlab.entity import Entity

from ..mdp.contacts import joint_ids as _joint_ids, root_euler
from ..mdp.observations import _SourceHistory, contact_observation


def _state(env):
    """状态机实例（**函数内导入**：状态类住在 rewards，模块级导入会成环）。"""
    current = getattr(env, "_spring_jump_state", None)
    if current is None:
        from .rewards import SpringJumpState

        current = SpringJumpState(env)
        setattr(env, "_spring_jump_state", current)
    return current


_ACTOR_NOISE = (
    (0.0,) * 5
    + (0.05,) * 3
    + (0.1,) * 3
    + (0.01,) * 12
    + (0.075,) * 12
    + (0.0,) * 12
)


def _actor_frame(env, command_name: str) -> torch.Tensor:
    """源 actor 帧：`[0,0, cmd, ω*0.25, euler, q-q_def, dq*0.05, a]`（47 维）。"""
    robot: Entity = env.scene["robot"]
    ids = _joint_ids(env)
    command = env.command_manager.get_command(command_name)
    assert command is not None
    return torch.cat(
        (
            torch.zeros((env.num_envs, 2), device=env.device),
            command,
            robot.data.root_link_ang_vel_b * 0.25,
            root_euler(robot),
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
        ),
        dim=1,
    )


def _critic_frame(env, command_name: str, sensor_name: str) -> torch.Tensor:
    """源 privileged 帧（65 维）。

    源注释说"两个接触"，实际拼了四只脚 —— 这是**源的既定行为**，照搬不复刻注释。
    """
    robot: Entity = env.scene["robot"]
    ids = _joint_ids(env)
    command = env.command_manager.get_command(command_name)
    assert command is not None
    state = _state(env)
    return torch.cat(
        (
            command,
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
            robot.data.root_link_lin_vel_b * 2.0,
            robot.data.root_link_ang_vel_b * 0.25,
            root_euler(robot),
            contact_observation(env, sensor_name),
            state.has_jumped.float().unsqueeze(1),
        ),
        dim=1,
    )


class SpringActorHistory(_SourceHistory):
    history_length = 10

    def __call__(self, env, command_name: str, add_noise: bool) -> torch.Tensor:
        frame = _actor_frame(env, command_name)
        if add_noise:
            amplitude = torch.tensor(_ACTOR_NOISE, device=env.device)
            frame = frame + (2.0 * torch.rand_like(frame) - 1.0) * amplitude
        return self._append(frame)


class SpringCriticHistory(_SourceHistory):
    history_length = 3

    def __call__(self, env, command_name: str, sensor_name: str) -> torch.Tensor:
        return self._append(_critic_frame(env, command_name, sensor_name))
