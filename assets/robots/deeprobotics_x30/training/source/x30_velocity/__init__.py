"""Package-local Deeprobotics X30 velocity tasks.

Exposes the flat/rough velocity entrypoints consumed by the B2 training
profiles.  All robot and task constants live under this package; nothing is
imported from an external training-source repository.
"""

from .env_cfg import x30_flat_env_cfg, x30_rough_env_cfg, x30_runner_cfg

__all__ = ["x30_flat_env_cfg", "x30_rough_env_cfg", "x30_runner_cfg"]
