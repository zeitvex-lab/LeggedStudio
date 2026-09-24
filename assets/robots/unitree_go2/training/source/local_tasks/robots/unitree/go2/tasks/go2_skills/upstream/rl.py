"""Go2 侧薄委托：PPO runner 构造（族级唯一真值）。

实现已上移为 `.../quadruped_kit/skills/mdp/rl.py`（`make_ppo_runner_cfg` +
对称性扩展算法配置 `RslRlPpoWithSymmetryAlgorithmCfg`）。本模块只做转出 ——
包内未上移的技能（backflip / hand_stand / rear_stand / spring_jump / dreamwaq /
amp_dreamwaq）与工具脚本按老路径继续导入。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.mdp.rl import (
    RslRlPpoWithSymmetryAlgorithmCfg,
    make_ppo_runner_cfg,
)

__all__ = ["RslRlPpoWithSymmetryAlgorithmCfg", "make_ppo_runner_cfg"]
