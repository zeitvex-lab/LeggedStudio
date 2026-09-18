"""Algorithm surface for the HORA plugin family (re-exports over the core).

The extracted UniLab files (``ppo.py`` et al.) keep their provenance headers
untouched; this module gives the family the standard ``algorithms.py`` face
the plugin layout expects.
"""

from __future__ import annotations

from .ppo import HoraPPO, HoraRolloutStorage, build_hora_ppo

__all__ = [
    "HoraPPO",
    "HoraRolloutStorage",
    "build_hora_ppo",
]
