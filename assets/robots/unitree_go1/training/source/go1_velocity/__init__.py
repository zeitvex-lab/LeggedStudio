"""Package-local Unitree Go1 velocity task.

Exposes the flat velocity entrypoint consumed by the go1 training profile.
All robot and task constants live under this package; the upstream training
reference (HIMLoco / walk-these-ways) is read-only evidence under
00_resources/, not imported at runtime.
"""

from .env_cfg import go1_flat_env_cfg, go1_runner_cfg

__all__ = ["go1_flat_env_cfg", "go1_runner_cfg"]
