"""Go2 侧薄委托：AMP-DreamWaQ 算法类（族级实现在
`quadruped_kit/skills/imitation/rl.py` 的 `AmpPpoMixin`）。

本模块只做三件事（入口符号 `local_tasks...amp_dreamwaq.rl:AmpDreamWaQPPO` 不动）：

1. 组合：族级 AMP 混入 + DreamWaQ 宿主 PPO（VAE 更新在混入里按宿主能力执行）；
2. 填 go2 的两个机型量：契约关节序（判别器状态 + 动作 std 下限）与专家数据目录；
3. 保留类名/模块路径 —— runner 配置与旧检查点都按它解析。

判别器、回放缓冲、归一化、AMP 奖励整形与更新次序全部在族级唯一实现。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.imitation.rl import AmpPpoMixin

from ..binding import GO2
from ..dreamwaq.mdp.rl import DreamWaQPPO
from .motion import GO2_AMP_MOTION_ROOT


class AmpDreamWaQPPO(AmpPpoMixin, DreamWaQPPO):
    """DreamWaQ PPO + Gym 兼容的 AMP 数据流与优化（源口径）。"""

    amp_joint_order = tuple(GO2.joint_order)
    amp_motion_root = str(GO2_AMP_MOTION_ROOT)
