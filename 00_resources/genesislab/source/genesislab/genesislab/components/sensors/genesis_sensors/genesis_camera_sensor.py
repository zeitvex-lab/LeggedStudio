"""RGB camera sensor wrapper over Genesis camera backends.

This is a thin wrapper over a Genesis camera sensor (e.g.
``gs.sensors.RasterizerCameraOptions`` or ``RaytracerCameraOptions``) that
exposes the data through :class:`SensorBase`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import torch

from genesislab.utils.configclass import configclass
from .sensor_base import GenesisSensorBase, GenesisSensorBaseCfg
from .genesis_sensor_utils import to_tensor, resolve_entity_idx, resolve_link_idx_local
from .genesis_sensor_types import GenesisCameraSensorHandle

if TYPE_CHECKING:
    import genesis as gs
    from genesislab.engine.scene.lab_scene import LabScene


class GenesisCameraSensor(GenesisSensorBase):
    """Camera sensor wrapper that exposes ``rgb`` images.

    The underlying Genesis sensor is expected to support ``read()`` and return
    an object with an ``rgb`` attribute of shape ``(H, W, 3)`` or
    ``(num_envs, H, W, 3)``.
    """

    @dataclass
    class Data:
        """Exposed buffers.

        Attributes:
            rgb: Tensor of shape (num_envs, H, W, 3).
        """

        rgb: torch.Tensor

    def __init__(
        self,
        cfg: "GenesisCameraSensorCfg",
        num_envs: int,
        device: str = "cuda",
        genesis_sensor: GenesisCameraSensorHandle = None,
    ) -> None:
        self._gs_sensor: GenesisCameraSensorHandle = genesis_sensor
        self._rgb: torch.Tensor = None
        super().__init__(cfg=cfg, num_envs=num_envs, device=device)

    def set_genesis_sensor(self, genesis_sensor: GenesisCameraSensorHandle) -> None:
        """Attach the underlying Genesis camera sensor."""
        self._gs_sensor = genesis_sensor

    def _initialize_impl(self) -> None:
        super()._initialize_impl()
        # Placeholder tensor; real buffer allocated on first update
        self._data = self.Data(rgb=torch.empty(0, device=self.device))

    @property
    def data(self) -> "GenesisCameraSensor.Data":
        self._update_outdated_buffers()
        return self._data

    def _extract_rgb_tensor(self) -> torch.Tensor:
        """Read RGB image(s) from the underlying Genesis camera."""
        if self._gs_sensor is None:
            raise RuntimeError(
                f"GenesisCameraSensor '{self.cfg.name or 'unnamed'}' has no Genesis sensor attached. "
                f"Call set_genesis_sensor() or pass genesis_sensor in the constructor."
            )

        raw = self._gs_sensor.read()
        if not hasattr(raw, "rgb"):
            raise AttributeError(
                f"Underlying Genesis camera sensor output has no 'rgb' attribute: {type(raw)}"
            )

        rgb = getattr(raw, "rgb")
        rgb_t = to_tensor(rgb, device=self.device, dtype=torch.float32)

        # Normalize shapes to (num_envs, H, W, 3)
        if rgb_t.dim() == 3 and rgb_t.shape[-1] == 3:
            # (H, W, 3) -> (1, H, W, 3)
            rgb_t = rgb_t.unsqueeze(0)
        if rgb_t.dim() != 4 or rgb_t.shape[-1] != 3:
            raise ValueError(
                f"Camera rgb tensor must have shape (num_envs, H, W, 3) or (H, W, 3), got {rgb_t.shape}"
            )
        if rgb_t.shape[0] != self.num_envs:
            # Allow single-env camera even if num_envs>1 (e.g., debug viewer)
            if self.num_envs == 1 and rgb_t.shape[0] == 1:
                return rgb_t
            raise ValueError(
                f"Camera batch size mismatch: expected num_envs={self.num_envs}, got {rgb_t.shape[0]}"
            )
        return rgb_t

    def _update_buffers_impl(self, env_ids: Sequence[int] | torch.Tensor) -> None:
        rgb = self._extract_rgb_tensor()  # (num_envs, H, W, 3)
        self._data.rgb = rgb


@configclass
class GenesisCameraSensorCfg(GenesisSensorBaseCfg):
    """Configuration for :class:`GenesisCameraSensor`."""

    class_type: type = GenesisCameraSensor
    name: str = None
    res: tuple[int, int] = (512, 512)
    pos: tuple[float, float, float] = (3.0, 0.0, 2.0)
    lookat: tuple[float, float, float] = (0.0, 0.0, 0.5)
    fov: float = 60.0
    entity_name: str = None  # None -> static camera (entity_idx=-1)
    link_name: str = None
    draw_debug: bool = False

    def build_genesis_sensor(
        self, gs_scene: "gs.Scene", lab_scene: "LabScene"
    ) -> GenesisCameraSensorHandle:
        import genesis as gs

        if self.entity_name:
            entity_idx = resolve_entity_idx(lab_scene, self.entity_name)
            link_idx_local = resolve_link_idx_local(lab_scene, self.entity_name, self.link_name)
        else:
            entity_idx = -1
            link_idx_local = 0
        return gs_scene.add_sensor(
            gs.sensors.RasterizerCameraOptions(
                res=self.res,
                pos=self.pos,
                lookat=self.lookat,
                fov=self.fov,
                entity_idx=entity_idx,
                link_idx_local=link_idx_local,
            )
        )

