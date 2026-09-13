"""Genesis-native asset abstractions for GenesisLab.

This subpackage provides lightweight asset wrappers built directly on top of
the Genesis Python API (``genesis as gs``). These assets are designed to be
backend-agnostic from the perspective of GenesisLab environments while
remaining fully compatible with the batched, multi-environment execution
model used by Genesis.

The goal is to mirror the high-level interface and configuration style of
the IsaacLab ``components.assets`` layer, but without any dependency on
Omniverse, USD, or Isaac Sim. Instead, assets here operate on already-built
Genesis scenes and entities.

Currently, this package focuses on rigid-body articulations (robots) and
simple terrain or rigid objects can be added incrementally as needed.
"""

from .lab_asset_base import LabAssetBase
from .articulation import Articulation, ArticulationCfg
from .robot import Robot

__all__ = [
    "LabAssetBase",
    "Articulation",
    "ArticulationCfg",
    "Robot",
]

