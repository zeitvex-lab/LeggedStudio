"""Package-local Unitree B2 velocity tasks.

Exposes the flat/rough velocity entrypoints consumed by the B2 training
profiles.  All robot and task constants live under this package; nothing is
imported from an external training-source repository.
"""

from .env_cfg import b2_flat_env_cfg, b2_rough_env_cfg, b2_runner_cfg

__all__ = ["b2_flat_env_cfg", "b2_rough_env_cfg", "b2_runner_cfg"]
