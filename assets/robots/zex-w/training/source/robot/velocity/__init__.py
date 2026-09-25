"""ZEX-W 的族级 velocity 技能客户端件（绑定 + 竞赛配方 profile + 注入名称空间）。

* `binding.py` —— 契约 + MJCF → `WheelLegSkillBinding`（技能层唯一的机型入口）；
* `profile.py` —— 竞赛配方两档的源配方数值 + 注入件（命令类 / 动作项类 / mdp 名称空间）；
* `terms.py` —— 交出去的机型 mdp 名称空间（奖励核 / 课程类 / 指标核）。

公开入口（档案 `entrypoints.env` 引用）仍是 `robot.config.env_cfgs:flat_env_cfg` /
`rough_env_cfg`；本包只提供它们要的两样数据。
"""

from .binding import ZEXW, contract, contract_path
from .profile import FLAT, ROUGH

__all__ = ["FLAT", "ROUGH", "ZEXW", "contract", "contract_path"]
