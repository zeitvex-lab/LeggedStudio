# -----------------------------------------------------------------------------
# Subterrain parameter configs (for Genesis gs.morphs.Terrain)
# Each maps to genesis.utils.terrain / isaacgym_terrain_utils params.
# -----------------------------------------------------------------------------
from __future__ import annotations

from typing import Any, Dict, List, Literal, Tuple

from genesislab.utils.configclass import configclass

@configclass
class SubTerrainBaseCfg:
    """Base for subterrain parameter configs. Subclasses provide to_genesis_dict()."""

    def to_genesis_dict(self) -> dict[str, Any]:
        """Return dict suitable for gs.morphs.Terrain subterrain_parameters."""
        return self.to_dict()


@configclass
class FlatSubTerrainCfg(SubTerrainBaseCfg):
    """Flat terrain (no params)."""

    pass


@configclass
class FractalSubTerrainCfg(SubTerrainBaseCfg):
    """Fractal terrain."""

    levels: int = 8
    scale: float = 5.0


@configclass
class RandomUniformSubTerrainCfg(SubTerrainBaseCfg):
    """Random uniform terrain."""

    min_height: float = -0.1
    max_height: float = 0.1
    step: float = 0.1
    downsampled_scale: float = 0.5


@configclass
class SlopedSubTerrainCfg(SubTerrainBaseCfg):
    """Sloped terrain."""

    slope: float = -0.5


@configclass
class PyramidSlopedSubTerrainCfg(SubTerrainBaseCfg):
    """Pyramid sloped terrain."""

    slope: float = -0.1


@configclass
class DiscreteObstaclesSubTerrainCfg(SubTerrainBaseCfg):
    """Discrete obstacles terrain."""

    max_height: float = 0.05
    min_size: float = 1.0
    max_size: float = 5.0
    num_rects: int = 20


@configclass
class WaveSubTerrainCfg(SubTerrainBaseCfg):
    """Wave terrain."""

    num_waves: float = 2.0
    amplitude: float = 0.1


@configclass
class StairsSubTerrainCfg(SubTerrainBaseCfg):
    """Stairs terrain."""

    step_width: float = 0.75
    step_height: float = -0.1


@configclass
class PyramidStairsSubTerrainCfg(SubTerrainBaseCfg):
    """Pyramid stairs terrain."""

    step_width: float = 0.75
    step_height: float = -0.1


@configclass
class SteppingStonesSubTerrainCfg(SubTerrainBaseCfg):
    """Stepping stones terrain."""

    stone_size: float = 1.0
    stone_distance: float = 0.25
    max_height: float = 0.2
    platform_size: float = 0.0


# Genesis subterrain type name -> our config class (for validation / defaults)
SUBTERRAIN_TYPE_TO_CFG = {
    "flat_terrain": FlatSubTerrainCfg,
    "fractal_terrain": FractalSubTerrainCfg,
    "random_uniform_terrain": RandomUniformSubTerrainCfg,
    "sloped_terrain": SlopedSubTerrainCfg,
    "pyramid_sloped_terrain": PyramidSlopedSubTerrainCfg,
    "discrete_obstacles_terrain": DiscreteObstaclesSubTerrainCfg,
    "wave_terrain": WaveSubTerrainCfg,
    "stairs_terrain": StairsSubTerrainCfg,
    "pyramid_stairs_terrain": PyramidStairsSubTerrainCfg,
    "stepping_stones_terrain": SteppingStonesSubTerrainCfg,
}


def subterrain_parameters_to_genesis_dict(
    params: Dict[str, SubTerrainBaseCfg],
) -> dict[str, dict]:
    """Convert configclass subterrain params to dict for gs.morphs.Terrain."""
    return {
        k: v.to_genesis_dict() if isinstance(v, SubTerrainBaseCfg) else v
        for k, v in params.items()
    }