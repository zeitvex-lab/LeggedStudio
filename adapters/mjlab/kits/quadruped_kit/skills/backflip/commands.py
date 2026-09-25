"""后空翻命令：一次性触发，其余时间恒零。

来源：`go2_skills/backflip/mdp/commands.py`。去机型化改动只有一处 —— 源实现从
`jump/mdp/commands.py` 借 `RearStandVelocityCommand.create_gui`（包内相对导入），
这里改从族级 `..mdp.commands` 借同一份实现。
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from mjlab.tasks.velocity.mdp import UniformVelocityCommand, UniformVelocityCommandCfg

from ..mdp.commands import RearStandVelocityCommand


class BackflipCommand(UniformVelocityCommand):
    def __init__(self, cfg: BackflipCommandCfg, env) -> None:
        super().__init__(cfg, env)
        self._takeoff_frame = torch.zeros(env.num_envs, dtype=torch.long, device=env.device)

    def _resample_command(self, env_ids) -> None:
        self.vel_command_b[env_ids] = 0.0
        low, high = self.cfg.takeoff_frame_range
        self._takeoff_frame[env_ids] = torch.randint(
            low, high, (len(env_ids),), device=self.device
        )

    def _update_command(self, env_ids=None) -> None:
        del env_ids
        self.vel_command_b[:, 2] = torch.maximum(
            self.vel_command_b[:, 2],
            (self._env.episode_length_buf >= self._takeoff_frame).float(),
        )

    create_gui = RearStandVelocityCommand.create_gui


@dataclass(kw_only=True)
class BackflipCommandCfg(UniformVelocityCommandCfg):
    #: 起跳帧的采样区间（源配方 50~60 控制步）。
    takeoff_frame_range: tuple[int, int] = (50, 60)

    def build(self, env) -> BackflipCommand:
        return BackflipCommand(self, env)
