"""Package-owned entrypoints for the LLoco Go2 training profiles.

The native worker loads these functions through the package manifest. Keeping
the wrappers no-argument makes the package profile contract independent from
the Web API while preserving LLoco's task and runner configuration.
"""

from __future__ import annotations

# Register this package's Go2 asset symbols before task modules import them.
from . import mjlab_extension as _mjlab_extension

_mjlab_extension.register()

from .robots.unitree.go2.tasks.aerial.config import (
    unitree_go2_backflip_env_cfg,
    unitree_go2_jump_env_cfg,
    unitree_go2_spring_jump_env_cfg,
)
from .robots.unitree.go2.tasks.balance.config import (
    unitree_go2_handstand_env_cfg,
    unitree_go2_leggedstand_env_cfg,
)
from .robots.unitree.go2.tasks.locomotion.trot import unitree_go2_trot_env_cfg
from .robots.unitree.go2.tasks.locomotion.velocity import (
    unitree_go2_flat_env_cfg,
    unitree_go2_rough_env_cfg,
)
from .robots.unitree.go2.training.config import unitree_go2_source_ppo_runner_cfg


def flat_env_cfg(*, play: bool = False):
    return unitree_go2_flat_env_cfg(play=play)


def rough_env_cfg(*, play: bool = False):
    return unitree_go2_rough_env_cfg(play=play)


def trot_env_cfg(*, play: bool = False):
    return unitree_go2_trot_env_cfg(play=play)


def jump_env_cfg(*, play: bool = False):
    return unitree_go2_jump_env_cfg(play=play)


def spring_jump_env_cfg(*, play: bool = False):
    return unitree_go2_spring_jump_env_cfg(play=play)


def backflip_env_cfg(*, play: bool = False):
    return unitree_go2_backflip_env_cfg(play=play)


def handstand_env_cfg(*, play: bool = False):
    return unitree_go2_handstand_env_cfg(play=play)


def leggedstand_env_cfg(*, play: bool = False):
    return unitree_go2_leggedstand_env_cfg(play=play)


def flat_ppo_runner_cfg():
    return unitree_go2_source_ppo_runner_cfg(
        learning_rate=1.0e-3, max_iterations=15_000, save_interval=100, seed=1
    )


def rough_ppo_runner_cfg():
    return unitree_go2_source_ppo_runner_cfg(
        learning_rate=1.0e-3, max_iterations=15_000, save_interval=100, seed=1
    )


def trot_ppo_runner_cfg():
    return unitree_go2_source_ppo_runner_cfg(
        learning_rate=1.0e-5,
        max_iterations=15_000,
        save_interval=100,
        seed=1,
        symmetry_func="lainloco.learning.symmetry.trot_jump_symmetry",
    )


def jump_ppo_runner_cfg():
    return unitree_go2_source_ppo_runner_cfg(
        learning_rate=1.0e-4,
        max_iterations=15_000,
        save_interval=100,
        seed=1,
        symmetry_func="lainloco.learning.symmetry.trot_jump_symmetry",
    )


def spring_jump_ppo_runner_cfg():
    return unitree_go2_source_ppo_runner_cfg(
        learning_rate=1.0e-5,
        max_iterations=50_000,
        save_interval=100,
        seed=1,
        symmetry_func="lainloco.learning.symmetry.spring_jump_symmetry",
    )


def backflip_ppo_runner_cfg():
    return unitree_go2_source_ppo_runner_cfg(
        learning_rate=1.0e-5, max_iterations=50_000, save_interval=100, seed=1
    )


def handstand_ppo_runner_cfg():
    return unitree_go2_source_ppo_runner_cfg(
        learning_rate=1.0e-3, max_iterations=15_000, save_interval=100, seed=1
    )


def leggedstand_ppo_runner_cfg():
    return unitree_go2_source_ppo_runner_cfg(
        learning_rate=1.0e-3, max_iterations=15_000, save_interval=100, seed=1
    )
