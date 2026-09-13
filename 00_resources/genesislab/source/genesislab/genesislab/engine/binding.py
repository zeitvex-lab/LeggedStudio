"""GenesisBinding: Engine binding wrapper for GenesisLab.

This module provides the GenesisBinding class that wraps the LabScene
and related components to provide a unified interface for engine operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:
    from genesislab.components.entities.scene_cfg import SceneCfg


class GenesisBinding:
    """Unified engine binding for GenesisLab.

    This class wraps LabScene and provides a simplified interface for
    scene management, state queries, and physics control.
    """

    def __init__(self, cfg: "SceneCfg", device: str = "cuda"):
        """Initialize the Genesis binding.

        Args:
            cfg: Scene configuration.
            device: Device to use for tensors ('cuda' or 'cpu').
        """
        from genesislab.engine.scene.lab_scene import LabScene

        self._scene = LabScene(cfg, device=device)
        self._device = device

    @property
    def num_envs(self) -> int:
        """Number of parallel environments."""
        return self._scene.num_envs

    @property
    def device(self) -> str:
        """Device being used."""
        return self._device

    def build(self, env: any = None) -> None:
        """Build the Genesis scene and entities.

        Args:
            env: Optional environment instance for entity construction.
        """
        self._scene.build(env=env)

    def get_joint_state(self, entity_name: str) -> tuple[torch.Tensor, torch.Tensor]:
        """Get joint positions and velocities for an entity.

        Args:
            entity_name: Name of the entity.

        Returns:
            Tuple of (positions, velocities) tensors.
        """
        return self._scene.querier.get_joint_state(entity_name)

    def get_root_state(
        self, entity_name: str
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Get root pose and velocity for an entity.

        Args:
            entity_name: Name of the entity.

        Returns:
            Tuple of (position, quaternion, linear_velocity, angular_velocity).
        """
        return self._scene.querier.get_root_state(entity_name)

    def step(self) -> None:
        """Step the physics simulation by one timestep."""
        self._scene.controller.step()

    def reset(self, env_ids: torch.Tensor = None) -> None:
        """Reset specified environments to initial state.

        Args:
            env_ids: Environment indices to reset. If None, resets all.
        """
        self._scene.controller.reset(env_ids=env_ids)

    def set_joint_targets(
        self,
        entity_name: str,
        targets: torch.Tensor,
        control_type: str = "position",
    ) -> None:
        """Set joint control targets for an entity.

        Args:
            entity_name: Name of the entity.
            targets: Target values.
            control_type: Type of control ('position', 'velocity', or 'torque').
        """
        self._scene.controller.set_joint_targets(entity_name, targets, control_type)

    @property
    def scene(self) -> "LabScene":
        """Access the underlying LabScene instance."""
        return self._scene
