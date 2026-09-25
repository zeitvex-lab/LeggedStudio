"""族级 Velocity 技能（四足）。

* `config.py`：`make_env_cfg(binding, profile, terrain_profile=..., play=...)` —— 环境装配；
* `profile.py`：`VelocityProfile` —— 任务级数值（命令/地形/DR/奖励权重/终止阈值）。

与 `trot` / `jump` / `parkour` 同一分层：机型包只提交**绑定**（契约 + MJCF + 基座实体）
与**profile 覆盖**，实现全在本层，零机型字面量。
"""

from .config import TerrainProfile, make_env_cfg
from .profile import VelocityProfile

__all__ = ["TerrainProfile", "VelocityProfile", "make_env_cfg"]
