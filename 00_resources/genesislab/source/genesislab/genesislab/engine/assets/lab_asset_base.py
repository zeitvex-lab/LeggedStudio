"""Base interfaces for Genesis-native assets.

These assets are small, composable wrappers around Genesis entities that
provide a stable, RL-friendly API while remaining fully batched over
``num_envs`` parallel environments.

Design goals
------------
* Keep the interface conceptually similar to ``components.assets.AssetBase``
  (reset, update, write-to-sim style), but:
  - Do not depend on Omniverse / USD / Isaac Sim.
  - Operate purely on ``genesis as gs`` entities and tensors.
* Be minimal: only the functionality required by current RL use-cases
  is implemented. Additional helpers can be layered on incrementally.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence

import torch

import genesis as gs


class LabAssetBase(ABC):
    """Abstract base class for Genesis-native assets.

    An asset is a lightweight wrapper around one or more Genesis entities
    (for example, an articulated robot). All operations are expected to be
    batched over the ``num_envs`` environments of the underlying ``gs.Scene``.
    """

    def __init__(self, name: str):
        """Construct the base asset wrapper.

        Parameters
        ----------
        name:
            Logical name of the asset within the scene / environment.
        """
        self._name = name

    # --------------------------------------------------------------------- #
    # Properties
    # --------------------------------------------------------------------- #
    @property
    def name(self) -> str:
        """Logical name of the asset."""

        return self._name

    # --------------------------------------------------------------------- #
    # Core operations
    # --------------------------------------------------------------------- #
    @abstractmethod
    def build_into_scene(self, scene: gs.Scene) -> Any:
        """Instantiate the underlying Genesis entity in the given scene.

        This method should:
        1. Construct the appropriate ``gs.morphs.*`` instance(s).
        2. Add them to the scene via :meth:`scene.add_entity`.
        3. Store any handles needed for later control or state queries.

        It must be called before any of the runtime methods (reset, update,
        write_to_sim, etc.) are used.

        Parameters
        ----------
        scene:
            The Genesis scene to which the asset should be added.

        Returns
        -------
        Any
            The primary Genesis entity (or a small struct / dict of entities)
            associated with this asset.
        """

    @abstractmethod
    def reset(self, env_ids: Sequence[int] | torch.Tensor = None) -> None:
        """Reset the asset state in the selected environments.

        Parameters
        ----------
        env_ids:
            Indices of the environments to reset. If ``None``, all environments
            are reset.
        """

    @abstractmethod
    def write_data_to_sim(self) -> None:
        """Write any buffered control targets into the Genesis simulation."""

    @abstractmethod
    def update(self, dt: float) -> None:
        """Update internal state buffers after a simulation step.

        Parameters
        ----------
        dt:
            Simulation timestep in seconds.
        """

