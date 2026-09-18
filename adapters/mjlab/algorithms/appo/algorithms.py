"""Algorithm surface for the APPO plugin family (re-exports over the core).

The extracted UniLab file (``learner.py``) keeps its provenance header
untouched; this module gives the family the standard ``algorithms.py`` face
the plugin layout expects.
"""

from __future__ import annotations

from .learner import APPOLearner, vtrace_advantages

__all__ = [
    "APPOLearner",
    "vtrace_advantages",
]
