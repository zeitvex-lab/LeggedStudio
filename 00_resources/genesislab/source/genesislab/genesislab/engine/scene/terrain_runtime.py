"""Lightweight terrain runtime state for GenesisLab.

This module provides :class:`TerrainRuntime`, which holds the runtime state
produced by terrain generation (environment origins, terrain levels, etc.)
without depending on IsaacLab's ``TerrainImporter`` or ``SimulationContext``.

The class is intentionally thin: it stores the tensors that the curriculum
system and environment reset logic need, and provides the
:meth:`update_env_origins` method used by ``terrain_levels_vel`` in
``curriculums.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import torch

if TYPE_CHECKING:
    from genesislab.components.terrains.terrain_generator_cfg import TerrainGeneratorCfg

logger = logging.getLogger(__name__)


class TerrainRuntime:
    """Runtime state for procedurally generated terrain.

    This object is created by :meth:`SceneBuilder.add_terrain` when the
    terrain mode is ``"generator"`` and is stored on :class:`LabScene` as
    ``scene.terrain``.

    It mirrors the subset of :class:`TerrainImporter` that downstream code
    (curriculum terms, environment resets) depends on:

    * ``terrain_generator``  — reference to the generator config
    * ``terrain_origins``    — sub-terrain origins ``(num_rows, num_cols, 3)``
    * ``env_origins``        — per-environment origins ``(num_envs, 3)``
    * ``terrain_levels``     — current terrain level per environment
    * ``terrain_types``      — terrain type index per environment
    * ``max_terrain_level``  — maximum level value
    * ``update_env_origins`` — method to advance curriculum levels
    """

    terrain_origins: torch.Tensor | None
    """Sub-terrain origins.  Shape ``(num_rows, num_cols, 3)``."""

    env_origins: torch.Tensor
    """Per-environment origins.  Shape ``(num_envs, 3)``."""

    terrain_levels: torch.Tensor | None
    """Current terrain level per environment.  Shape ``(num_envs,)``."""

    terrain_types: torch.Tensor | None
    """Terrain type index per environment.  Shape ``(num_envs,)``."""

    max_terrain_level: int | None
    """Maximum terrain level (equal to ``num_rows``)."""

    def __init__(
        self,
        terrain_generator: TerrainGeneratorCfg | None,
        terrain_origins: np.ndarray | torch.Tensor | None,
        num_envs: int,
        env_spacing: float | None,
        max_init_terrain_level: int | None,
        device: str = "cpu",
    ) -> None:
        """Initialize the terrain runtime.

        Args:
            terrain_generator: The generator config (stored for downstream
                access by curriculum terms and env configs).
            terrain_origins: Sub-terrain origins produced by
                :class:`TerrainGenerator`.  Shape ``(num_rows, num_cols, 3)``.
                ``None`` when origins should be computed from a uniform grid.
            num_envs: Number of parallel environments.
            env_spacing: Grid spacing used when *terrain_origins* is ``None``.
            max_init_terrain_level: Maximum initial terrain level.  If ``None``
                the maximum available level is used.
            device: Torch device string.
        """
        self.terrain_generator = terrain_generator
        self.device = device

        if terrain_origins is not None:
            if isinstance(terrain_origins, np.ndarray):
                terrain_origins = torch.from_numpy(terrain_origins)
            self.terrain_origins = terrain_origins.to(device, dtype=torch.float)
            self.env_origins = self._compute_env_origins_curriculum(
                num_envs,
                self.terrain_origins,
                max_init_terrain_level,
            )
        else:
            self.terrain_origins = None
            self.terrain_levels = None
            self.terrain_types = None
            self.max_terrain_level = None
            if env_spacing is None:
                raise ValueError(
                    "env_spacing must be specified when terrain_origins is None."
                )
            self.env_origins = self._compute_env_origins_grid(num_envs, env_spacing)

    # ------------------------------------------------------------------
    # Curriculum update
    # ------------------------------------------------------------------

    def update_env_origins(
        self,
        env_ids: torch.Tensor,
        move_up: torch.Tensor,
        move_down: torch.Tensor,
    ) -> None:
        """Update environment origins based on curriculum terrain levels.

        Mirrors :meth:`TerrainImporter.update_env_origins`.

        Args:
            env_ids: Indices of environments to update.
            move_up: Boolean mask — environments that should progress.
            move_down: Boolean mask — environments that should regress.
        """
        if self.terrain_origins is None:
            return

        self.terrain_levels[env_ids] += 1 * move_up - 1 * move_down
        # Robots that solve the last level are sent to a random one.
        # The minimum level is zero.
        self.terrain_levels[env_ids] = torch.where(
            self.terrain_levels[env_ids] >= self.max_terrain_level,
            torch.randint_like(self.terrain_levels[env_ids], self.max_terrain_level),
            torch.clip(self.terrain_levels[env_ids], 0),
        )
        self.env_origins[env_ids] = self.terrain_origins[
            self.terrain_levels[env_ids], self.terrain_types[env_ids]
        ]

    # ------------------------------------------------------------------
    # Internal helpers (ported from TerrainImporter)
    # ------------------------------------------------------------------

    def _compute_env_origins_curriculum(
        self,
        num_envs: int,
        origins: torch.Tensor,
        max_init_terrain_level: int | None,
    ) -> torch.Tensor:
        """Compute environment origins from sub-terrain origins (curriculum)."""
        num_rows, num_cols = origins.shape[:2]

        if max_init_terrain_level is None:
            max_init_level = num_rows - 1
        else:
            max_init_level = min(max_init_terrain_level, num_rows - 1)

        self.max_terrain_level = num_rows
        self.terrain_levels = torch.randint(
            0,
            max_init_level + 1,
            (num_envs,),
            device=self.device,
        )
        self.terrain_types = torch.div(
            torch.arange(num_envs, device=self.device),
            (num_envs / num_cols),
            rounding_mode="floor",
        ).to(torch.long)

        env_origins = torch.zeros(num_envs, 3, device=self.device)
        env_origins[:] = origins[self.terrain_levels, self.terrain_types]
        return env_origins

    def _compute_env_origins_grid(
        self,
        num_envs: int,
        env_spacing: float,
    ) -> torch.Tensor:
        """Compute environment origins in a uniform grid."""
        env_origins = torch.zeros(num_envs, 3, device=self.device)
        num_rows = int(np.ceil(num_envs / int(np.sqrt(num_envs))))
        num_cols = int(np.ceil(num_envs / num_rows))
        ii, jj = torch.meshgrid(
            torch.arange(num_rows, device=self.device),
            torch.arange(num_cols, device=self.device),
            indexing="ij",
        )
        env_origins[:, 0] = (
            -(ii.flatten()[:num_envs] - (num_rows - 1) / 2) * env_spacing
        )
        env_origins[:, 1] = (jj.flatten()[:num_envs] - (num_cols - 1) / 2) * env_spacing
        env_origins[:, 2] = 0.0
        return env_origins
