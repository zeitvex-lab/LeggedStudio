"""Package-local LimX TRON1 wheel-foot velocity tasks.

Exposes the flat velocity entrypoint consumed by the WF training profile.
All robot and task constants live under this package; nothing is imported
from an external training-source repository.
"""

from .env_cfg import wf_flat_env_cfg, wf_runner_cfg

__all__ = ["wf_flat_env_cfg", "wf_runner_cfg"]
