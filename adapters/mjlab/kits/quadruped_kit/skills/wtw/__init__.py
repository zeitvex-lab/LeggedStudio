"""WTW（Walk-These-Ways 周期步态先验）技能（族级）。

来源：`go2` 包的 `tasks/locomotion/wtw.py` + `wtw_mdp.py`（LeggedGym-Ex Periodic
Reward Framework 的移植）。三个模块的分工与族级其它技能一致：

* `profile.py` —— 任务数值（θ 采样池、行为参数区间、奖励权重与核参数、命令/仿真上限）；
* `mdp.py`     —— MDP 项（相位推进 / 时钟与行为观测 / 周期步态与跟踪奖励）；
* `config.py`  —— 环境与运行器工厂（绑定派生几何 + profile 数据装配）。
"""

from __future__ import annotations

from .config import TerrainProfile as WtwTerrainProfile
from .config import make_env_cfg, make_runner_cfg
from .profile import WtwProfile

__all__ = ["WtwProfile", "WtwTerrainProfile", "make_env_cfg", "make_runner_cfg"]
