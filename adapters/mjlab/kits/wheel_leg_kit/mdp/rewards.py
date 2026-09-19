# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：本文件由 b2w_velocity/mdp/{name}.py **逐字上移**
# （== go2w_velocity 同名文件 sha256 一致；m20_velocity 同名文件亦逐字一致）。
# 包侧 mdp/__init__ 改为从本 kit 模块星导入，组合顺序与原 mdp/__init__ 相同。
# ------------------------------------------------------------------------------
"""Compatibility exports for active Go2-W reward helpers."""

from .feet_rewards import *  # noqa: F401, F403
from .posture_rewards import *  # noqa: F401, F403
from .tracking_rewards import *  # noqa: F401, F403
from .wheel_rewards import *  # noqa: F401, F403
