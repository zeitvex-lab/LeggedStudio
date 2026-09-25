"""弹簧跳命令：一次性触发 + 固定的前进目标速度。

来源：`go2_skills/spring_jump/mdp/commands.py`。去机型化：目标速度区间与起跳帧区间由
技能 profile 给（命令 cfg 的 `ranges.lin_vel_x` 就是采样区间，源实现即如此）；
`create_gui` 从族级 `..mdp.commands` 借同一份实现（源实现从 jump 包内借）。
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from mjlab.tasks.velocity.mdp import UniformVelocityCommand, UniformVelocityCommandCfg

from ..mdp.commands import RearStandVelocityCommand


class SpringJumpCommand(UniformVelocityCommand):
    """保留采样到的目标 x 速度，并在随机的 50~59 帧把 `command[2]` 置 1（起跳）。"""

    def __init__(self, cfg: SpringJumpCommandCfg, env) -> None:
        super().__init__(cfg, env)
        self._takeoff_frame = torch.zeros(env.num_envs, dtype=torch.long, device=env.device)

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        self.vel_command_b[env_ids] = 0.0
        low, high = self.cfg.ranges.lin_vel_x
        self.vel_command_b[env_ids, 0].uniform_(low, high)
        takeoff_low, takeoff_high = self.cfg.takeoff_frame_range
        self._takeoff_frame[env_ids] = torch.randint(
            takeoff_low, takeoff_high, (len(env_ids),), device=self.device
        )

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        del env_ids
        # 源实现在"相等"时翻转并保持到落地（本实现用 >= 复现同一语义）。
        self.vel_command_b[:, 2] = torch.maximum(
            self.vel_command_b[:, 2],
            (self._env.episode_length_buf >= self._takeoff_frame).float(),
        )

    # 基座的速度 GUI 对固定的 y / yaw 会生成 max=0 的非法滑条；
    # 源兼容 GUI 把零区间轴渲成禁用控件（与 backflip 同一份实现）。
    create_gui = RearStandVelocityCommand.create_gui


@dataclass(kw_only=True)
class SpringJumpCommandCfg(UniformVelocityCommandCfg):
    #: 起跳帧的采样区间（源配方 50~60 控制步）。
    takeoff_frame_range: tuple[int, int] = (50, 60)

    def build(self, env) -> SpringJumpCommand:
        return SpringJumpCommand(self, env)
