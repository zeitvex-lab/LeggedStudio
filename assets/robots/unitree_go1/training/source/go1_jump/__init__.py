"""Unitree Go1 的特技（jump）训练入口：族级技能 + go1 绑定。

本包是"族级技能在第二台同族机型上复用"的**实证点**：任务配方（观测 / 奖励 / 命令 /
事件 / 课程 / 终止 / 传感器 / 动作项）一行都不在包内 —— 全部来自
`adapters/mjlab/kits/quadruped_kit/skills/jump/`；包内只有两样**机型事实**：

* `config.py` 的 go1 绑定（契约 + 包内 MJCF 派生）；
* `profile.py` 的机型身份（task_id / experiment_name）。

关节序、默认姿、PD 谱、足端几何、根 body 一律经契约/MJCF 解析（见
`quadruped_kit/skills/binding.py`），所以 go1 的 **MJCF 腿序是 FR/FL/RL/RR、而契约是
FL/FR/RL/RR** 这个差异不需要任何技能层代码去处理。
"""

from .config import make_go1_jump_env_cfg, make_go1_jump_runner_cfg  # noqa: F401

__all__ = ["make_go1_jump_env_cfg", "make_go1_jump_runner_cfg"]
