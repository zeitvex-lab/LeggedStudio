"""Package-local Deeprobotics Lite3 velocity tasks.

Exposes the flat/rough velocity entrypoints consumed by the B2 training
profiles.  All robot and task constants live under this package; nothing is
imported from an external training-source repository.
"""

from .env_cfg import (
    lite3_flat_env_cfg,
    lite3_rough_env_cfg,
    lite3_runner_cfg,
    make_lite3_flat_env_cfg,
    make_lite3_rough_env_cfg,
)

__all__ = [
    "lite3_flat_env_cfg",
    "lite3_rough_env_cfg",
    "lite3_runner_cfg",
    "make_lite3_flat_env_cfg",
    "make_lite3_rough_env_cfg",
]
