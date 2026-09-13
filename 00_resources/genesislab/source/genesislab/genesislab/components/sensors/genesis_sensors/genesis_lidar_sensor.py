"""LiDAR sensor wrapper over ``gs.sensors.Lidar``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import torch

from genesislab.utils.configclass import configclass
from .sensor_base import GenesisSensorBase, GenesisSensorBaseCfg
from .genesis_sensor_utils import to_tensor, resolve_entity_idx
from .genesis_sensor_types import GenesisLidarSensorHandle

if TYPE_CHECKING:
    import genesis as gs
    from genesislab.engine.scene.lab_scene import LabScene


class GenesisLidarSensor(GenesisSensorBase):
    """LiDAR sensor backed by ``gs.sensors.Lidar``.

    Exposes point cloud and distance tensors from the underlying Genesis sensor.
    """

    @dataclass
    class Data:
        """Exposed buffers.

        Attributes:
            points: Tensor of shape (num_envs, H, V, 3) or (H, V, 3).
            distances: Tensor of shape (num_envs, H, V) or (H, V).
        """

        points: torch.Tensor
        distances: torch.Tensor

    def __init__(
        self,
        cfg: "GenesisLidarSensorCfg",
        num_envs: int,
        device: str = "cuda",
        genesis_sensor: GenesisLidarSensorHandle = None,
    ) -> None:
        self._gs_sensor: GenesisLidarSensorHandle = genesis_sensor
        super().__init__(cfg=cfg, num_envs=num_envs, device=device)

    def set_genesis_sensor(self, genesis_sensor: GenesisLidarSensorHandle) -> None:
        """Attach the underlying Genesis ``Lidar`` sensor."""
        self._gs_sensor = genesis_sensor

    def _initialize_impl(self) -> None:
        super()._initialize_impl()
        # Placeholders; real buffers allocated on first update
        self._data = self.Data(
            points=torch.empty(0, device=self.device),
            distances=torch.empty(0, device=self.device),
        )

    @property
    def data(self) -> "GenesisLidarSensor.Data":
        self._update_outdated_buffers()
        return self._data

    def _extract_lidar_tensors(self) -> tuple[torch.Tensor, torch.Tensor]:
        """Read LiDAR data (points, distances) from Genesis."""
        if self._gs_sensor is None:
            raise RuntimeError(
                f"GenesisLidarSensor '{self.cfg.name or 'unnamed'}' has no Genesis sensor attached. "
                f"Call set_genesis_sensor() or pass genesis_sensor in the constructor."
            )

        raw = self._gs_sensor.read()
        if hasattr(raw, "points") and hasattr(raw, "distances"):
            points = raw.points
            distances = raw.distances
        elif isinstance(raw, (tuple, list)) and len(raw) >= 2:
            points, distances = raw[0], raw[1]
        else:  # pragma: no cover - defensive
            raise TypeError(
                f"Unsupported Lidar sensor output type {type(raw)} for GenesisLidarSensor. "
                f"Expected NamedTuple with (points, distances)."
            )

        points_t = to_tensor(points, device=self.device, dtype=torch.float32)
        distances_t = to_tensor(distances, device=self.device, dtype=torch.float32)

        # Normalize shapes:
        # points: (H, V, 3) or (num_envs, H, V, 3)
        if points_t.dim() == 3 and points_t.shape[-1] == 3:
            points_t = points_t.unsqueeze(0)
        if points_t.dim() != 4 or points_t.shape[-1] != 3:
            raise ValueError(
                f"Lidar points tensor must have shape (num_envs, H, V, 3) or (H, V, 3), got {points_t.shape}"
            )

        # distances: (H, V) or (num_envs, H, V)
        if distances_t.dim() == 2:
            distances_t = distances_t.unsqueeze(0)
        if distances_t.dim() != 3:
            raise ValueError(
                f"Lidar distances tensor must have shape (num_envs, H, V) or (H, V), got {distances_t.shape}"
            )

        if points_t.shape[0] != distances_t.shape[0]:
            raise ValueError(
                f"Lidar batch size mismatch between points and distances: "
                f"{points_t.shape} vs {distances_t.shape}"
            )

        if points_t.shape[0] != self.num_envs:
            # Allow single-env LiDAR for debugging
            if self.num_envs == 1 and points_t.shape[0] == 1:
                return points_t, distances_t
            raise ValueError(
                f"Lidar batch size mismatch: expected num_envs={self.num_envs}, got {points_t.shape[0]}"
            )

        return points_t, distances_t

    def _update_buffers_impl(self, env_ids: Sequence[int] | torch.Tensor) -> None:
        points, distances = self._extract_lidar_tensors()
        self._data.points = points
        self._data.distances = distances


@configclass
class GenesisLidarSensorCfg(GenesisSensorBaseCfg):
    """Configuration for :class:`GenesisLidarSensor`."""

    class_type: type = GenesisLidarSensor
    name: str = None
    entity_name: str = "robot"
    pos_offset: tuple[float, float, float] = (0.0, 0.0, 0.15)
    pattern_fov: tuple[float, float] = (360.0, 60.0)  # (horizontal, vertical) degrees
    pattern_n_points: tuple[int, int] = (128, 32)
    max_range: float = 100.0
    min_range: float = 0.1
    return_world_frame: bool = True
    draw_debug: bool = False

    def build_genesis_sensor(
        self, gs_scene: "gs.Scene", lab_scene: "LabScene"
    ) -> GenesisLidarSensorHandle:
        import genesis as gs

        entity_idx = resolve_entity_idx(lab_scene, self.entity_name)
        pattern = gs.sensors.SphericalPattern(
            fov=self.pattern_fov,
            n_points=self.pattern_n_points,
        )
        return gs_scene.add_sensor(
            gs.sensors.Lidar(
                pattern=pattern,
                entity_idx=entity_idx,
                pos_offset=self.pos_offset,
                max_range=self.max_range,
                min_range=self.min_range,
                return_world_frame=self.return_world_frame,
                draw_debug=self.draw_debug,
            )
        )

