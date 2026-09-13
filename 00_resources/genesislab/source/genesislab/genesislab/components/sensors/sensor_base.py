"""Base class for sensors in GenesisLab.

This class defines an interface for sensors similar to how the AssetBase class works.
Each sensor class should inherit from this class and implement the abstract methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import torch

from genesislab.utils.configclass import configclass

class SensorBase(ABC):
    """The base class for implementing a sensor in GenesisLab.

    The implementation is based on lazy evaluation. The sensor data is only updated when the user
    tries accessing the data through the :attr:`data` property or sets ``force_compute=True`` in
    the :meth:`update` method. This is done to avoid unnecessary computation when the sensor data
    is not used.

    The sensor is updated at the specified update period. If the update period is zero, then the
    sensor is updated at every simulation step.
    """

    def __init__(self, cfg: "SensorBaseCfg", num_envs: int, device: str = "cuda"):
        """Initialize the sensor class.

        Args:
            cfg: The configuration parameters for the sensor.
            num_envs: Number of parallel environments.
            device: Device for computation (e.g., "cuda" or "cpu").
        """
        # Validate configuration
        if cfg.history_length < 0:
            raise ValueError(f"History length must be >= 0! Received: {cfg.history_length}")
        if num_envs <= 0:
            raise ValueError(f"Number of environments must be > 0! Received: {num_envs}")

        # Store inputs
        self.cfg = cfg
        self._num_envs = int(num_envs)
        self._device = device

        # Flag for whether the sensor is initialized
        self._is_initialized = False

        # Boolean tensor indicating whether the sensor data has to be refreshed
        self._is_outdated = torch.ones(self._num_envs, dtype=torch.bool, device=self._device)

        # Current timestamp (in seconds)
        self._timestamp = torch.zeros(self._num_envs, device=self._device)

        # Timestamp from last update
        self._timestamp_last_update = torch.zeros_like(self._timestamp)

        # Initialize the sensor
        self._initialize_impl()

    """
    Properties.
    """

    @property
    def is_initialized(self) -> bool:
        """Whether the sensor is initialized.

        Returns True if the sensor is initialized, False otherwise.
        """
        return self._is_initialized

    @property
    def num_instances(self) -> int:
        """Number of instances of the sensor.

        This is equal to the number of sensors per environment multiplied by the number of environments.
        """
        return self._num_envs

    @property
    def num_envs(self) -> int:
        """Number of environments."""
        return self._num_envs

    @property
    def device(self) -> str:
        """Memory device for computation."""
        return self._device

    @property
    @abstractmethod
    def data(self) -> Any:
        """Data from the sensor.

        This property is only updated when the user tries to access the data. This is done to avoid
        unnecessary computation when the sensor data is not used.

        For updating the sensor when this property is accessed, you can use the following
        code snippet in your sensor implementation:

        .. code-block:: python

            # update sensors if needed
            self._update_outdated_buffers()
            # return the data (where `_data` is the data for the sensor)
            return self._data
        """
        raise NotImplementedError

    """
    Operations.
    """

    def reset(self, env_ids: Sequence[int] = None) -> None:
        """Resets the sensor internals.

        Args:
            env_ids: The sensor ids to reset. Defaults to None (reset all).
        """
        # Resolve sensor ids
        if env_ids is None:
            env_ids = slice(None)
        else:
            if isinstance(env_ids, (list, tuple)):
                env_ids = torch.tensor(env_ids, dtype=torch.long, device=self._device)
            elif isinstance(env_ids, torch.Tensor):
                env_ids = env_ids.to(self._device)

        # Reset the timestamp for the sensors
        self._timestamp[env_ids] = 0.0
        self._timestamp_last_update[env_ids] = 0.0
        # Set all reset sensors to outdated so that they are updated when data is called the next time.
        self._is_outdated[env_ids] = True

        # Call implementation-specific reset
        self._reset_impl(env_ids)

    def update(self, dt: float, force_recompute: bool = False) -> None:
        """Update the sensor data.

        Args:
            dt: Time step since last update (in seconds).
            force_recompute: Whether to force recomputation even if update period hasn't elapsed.
        """
        # Update the timestamp for the sensors
        self._timestamp += dt

        # Check if update is needed based on update period
        # Note: self._timestamp is a tensor of shape (num_envs,), so we need to check if any env needs update
        if force_recompute:
            needs_update = True
        elif self.cfg.history_length > 0:
            needs_update = True
        else:
            # Check if any environment's timestamp exceeds the update period
            time_since_update = self._timestamp - self._timestamp_last_update + 1e-6
            needs_update = (time_since_update >= self.cfg.update_period).any().item()
        
        if needs_update:
            # Mark all environments as outdated if update is needed
            self._is_outdated[:] = True
            self._update_outdated_buffers()

    """
    Implementation specific.
    """

    @abstractmethod
    def _initialize_impl(self) -> None:
        """Initializes the sensor-related handles and internal buffers.

        This method is called during __init__ and should set up any sensor-specific
        initialization logic.
        """
        self._is_initialized = True

    @abstractmethod
    def _update_buffers_impl(self, env_ids: Sequence[int] | torch.Tensor) -> None:
        """Fills the sensor data for provided environment ids.

        This function does not perform any time-based checks and directly fills the data into the
        data container.

        Args:
            env_ids: The indices of the sensors that are ready to capture.
                Can be a sequence of integers or a torch.Tensor.
        """
        raise NotImplementedError

    def _reset_impl(self, env_ids: Sequence[int] | torch.Tensor | slice) -> None:
        """Implementation-specific reset logic.

        Override this method in subclasses if additional reset logic is needed.

        Args:
            env_ids: The indices of the sensors to reset.
        """
        pass

    """
    Helper functions.
    """

    def _update_outdated_buffers(self) -> None:
        """Fills the sensor data for the outdated sensors."""
        outdated_mask = self._is_outdated
        if outdated_mask.any():
            # Convert boolean mask to indices
            outdated_env_ids = outdated_mask.nonzero().squeeze(-1)
            if len(outdated_env_ids) > 0:
                # Obtain new data
                self._update_buffers_impl(outdated_env_ids)
                # Update the timestamp from last update
                self._timestamp_last_update[outdated_env_ids] = self._timestamp[outdated_env_ids]
                # Set outdated flag to false for the updated sensors
                self._is_outdated[outdated_env_ids] = False

@configclass
class SensorBaseCfg:
    """Base configuration parameters for a sensor.

    All sensor configuration classes should inherit from this base class.
    """

    class_type: type["SensorBase"] = SensorBase
    """The associated sensor class.

    The class should inherit from :class:`SensorBase`.
    """

    name: str = None
    """Logical name of the sensor. If None, the key in SceneCfg.sensors is used."""

    update_period: float = 0.0
    """Update period of the sensor buffers (in seconds). Defaults to 0.0 (update every step)."""

    history_length: int = 0
    """Number of past frames to store in the sensor buffers. Defaults to 0, which means that only
    the current data is stored (no history)."""

    debug_vis: bool = False
    """Whether to visualize the sensor. Defaults to False."""
