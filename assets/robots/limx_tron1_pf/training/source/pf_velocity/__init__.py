"""Package-local LimX TRON1 point-foot velocity tasks.

Exposes the flat velocity entrypoint consumed by the PF training profile.
All robot and task constants live under this package; nothing is imported
from an external training-source repository.
"""

from .env_cfg import pf_flat_env_cfg, pf_runner_cfg

__all__ = ["pf_flat_env_cfg", "pf_runner_cfg"]
