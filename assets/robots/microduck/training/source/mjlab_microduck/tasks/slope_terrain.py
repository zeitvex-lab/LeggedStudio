"""Terrain custom « plat + rampe descendante » pour la tâche roller_slope.

Le robot spawne sur une zone plate, reçoit une impulsion vers +x, roule
jusqu'à la rampe et se laisse glisser. L'angle de la rampe est interpolé par
la difficulté (curriculum) sur [RAMP_DEG_MIN, RAMP_DEG_MAX] degrés.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import mujoco
import numpy as np

from mjlab.terrains.terrain_generator import (
    SubTerrainCfg,
    TerrainGeometry,
    TerrainOutput,
)

RAMP_DEG_MIN = 2.0
RAMP_DEG_MAX = 20.0


def ramp_angle_by_difficulty(
    difficulty: float, deg_min: float = RAMP_DEG_MIN, deg_max: float = RAMP_DEG_MAX
) -> float:
    """Angle de rampe (radians) interpolé linéairement par la difficulté [0,1]."""
    d = float(np.clip(difficulty, 0.0, 1.0))
    return math.radians(deg_min + d * (deg_max - deg_min))


