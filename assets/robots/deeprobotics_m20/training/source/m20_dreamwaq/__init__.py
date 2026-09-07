"""DreamWaQ wheel-legged (Deeprobotics M20) training task.

Package-local DreamWaQ port (see config.py module docstring for the source
fidelity notes).  Exposes the flat/rough env factories and the runner config
consumed by the M20 training profiles.
"""

from .config import make_m20_dreamwaq_env_cfg, make_m20_dreamwaq_runner_cfg

__all__ = ["make_m20_dreamwaq_env_cfg", "make_m20_dreamwaq_runner_cfg"]
