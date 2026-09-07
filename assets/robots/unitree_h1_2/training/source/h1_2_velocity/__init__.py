"""Package-local Unitree H1_2 velocity tasks.

Exposes the flat/rough velocity entrypoints consumed by the H1_2 training
profiles.  All robot and task constants live under this package; nothing is
imported from an external training-source repository.
"""

from .env_cfg import h1_2_flat_env_cfg, h1_2_rough_env_cfg, h1_2_runner_cfg

__all__ = ["h1_2_flat_env_cfg", "h1_2_rough_env_cfg", "h1_2_runner_cfg"]
