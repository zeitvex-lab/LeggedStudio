"""Boolean contact sensor wrapper over ``gs.sensors.Contact``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import torch

from genesislab.utils.configclass import configclass
from .sensor_base import GenesisSensorBase, GenesisSensorBaseCfg
from .genesis_sensor_utils import to_tensor, resolve_entity_idx
from .genesis_sensor_types import GenesisContactSensorHandle

if TYPE_CHECKING:
    import genesis as gs
    from genesislab.engine.scene.lab_scene import LabScene


class GenesisContactBoolSensor(GenesisSensorBase):
    """Contact state sensor backed by ``gs.sensors.Contact``.

    This sensor keeps a history of per-link boolean contacts. It expects an
    underlying Genesis contact sensor handle to be provided via the constructor
    or :meth:`set_genesis_sensor`.
    """

    @dataclass
    class Data:
        """Exposed buffers.

        Attributes:
            contact_w_history: bool tensor of shape
                (history_length, num_envs, num_links).
        """

        contact_w_history: torch.Tensor

    def __init__(
        self,
        cfg: "GenesisContactBoolSensorCfg",
        num_envs: int,
        device: str = "cuda",
        genesis_sensor: GenesisContactSensorHandle = None,
    ) -> None:
        self._gs_sensor: GenesisContactSensorHandle = genesis_sensor
        history_len = max(int(cfg.history_length), 1)

        # Allocate with a conservative shape; will be resized on first update.
        self._contact_buffer = torch.zeros(
            history_len,
            num_envs,
            1,
            device=device,
            dtype=torch.bool,
        )
        super().__init__(cfg=cfg, num_envs=num_envs, device=device)

    def set_genesis_sensor(self, genesis_sensor: GenesisContactSensorHandle) -> None:
        """Attach the underlying Genesis ``Contact`` sensor."""
        self._gs_sensor = genesis_sensor

    def _initialize_impl(self) -> None:
        super()._initialize_impl()
        self._data = self.Data(contact_w_history=self._contact_buffer)

    @property
    def data(self) -> "GenesisContactBoolSensor.Data":
        self._update_outdated_buffers()
        return self._data

    def _extract_contact_tensor(self) -> torch.Tensor:
        """Read contact state from the underlying Genesis sensor."""
        if self._gs_sensor is None:
            raise RuntimeError(
                f"GenesisContactBoolSensor '{self.cfg.name or 'unnamed'}' has no Genesis sensor attached. "
                f"Call set_genesis_sensor() or pass genesis_sensor in the constructor."
            )

        raw = self._gs_sensor.read()

        # Try common layouts: tensor / namedtuple / sequence
        if isinstance(raw, torch.Tensor):
            contact = raw
        elif hasattr(raw, "contact"):
            contact = getattr(raw, "contact")
        elif hasattr(raw, "contacts"):
            contact = getattr(raw, "contacts")
        else:
            # Fallback: first field of a sequence / namedtuple
            try:
                contact = raw[0]
            except Exception as exc:  # pragma: no cover - defensive
                raise TypeError(
                    f"Unsupported contact sensor output type {type(raw)} for GenesisContactBoolSensor"
                ) from exc

        contact_t = to_tensor(contact, device=self.device, dtype=torch.bool)
        if contact_t.dim() == 2:
            # (num_envs, num_links) -> (num_envs, num_links)
            return contact_t
        if contact_t.dim() == 3 and contact_t.shape[-1] == 1:
            # (num_envs, num_links, 1) -> squeeze last dim
            return contact_t.squeeze(-1)
        return contact_t

    def _maybe_resize_buffers(self, num_links: int) -> None:
        """Resize history buffers if number of links changed."""
        if num_links == self._data.contact_w_history.shape[2]:
            return

        history_len, num_envs, _ = self._data.contact_w_history.shape
        new_buf = torch.zeros(
            history_len,
            num_envs,
            num_links,
            device=self.device,
            dtype=torch.bool,
        )
        # Copy as much history as possible
        old_links = min(self._data.contact_w_history.shape[2], num_links)
        new_buf[:, :, :old_links] = self._data.contact_w_history[:, :, :old_links]
        self._data.contact_w_history = new_buf

    def _update_buffers_impl(self, env_ids: Sequence[int] | torch.Tensor) -> None:
        # Roll along time dimension
        self._data.contact_w_history = torch.roll(
            self._data.contact_w_history, shifts=-1, dims=0
        )

        contact = self._extract_contact_tensor()  # (num_envs, num_links)
        if contact.shape[0] != self.num_envs:
            raise ValueError(
                f"Contact tensor batch size mismatch: expected num_envs={self.num_envs}, "
                f"got shape {contact.shape}"
            )

        num_links = contact.shape[1]
        self._maybe_resize_buffers(num_links)

        # Write latest contacts into last history slot
        self._data.contact_w_history[-1, :, :num_links] = contact


@configclass
class GenesisContactBoolSensorCfg(GenesisSensorBaseCfg):
    """Configuration for :class:`GenesisContactBoolSensor`."""

    class_type: type = GenesisContactBoolSensor
    name: str = None
    history_length: int = 3
    entity_name: str = "robot"

    def build_genesis_sensor(
        self, gs_scene: "gs.Scene", lab_scene: "LabScene"
    ) -> GenesisContactSensorHandle:
        import genesis as gs

        entity_idx = resolve_entity_idx(lab_scene, self.entity_name)
        return gs_scene.add_sensor(
            gs.sensors.Contact(
                entity_idx=entity_idx,
                draw_debug=getattr(self, "debug_vis", False),
            )
        )

