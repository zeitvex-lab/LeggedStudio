# Copyright (c) 2022-2026, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Converter from GenesisLab ``TerrainGeneratorCfg`` to Genesis-native terrain parameters.

Genesis ships its own procedural terrain generator (``gs.morphs.Terrain``) that accepts a set of
sub-terrain *type strings* and corresponding parameter dicts.  When **all** sub-terrains in a
``TerrainGeneratorCfg`` map to supported Genesis-native types this converter builds the kwargs dict
that can be passed directly to ``gs.morphs.Terrain``, avoiding the heavier trimesh/CPU path.

If *any* sub-terrain is mesh-only (e.g. ``MeshPyramidStairsTerrainCfg``) or uses features that
have no native equivalent, :func:`can_convert` returns ``False`` and the caller must fall back to
the existing ``TerrainGenerator`` mesh path.

Supported native mappings
--------------------------

+--------------------------------------+---------------------------+
| GenesisLab config class              | Genesis sub-terrain type  |
+======================================+===========================+
| HfRandomUniformTerrainCfg            | random_uniform_terrain    |
+--------------------------------------+---------------------------+
| HfPyramidSlopedTerrainCfg            | pyramid_sloped_terrain    |
| HfInvertedPyramidSlopedTerrainCfg    | pyramid_sloped_terrain    |
+--------------------------------------+---------------------------+
| HfPyramidStairsTerrainCfg            | pyramid_stairs_terrain    |
| HfInvertedPyramidStairsTerrainCfg    | pyramid_stairs_terrain    |
+--------------------------------------+---------------------------+
| HfDiscreteObstaclesTerrainCfg        | discrete_obstacles_terrain|
+--------------------------------------+---------------------------+
| HfWaveTerrainCfg                     | wave_terrain              |
+--------------------------------------+---------------------------+
| HfSteppingStonesTerrainCfg           | stepping_stones_terrain   |
+--------------------------------------+---------------------------+
| MeshPlaneTerrainCfg                  | flat_terrain              |
+--------------------------------------+---------------------------+
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .terrain_generator_cfg import TerrainGeneratorCfg
    from .sub_terrain_cfg import SubTerrainBaseCfg

# ---------------------------------------------------------------------------
# Lazy imports – avoid pulling in trimesh / heavy deps at module load time.
# ---------------------------------------------------------------------------


def _hf_cfg_classes() -> tuple:
    """Return HF cfg classes (lazy import to avoid circular deps at module load)."""
    from .height_field.hf_terrains_cfg import (
        HfRandomUniformTerrainCfg,
        HfPyramidSlopedTerrainCfg,
        HfInvertedPyramidSlopedTerrainCfg,
        HfPyramidStairsTerrainCfg,
        HfInvertedPyramidStairsTerrainCfg,
        HfDiscreteObstaclesTerrainCfg,
        HfWaveTerrainCfg,
        HfSteppingStonesTerrainCfg,
    )

    return (
        HfRandomUniformTerrainCfg,
        HfPyramidSlopedTerrainCfg,
        HfInvertedPyramidSlopedTerrainCfg,
        HfPyramidStairsTerrainCfg,
        HfInvertedPyramidStairsTerrainCfg,
        HfDiscreteObstaclesTerrainCfg,
        HfWaveTerrainCfg,
        HfSteppingStonesTerrainCfg,
    )


def _mesh_plane_cfg_class():
    """Return MeshPlaneTerrainCfg (lazy import)."""
    from .trimesh.mesh_terrains_cfg import MeshPlaneTerrainCfg

    return MeshPlaneTerrainCfg


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def can_convert(gen_cfg: "TerrainGeneratorCfg") -> bool:
    """Return ``True`` if *all* sub-terrains in *gen_cfg* have a native Genesis equivalent.

    Args:
        gen_cfg: The :class:`~genesislab.components.terrains.TerrainGeneratorCfg` to inspect.

    Returns:
        ``True`` when every sub-terrain can be converted to a Genesis-native type; ``False``
        otherwise (caller should fall back to the mesh-based ``TerrainGenerator`` path).
    """
    hf_classes = _hf_cfg_classes()
    mesh_plane_cls = _mesh_plane_cfg_class()
    supported = hf_classes + (mesh_plane_cls,)

    for name, sub_cfg in gen_cfg.sub_terrains.items():
        if not isinstance(sub_cfg, supported):
            return False
    return True


def convert(gen_cfg: "TerrainGeneratorCfg") -> dict:
    """Convert *gen_cfg* to a kwargs dict for ``gs.morphs.Terrain``.

    This function assumes :func:`can_convert` returned ``True``.  Calling it when
    ``can_convert`` is ``False`` will raise a :class:`TypeError`.

    Args:
        gen_cfg: The terrain generator configuration to convert.

    Returns:
        A dict with keys accepted by ``gs.morphs.Terrain``:
        ``n_subterrains``, ``subterrain_size``, ``horizontal_scale``,
        ``vertical_scale``, ``subterrain_types``, ``subterrain_parameters``.

    Raises:
        TypeError: If any sub-terrain cannot be mapped to a native Genesis type.
    """
    # Collect (type_string, params_dict) for each sub-terrain definition.
    type_params: list[tuple[str, dict]] = []
    for sub_name, sub_cfg in gen_cfg.sub_terrains.items():
        gs_type, gs_params = _convert_sub_terrain(sub_cfg, gen_cfg)
        type_params.append((gs_type, gs_params))

    # Genesis expects:
    #   subterrain_types: 2D list[list[str]] of shape (num_rows, num_cols).
    #   subterrain_parameters: dict[str, dict] keyed by terrain type string.
    #
    # We cycle through the defined sub-terrain types to tile the (num_rows × num_cols) grid,
    # and collect per-type params into a single dict (last-writer-wins for duplicate types).
    num_types = len(type_params)
    subterrain_types_2d: list[list[str]] = []
    subterrain_parameters: dict[str, dict] = {}

    for row in range(gen_cfg.num_rows):
        row_types: list[str] = []
        for col in range(gen_cfg.num_cols):
            idx = (row * gen_cfg.num_cols + col) % num_types
            gs_type, gs_params = type_params[idx]
            row_types.append(gs_type)
            # Merge params for this type (each type key holds one params dict).
            if gs_type not in subterrain_parameters:
                subterrain_parameters[gs_type] = gs_params
        subterrain_types_2d.append(row_types)

    return {
        "n_subterrains": (gen_cfg.num_rows, gen_cfg.num_cols),
        "subterrain_size": gen_cfg.size,
        "horizontal_scale": gen_cfg.horizontal_scale,
        "vertical_scale": gen_cfg.vertical_scale,
        "subterrain_types": subterrain_types_2d,
        "subterrain_parameters": subterrain_parameters,
    }

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _convert_sub_terrain(
    sub_cfg: "SubTerrainBaseCfg",
    gen_cfg: "TerrainGeneratorCfg",
) -> tuple[str, dict]:
    """Convert a single sub-terrain config to a (genesis_type_string, params_dict) pair.

    Args:
        sub_cfg: The sub-terrain configuration to convert.
        gen_cfg: Parent generator config (supplies shared scale values).

    Returns:
        Tuple of (genesis_type_string, params_dict).

    Raises:
        TypeError: If *sub_cfg* has no known native mapping.
    """
    (
        HfRandomUniformTerrainCfg,
        HfPyramidSlopedTerrainCfg,
        HfInvertedPyramidSlopedTerrainCfg,
        HfPyramidStairsTerrainCfg,
        HfInvertedPyramidStairsTerrainCfg,
        HfDiscreteObstaclesTerrainCfg,
        HfWaveTerrainCfg,
        HfSteppingStonesTerrainCfg,
    ) = _hf_cfg_classes()
    MeshPlaneTerrainCfg = _mesh_plane_cfg_class()

    if isinstance(sub_cfg, MeshPlaneTerrainCfg):
        return "flat_terrain", {}

    if isinstance(sub_cfg, HfRandomUniformTerrainCfg):
        return "random_uniform_terrain", {
            "min_height": sub_cfg.noise_range[0],
            "max_height": sub_cfg.noise_range[1],
            "step": sub_cfg.noise_step,
            "downsampled_scale": sub_cfg.downsampled_scale,
        }

    if isinstance(
        sub_cfg, (HfPyramidSlopedTerrainCfg, HfInvertedPyramidSlopedTerrainCfg)
    ):
        # Use midpoint of slope_range as the representative slope value.
        slope = statistics.mean(sub_cfg.slope_range)
        return "pyramid_sloped_terrain", {
            "slope": slope,
            "platform_size": sub_cfg.platform_width,
            "inverted": sub_cfg.inverted,
        }

    if isinstance(
        sub_cfg, (HfPyramidStairsTerrainCfg, HfInvertedPyramidStairsTerrainCfg)
    ):
        step_height = statistics.mean(sub_cfg.step_height_range)
        return "pyramid_stairs_terrain", {
            "step_width": sub_cfg.step_width,
            "step_height": step_height,
            "platform_size": sub_cfg.platform_width,
            "inverted": sub_cfg.inverted,
        }

    if isinstance(sub_cfg, HfDiscreteObstaclesTerrainCfg):
        return "discrete_obstacles_terrain", {
            "obstacle_height_min": sub_cfg.obstacle_height_range[0],
            "obstacle_height_max": sub_cfg.obstacle_height_range[1],
            "obstacle_width_min": sub_cfg.obstacle_width_range[0],
            "obstacle_width_max": sub_cfg.obstacle_width_range[1],
            "num_obstacles": sub_cfg.num_obstacles,
            "platform_size": sub_cfg.platform_width,
        }

    if isinstance(sub_cfg, HfWaveTerrainCfg):
        amplitude = statistics.mean(sub_cfg.amplitude_range)
        return "wave_terrain", {
            "amplitude": amplitude,
            "num_waves": sub_cfg.num_waves,
        }

    if isinstance(sub_cfg, HfSteppingStonesTerrainCfg):
        stone_width = statistics.mean(sub_cfg.stone_width_range)
        stone_distance = statistics.mean(sub_cfg.stone_distance_range)
        return "stepping_stones_terrain", {
            "stone_size": stone_width,
            "stone_distance": stone_distance,
            "max_height": sub_cfg.stone_height_max,
            "platform_size": sub_cfg.platform_width,
            "depth": sub_cfg.holes_depth,
        }

    raise TypeError(
        f"Sub-terrain config '{type(sub_cfg).__name__}' has no Genesis-native mapping. "
        "Use TerrainGenerator (mesh path) instead, or add a mapping to "
        "genesis_terrain_converter.py."
    )
