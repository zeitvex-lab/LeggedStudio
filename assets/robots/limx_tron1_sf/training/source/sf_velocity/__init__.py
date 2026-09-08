"""Package-local LimX TRON1 sole-foot velocity tasks.

Exposes the flat velocity entrypoint consumed by the SF training profile.
All robot and task constants live under this package; nothing is imported
from an external training-source repository.
"""

from .env_cfg import sf_flat_env_cfg, sf_runner_cfg

__all__ = ["sf_flat_env_cfg", "sf_runner_cfg"]
