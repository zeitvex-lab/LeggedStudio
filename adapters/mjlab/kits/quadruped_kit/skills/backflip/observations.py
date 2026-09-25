"""后空翻的观测帧（源 47 维 actor / 50 维 privileged）与历史。

来源：`go2_skills/backflip/mdp/observations.py`。去机型化改动：
`joint_ids` 从包内 `shared/contacts` 改为族级 `..mdp.contacts`（**按动作项序**取关节
—— 这正是"观测里的关节序与动作维序结构上不可能错位"的那条约定）。
"""

from __future__ import annotations

import torch
from mjlab.entity import Entity

from ..mdp.contacts import joint_ids as _joint_ids
from ..mdp.observations import _SourceHistory

#: 帧内固定字段宽度（源配方常量：命令 3 / 角速度 3 / 重力 3 / 关节 12 / 动作 12 …），
#: 其中"关节段"宽度随族关节数派生，不写死 —— 见 `_actor` / `_critic`。
_LEADING_ZEROS = 2
_ACTOR_NOISE = (0.0,) * 5 + (0.05,) * 3 + (0.1,) * 3 + (0.01,) * 12 + (0.075,) * 12 + (0.0,) * 12


def _gravity(robot: Entity) -> torch.Tensor:
    return robot.data.projected_gravity_b


def _actor(env, command_name: str) -> torch.Tensor:
    """源 actor 帧：`[0,0, cmd, ω*0.25, g, q-q_def, dq*0.05, a]`。"""
    robot: Entity = env.scene["robot"]
    ids = _joint_ids(env)
    command = env.command_manager.get_command(command_name)
    assert command is not None
    return torch.cat(
        (
            torch.zeros((env.num_envs, _LEADING_ZEROS), device=env.device),
            command,
            robot.data.root_link_ang_vel_b * 0.25,
            _gravity(robot),
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
        ),
        1,
    )


def _critic(env, command_name: str) -> torch.Tensor:
    """源 privileged 帧：`[0,0, cmd, q-q_def, dq*0.05, a, v*2, ω*0.25, g]`。"""
    robot: Entity = env.scene["robot"]
    ids = _joint_ids(env)
    command = env.command_manager.get_command(command_name)
    assert command is not None
    return torch.cat(
        (
            torch.zeros((env.num_envs, _LEADING_ZEROS), device=env.device),
            command,
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
            robot.data.root_link_lin_vel_b * 2.0,
            robot.data.root_link_ang_vel_b * 0.25,
            _gravity(robot),
        ),
        1,
    )


class BackflipActorHistory(_SourceHistory):
    history_length = 10

    def __call__(self, env, command_name: str, add_noise: bool) -> torch.Tensor:
        frame = _actor(env, command_name)
        if add_noise:
            amplitude = torch.tensor(_ACTOR_NOISE, device=env.device)
            frame = frame + (2.0 * torch.rand_like(frame) - 1.0) * amplitude
        return self._append(frame)


class BackflipCriticHistory(_SourceHistory):
    history_length = 3

    def __call__(self, env, command_name: str) -> torch.Tensor:
        return self._append(_critic(env, command_name))
