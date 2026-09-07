"""Package-local Agibot D1 velocity tasks.

Exposes the flat/rough velocity entrypoints consumed by the B2 training
profiles.  All robot and task constants live under this package; nothing is
imported from an external training-source repository.
"""

from .env_cfg import d1_flat_env_cfg, d1_rough_env_cfg, d1_runner_cfg

__all__ = ["d1_flat_env_cfg", "d1_rough_env_cfg", "d1_runner_cfg"]
