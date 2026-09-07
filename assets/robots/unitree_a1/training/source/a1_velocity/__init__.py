"""Package-local Unitree A1 velocity tasks.

Exposes the flat/rough velocity entrypoints consumed by the B2 training
profiles.  All robot and task constants live under this package; nothing is
imported from an external training-source repository.
"""

from .env_cfg import a1_flat_env_cfg, a1_rough_env_cfg, a1_runner_cfg

__all__ = ["a1_flat_env_cfg", "a1_rough_env_cfg", "a1_runner_cfg"]
