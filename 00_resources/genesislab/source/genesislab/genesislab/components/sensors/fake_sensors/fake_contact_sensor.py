"""Contact sensor implementations for GenesisLab.

These sensors read real contact forces from the Genesis engine using the
`get_links_net_contact_force()` API and provide the same interface as
IsaacLab's contact sensors for MDP terms.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch

from genesislab.utils.configclass import configclass
from genesislab.engine.entity import LabEntity
from .fake_sensor_base import FakeSensorBase, FakeSensorBaseCfg

class FakeContactSensor(FakeSensorBase):
    """Contact sensor for GenesisLab that reads real contact forces from Genesis engine.

    The sensor reads contact forces from the Genesis entity using
    `get_links_net_contact_force()` and maintains a history buffer compatible
    with IsaacLab's contact sensor interface.
    """

    def __init__(
        self,
        cfg: "FakeContactSensorCfg",
        num_envs: int,
        device: str = "cuda",
        entity: "LabEntity" = None,
    ):
        """Initialize the contact sensor.

        Args:
            cfg: Sensor configuration.
            num_envs: Number of parallel environments.
            device: Device for tensors.
            entity: Genesis entity object to read contact forces from. If None,
                will be set later via `set_entity()`.
        """
        # Store entity reference before calling super().__init__()
        self._entity = entity
        num_channels = entity.n_links
        history_len = max(int(cfg.history_length), 1)
        
        # Create buffers BEFORE calling super().__init__() because
        # super().__init__() will call _initialize_impl() which needs these buffers
        self._net_forces_buffer = torch.zeros(
            history_len,
            num_envs,
            num_channels,
            3,
            device=device,
            dtype=torch.float32,
        )
        self._last_air_time_buffer = torch.zeros(
            num_envs,
            num_channels,
            device=device,
            dtype=torch.float32,
        )
        self._prev_air_time = self._last_air_time_buffer.clone()
        
        # Initialize base class (this will call _initialize_impl())
        super().__init__(cfg=cfg, num_envs=num_envs, device=device)

    @dataclass
    class _ContactSensorData:
        """Data buffers exposed by :class:`ContactSensor`.

        For now, these are zero tensors with the right shapes. The fields mirror
        those used in the MDP reward/termination functions:

        - ``net_forces_w_history``: Tensor of shape
        ``(history_length, num_envs, num_channels, 3)``.
        - ``last_air_time``: Tensor of shape ``(num_envs, num_channels)``.
        """

        net_forces_w_history: torch.Tensor
        last_air_time: torch.Tensor

    def _initialize_impl(self) -> None:
        """Initialize the sensor data buffers."""
        super()._initialize_impl()
        # Create data object
        self._data = self._ContactSensorData(
            net_forces_w_history=self._net_forces_buffer,
            last_air_time=self._last_air_time_buffer,
        )

    @property
    def data(self) -> "_ContactSensorData":
        """Data from the sensor."""
        # Update sensors if needed
        self._update_outdated_buffers()
        return self._data

    def set_entity(self, entity: "LabEntity") -> None:
        """Set the Genesis entity to read contact forces from.

        Args:
            entity: Genesis entity object.
        """
        self._entity = entity
        # Resize buffers if entity has different number of links
        num_channels = entity.n_links
        if num_channels != self._data.net_forces_w_history.shape[2]:
            # Resize buffers to match number of links
            history_len = self._data.net_forces_w_history.shape[0]
            self._data.net_forces_w_history = torch.zeros(
                history_len,
                self.num_envs,
                num_channels,
                3,
                device=self.device,
                dtype=torch.float32,
            )
            self._data.last_air_time = torch.zeros(
                self.num_envs,
                num_channels,
                device=self.device,
                dtype=torch.float32,
            )
            # Initialize previous air time
            self._prev_air_time = self._data.last_air_time.clone()

    def _update_buffers_impl(self, env_ids) -> None:
        """Update sensor buffers for the specified environment ids."""
        # Roll history along the time dimension
        self._data.net_forces_w_history = torch.roll(
            self._data.net_forces_w_history, shifts=-1, dims=0
        )

        # Get real contact forces from Genesis entity
        if self._entity is None:
            raise RuntimeError(
                f"ContactSensor '{self.cfg.name or 'unnamed'}' has no entity assigned. "
                f"Call set_entity() or provide entity in __init__()."
            )
        
        if not hasattr(self._entity, "get_links_net_contact_force"):
            raise AttributeError(
                f"Entity '{self.cfg.entity_name}' does not have 'get_links_net_contact_force()' method. "
                f"Contact sensor requires a Genesis RigidEntity with contact force API."
            )
        
        # Get contact forces: shape (num_envs, num_links, 3)
        contact_forces = self._entity.get_links_net_contact_force()
        
        # Ensure device and dtype match
        contact_forces = contact_forces.to(device=self.device, dtype=torch.float32)
        
        # Validate shape
        if len(contact_forces.shape) != 3 or contact_forces.shape[0] != self.num_envs or contact_forces.shape[2] != 3:
            raise ValueError(
                f"Contact forces shape mismatch: expected (num_envs={self.num_envs}, num_links, 3), "
                f"got {contact_forces.shape}"
            )
        
        # Reshape to match expected format: (num_envs, num_links, 3) -> (num_envs, num_channels, 3)
        # If num_channels doesn't match, resize buffers
        num_links = contact_forces.shape[1]
        if num_links != self._data.net_forces_w_history.shape[2]:
            # Resize buffers
            history_len = self._data.net_forces_w_history.shape[0]
            old_forces = self._data.net_forces_w_history.clone()
            old_air_time = self._data.last_air_time.clone()
            
            self._data.net_forces_w_history = torch.zeros(
                history_len,
                self.num_envs,
                num_links,
                3,
                device=self.device,
                dtype=torch.float32,
            )
            self._data.last_air_time = torch.zeros(
                self.num_envs,
                num_links,
                device=self.device,
                dtype=torch.float32,
            )
            
            # Copy old data if possible
            if old_forces.shape[2] <= num_links:
                self._data.net_forces_w_history[:, :, :old_forces.shape[2], :] = old_forces
                self._data.last_air_time[:, :old_air_time.shape[1]] = old_air_time
        
        # Store latest contact forces in history (last time step)
        self._data.net_forces_w_history[-1, ...] = contact_forces
        
        # Update air time: reset to 0 if contact force magnitude > threshold, otherwise accumulate
        force_mag = torch.norm(contact_forces, dim=-1)  # (num_envs, num_links)
        contact_threshold = 1.0  # Threshold for considering a contact as "active"
        is_contact = force_mag > contact_threshold
        
        # Save previous air time for first-contact detection
        self._prev_air_time = self._data.last_air_time.clone()
        
        # Get dt from cfg or use a default
        dt = self.cfg.update_period if self.cfg.update_period > 0 else 0.005
        
        # Reset air time for links in contact, accumulate for others
        self._data.last_air_time = torch.where(
            is_contact,
            torch.zeros_like(self._data.last_air_time),
            self._data.last_air_time + dt,
        )

    # IsaacLab-style helper used in feet_air_time.
    def compute_first_contact(self, step_dt: float) -> torch.Tensor:
        """Compute whether a first contact was detected at the current step.

        A "first contact" is detected when a link transitions from no contact
        (air_time > threshold) to contact (air_time == 0).

        Args:
            step_dt: Environment step time (used as threshold for detecting "was in air").

        Returns:
            A boolean tensor of shape ``(num_envs, num_channels)`` indicating
            whether a first contact was detected at the current step.
        """
        # Check if previous air_time was > threshold (was in air) and current air_time is 0 (now in contact)
        was_in_air = self._prev_air_time > step_dt
        is_now_in_contact = self._data.last_air_time < step_dt  # Air time reset to near-zero means contact
        
        # First contact: was in air AND now in contact
        first_contact = was_in_air & is_now_in_contact
        
        return first_contact


@configclass
class FakeContactSensorCfg(FakeSensorBaseCfg):
    """Configuration for a contact sensor.

    Attributes:
        name: Logical name of the sensor. If None, the key in SceneCfg.sensors
            is used.
        entity_name: Name of the articulated entity to which this sensor is
            conceptually attached (typically ``"robot"``).
        history_length: Number of past steps of contact forces to keep.
        track_air_time: Whether to track a simple notion of link "air time".
            Currently this is a no-op placeholder kept for API compatibility.
    """

    class_type: type = FakeContactSensor  # Will be set after ContactSensor is defined
    name: str = None
    entity_name: str = "robot"
    history_length: int = 3
    track_air_time: bool = True
