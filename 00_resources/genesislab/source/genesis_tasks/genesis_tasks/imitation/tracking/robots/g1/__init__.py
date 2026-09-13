"""G1 BeyondMimic whole-body tracking task registration for GenesisLab."""

from __future__ import annotations

import gymnasium as gym

from genesis_tasks.imitation.tracking import agents as tracking_agents
from .g1_tracking_env_cfg import (
    G1FlatEnvCfg,
    G1FlatWoStateEstimationEnvCfg,
    G1FlatLowFreqEnvCfg,
)

__all__ = [
    "G1FlatEnvCfg",
    "G1FlatWoStateEstimationEnvCfg",
    "G1FlatLowFreqEnvCfg",
]


# Flat tracking with full observations
gym.register(
    id="Genesis-Tracking-Flat-G1-v0",
    entry_point="genesislab.envs:ManagerBasedRlEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_tracking_env_cfg:G1FlatEnvCfg",
        "rsl_rl_cfg_entry_point": tracking_agents.TrackingPPORunnerCfg(
            experiment_name="g1_tracking_flat"
        ),
    },
)


# Flat tracking without state-estimation-related observations
gym.register(
    id="Genesis-Tracking-Flat-G1-Wo-State-Estimation-v0",
    entry_point="genesislab.envs:ManagerBasedRlEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_tracking_env_cfg:G1FlatWoStateEstimationEnvCfg",
        "rsl_rl_cfg_entry_point": tracking_agents.TrackingPPORunnerCfg(
            experiment_name="g1_tracking_flat_wo_state"
        ),
    },
)


# Flat tracking at lower control frequency
gym.register(
    id="Genesis-Tracking-Flat-G1-Low-Freq-v0",
    entry_point="genesislab.envs:ManagerBasedRlEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_tracking_env_cfg:G1FlatLowFreqEnvCfg",
        "rsl_rl_cfg_entry_point": tracking_agents.TrackingPPORunnerCfg(
            experiment_name="g1_tracking_flat_low_freq"
        ),
    },
)

