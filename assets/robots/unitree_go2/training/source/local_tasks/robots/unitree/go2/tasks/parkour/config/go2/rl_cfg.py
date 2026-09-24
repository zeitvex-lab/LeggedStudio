"""Standalone RSL-RL configuration for Unitree Go2 PIE（薄委托）。

族级实现在 `adapters.mjlab.kits.quadruped_kit/skills/parkour/config.py::make_runner_cfg`
（PIE actor / PIE-PPO 的类路径与全部超参都在那里，属族级配方）；本模块只把
机型身份（`GO2_PARKOUR` 的 `experiment_name`）带进去，入口名不动
（profile 的 `entrypoints.runner` 指向本函数）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.parkour import config as kit_parkour
from mjlab.rl import RslRlOnPolicyRunnerCfg

from ...profile import GO2_PARKOUR


def unitree_go2_pie_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    """Create the policy, estimator, and PPO settings for Go2 PIE."""
    return kit_parkour.make_runner_cfg(GO2_PARKOUR)
