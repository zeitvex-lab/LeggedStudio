"""Model surface for the HIM plugin family (re-exports over the extracted core).

The extracted UniLab files (``actor_critic.py`` / ``estimator.py``) keep their
provenance headers untouched; this module gives the family the standard
``models.py`` face the plugin layout expects.
"""

from __future__ import annotations

from .actor_critic import HIMActorCritic
from .estimator import HIMEstimator, get_activation, sinkhorn

__all__ = [
    "HIMActorCritic",
    "HIMEstimator",
    "get_activation",
    "sinkhorn",
]
