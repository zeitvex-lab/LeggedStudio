"""IMU sensor wrapper over ``gs.sensors.IMU``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import torch

from genesislab.utils.configclass import configclass
from .sensor_base import GenesisSensorBase, GenesisSensorBaseCfg
from .genesis_sensor_utils import to_tensor, resolve_entity_idx, resolve_link_idx_local
from .genesis_sensor_types import GenesisImuSensorHandle

if TYPE_CHECKING:
    import genesis as gs
    from genesislab.engine.scene.lab_scene import LabScene


class GenesisImuSensor(GenesisSensorBase):
    """IMU sensor backed by ``gs.sensors.IMU``.

    Exposes linear acceleration and angular velocity (optionally with history).
    """

    @dataclass
    class Data:
        """Exposed buffers.

        Attributes:
            lin_acc: Tensor of shape (history_length, num_envs, 3).
            ang_vel: Tensor of shape (history_length, num_envs, 3).
        """

        lin_acc: torch.Tensor
        ang_vel: torch.Tensor

    def __init__(
        self,
        cfg: "GenesisImuSensorCfg",
        num_envs: int,
        device: str = "cuda",
        genesis_sensor: GenesisImuSensorHandle = None,
    ) -> None:
        self._gs_sensor: GenesisImuSensorHandle = genesis_sensor
        history_len = max(int(cfg.history_length), 1)

        # Allocate buffers; resized only if batch size changes.
        self._lin_acc = torch.zeros(history_len, num_envs, 3, device=device, dtype=torch.float32)
        self._ang_vel = torch.zeros(history_len, num_envs, 3, device=device, dtype=torch.float32)
        super().__init__(cfg=cfg, num_envs=num_envs, device=device)

    def set_genesis_sensor(self, genesis_sensor: GenesisImuSensorHandle) -> None:
        """Attach the underlying Genesis ``IMU`` sensor."""
        self._gs_sensor = genesis_sensor

    def _initialize_impl(self) -> None:
        super()._initialize_impl()
        self._data = self.Data(lin_acc=self._lin_acc, ang_vel=self._ang_vel)

    @property
    def data(self) -> "GenesisImuSensor.Data":
        self._update_outdated_buffers()
        return self._data

    def _extract_imu_tensors(self) -> tuple[torch.Tensor, torch.Tensor]:
        """Read IMU data (lin_acc, ang_vel) from Genesis."""
        if self._gs_sensor is None:
            raise RuntimeError(
                f"GenesisImuSensor '{self.cfg.name or 'unnamed'}' has no Genesis sensor attached. "
                f"Call set_genesis_sensor() or pass genesis_sensor in the constructor."
            )

        raw = self._gs_sensor.read()
        if hasattr(raw, "lin_acc") and hasattr(raw, "ang_vel"):
            lin_acc = raw.lin_acc
            ang_vel = raw.ang_vel
        elif isinstance(raw, (tuple, list)) and len(raw) >= 2:
            lin_acc, ang_vel = raw[0], raw[1]
        else:  # pragma: no cover - defensive
            raise TypeError(
                f"Unsupported IMU sensor output type {type(raw)} for GenesisImuSensor. "
                f"Expected NamedTuple with (lin_acc, ang_vel)."
            )

        lin_acc_t = to_tensor(lin_acc, device=self.device, dtype=torch.float32)
        ang_vel_t = to_tensor(ang_vel, device=self.device, dtype=torch.float32)

        # Ensure shape (num_envs, 3)
        for name, t in (("lin_acc", lin_acc_t), ("ang_vel", ang_vel_t)):
            if t.dim() == 1 and t.shape[0] == 3:
                # Single env -> (1, 3)
                t = t.unsqueeze(0)
            if t.dim() != 2 or t.shape[1] != 3:
                raise ValueError(
                    f"IMU {name} tensor must have shape (num_envs, 3), got {t.shape}"
                )
            if name == "lin_acc":
                lin_acc_t = t
            else:
                ang_vel_t = t

        return lin_acc_t, ang_vel_t

    def _update_buffers_impl(self, env_ids: Sequence[int] | torch.Tensor) -> None:
        # Roll along time dimension
        self._data.lin_acc = torch.roll(self._data.lin_acc, shifts=-1, dims=0)
        self._data.ang_vel = torch.roll(self._data.ang_vel, shifts=-1, dims=0)

        lin_acc, ang_vel = self._extract_imu_tensors()  # (num_envs, 3)
        if lin_acc.shape[0] != self.num_envs or ang_vel.shape[0] != self.num_envs:
            raise ValueError(
                f"IMU batch size mismatch: expected num_envs={self.num_envs}, "
                f"got lin_acc={lin_acc.shape}, ang_vel={ang_vel.shape}"
            )

        self._data.lin_acc[-1, :, :] = lin_acc
        self._data.ang_vel[-1, :, :] = ang_vel


@configclass
class GenesisImuSensorCfg(GenesisSensorBaseCfg):
    """Configuration for :class:`GenesisImuSensor`."""

    class_type: type = GenesisImuSensor
    name: str = None
    history_length: int = 1
    entity_name: str = "robot"
    link_name: str = None  # e.g. "base" or "trunk"; None -> link_idx_local=0
    pos_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    draw_debug: bool = False

    def build_genesis_sensor(
        self, gs_scene: "gs.Scene", lab_scene: "LabScene"
    ) -> GenesisImuSensorHandle:
        import genesis as gs

        entity_idx = resolve_entity_idx(lab_scene, self.entity_name)
        link_idx_local = resolve_link_idx_local(lab_scene, self.entity_name, self.link_name)
        return gs_scene.add_sensor(
            gs.sensors.IMU(
                entity_idx=entity_idx,
                link_idx_local=link_idx_local,
                pos_offset=self.pos_offset,
                draw_debug=self.draw_debug,
            )
        )

