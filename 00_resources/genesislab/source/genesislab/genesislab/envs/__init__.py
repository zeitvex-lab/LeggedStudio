"""Environment definitions for GenesisLab.

Environments define the interface between RL agents and the Genesis-based
simulation. GenesisLab currently focuses on the manager-based workflow:

- A scene management layer over Genesis `Scene` (see :mod:`genesislab.engine.scene`).
- A manager-based environment core (see :mod:`genesislab.envs.base_env`).
- A stack of managers for observations, rewards, actions, terminations, etc.

Over time, this subpackage can be extended with direct (non-manager) envs and
multi-agent variants, mirroring IsaacLab's structure.
"""

from .common import VecEnvObs, VecEnvStepReturn, ViewerCfg
from .manager_based_genesis_env import ManagerBasedGenesisEnv
from .manager_based_rl_env import ManagerBasedRlEnv, ManagerBasedRlEnvCfg

__all__ = [
    "ManagerBasedGenesisEnv",
    "ManagerBasedRlEnv",
    "ManagerBasedRlEnvCfg",
    "VecEnvObs",
    "VecEnvStepReturn",
    "ViewerCfg",
]

