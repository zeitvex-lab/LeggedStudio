"""Shared agent (RL) configuration for velocity tasks in GenesisLab.

Used by B2, Booster K1/T1, G1, H1 and other robots that do not define their own PPO config.
"""

from .rsl_rl_ppo_cfg import VelocityFlatPPORunnerCfg, VelocityRoughPPORunnerCfg

__all__ = [
    "VelocityFlatPPORunnerCfg",
    "VelocityRoughPPORunnerCfg",
]
