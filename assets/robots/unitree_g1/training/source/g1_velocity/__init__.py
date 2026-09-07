"""Unitree G1 velocity tasks (package-local).

Thin entrypoints over mjlab's built-in G1 velocity configurations.  All
robot and task constants live in the shared mjlab distribution; this module
only exposes the no-argument factories the package profile contract needs.
"""

from mjlab.tasks.velocity.config.g1.env_cfgs import (
    unitree_g1_flat_env_cfg as _flat_env_cfg,
)
from mjlab.tasks.velocity.config.g1.env_cfgs import (
    unitree_g1_rough_env_cfg as _rough_env_cfg,
)
from mjlab.tasks.velocity.config.g1.rl_cfg import (
    unitree_g1_ppo_runner_cfg as _ppo_runner_cfg,
)


def g1_flat_env_cfg(*, play: bool = False):
    return _flat_env_cfg(play=play)


def g1_rough_env_cfg(*, play: bool = False):
    return _rough_env_cfg(play=play)


def g1_runner_cfg():
    return _ppo_runner_cfg()


__all__ = ["g1_flat_env_cfg", "g1_rough_env_cfg", "g1_runner_cfg"]
