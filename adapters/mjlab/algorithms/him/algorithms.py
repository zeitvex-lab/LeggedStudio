"""Algorithm surface for the HIM plugin family (re-exports over the core).

The extracted UniLab file (``algorithm.py``, singular — upstream file name)
keeps its provenance header untouched; this module gives the family the
standard plural ``algorithms.py`` face the plugin layout expects.
"""

from __future__ import annotations

from .algorithm import HIMPPO

__all__ = [
    "HIMPPO",
]
