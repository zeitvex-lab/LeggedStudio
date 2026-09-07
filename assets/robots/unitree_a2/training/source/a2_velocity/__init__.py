"""Package-local Unitree A2 velocity tasks.

Exposes the flat/rough velocity entrypoints consumed by the A2 training
profiles.  All robot and task constants live under this package; nothing is
imported from an external training-source repository.
"""

from .env_cfg import a2_flat_env_cfg, a2_rough_env_cfg, a2_runner_cfg

__all__ = ["a2_flat_env_cfg", "a2_rough_env_cfg", "a2_runner_cfg"]
