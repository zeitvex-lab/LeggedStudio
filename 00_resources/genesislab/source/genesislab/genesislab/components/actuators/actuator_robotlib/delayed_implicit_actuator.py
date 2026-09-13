"""Delayed implicit actuator implementation.

This module provides the DelayedImplicitActuator class, which extends
ImplicitActuator with delayed command application.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from genesislab.utils.configclass import configclass

from ..actuator_pd import ImplicitActuator
from ..articulation_actions import ArticulationActions
from ..actuator_pd_cfg import ImplicitActuatorCfg
from .delay_buffer_wrapper import IsaacLabStyleDelayBuffer

if TYPE_CHECKING:
    pass

import torch


class DelayedImplicitActuator(ImplicitActuator):
    """Implicit PD actuator with delayed command application.

    This class extends the :class:`ImplicitActuator` class by adding a delay to the actuator commands.
    The delay is implemented using a delay buffer that stores the actuator commands for a certain
    number of physics steps. The most recent actuation value is pushed to the buffer at every physics
    step, but the final actuation value applied to the simulation is lagged by a certain number of
    physics steps.

    The amount of time lag is configurable and can be set to a random value between the minimum and
    maximum time lag bounds at every reset. The minimum and maximum time lag values are set in the
    configuration instance passed to the class.
    """

    cfg: "DelayedImplicitActuatorCfg"
    """The configuration for the actuator model."""

    def __init__(self, cfg: "DelayedImplicitActuatorCfg", *args, **kwargs):
        super().__init__(cfg, *args, **kwargs)
        # Instantiate delay buffers using IsaacLab-style interface
        # Note: We use a wrapper to adapt genesislab's DelayBuffer to IsaacLab's interface
        self.positions_delay_buffer = IsaacLabStyleDelayBuffer(cfg.max_delay, self._num_envs, device=self._device)
        self.velocities_delay_buffer = IsaacLabStyleDelayBuffer(cfg.max_delay, self._num_envs, device=self._device)
        self.efforts_delay_buffer = IsaacLabStyleDelayBuffer(cfg.max_delay, self._num_envs, device=self._device)
        # All of the envs
        self._ALL_INDICES = torch.arange(self._num_envs, dtype=torch.long, device=self._device)

    def reset(self, env_ids: Sequence[int]):
        super().reset(env_ids)
        # Number of environments (since env_ids can be a slice)
        if env_ids is None or env_ids == slice(None):
            num_envs = self._num_envs
        else:
            num_envs = len(env_ids)
        # Set a new random delay for environments in env_ids
        time_lags = torch.randint(
            low=self.cfg.min_delay,
            high=self.cfg.max_delay + 1,
            size=(num_envs,),
            dtype=torch.int,
            device=self._device,
        )
        # Set delays
        self.positions_delay_buffer.set_time_lag(time_lags, env_ids)
        self.velocities_delay_buffer.set_time_lag(time_lags, env_ids)
        self.efforts_delay_buffer.set_time_lag(time_lags, env_ids)
        # Reset buffers
        self.positions_delay_buffer.reset(env_ids)
        self.velocities_delay_buffer.reset(env_ids)
        self.efforts_delay_buffer.reset(env_ids)

    def compute(
        self, control_action: ArticulationActions, joint_pos: torch.Tensor, joint_vel: torch.Tensor
    ) -> ArticulationActions:
        # Apply delay based on the delay model for all the setpoints
        control_action.joint_positions = self.positions_delay_buffer.compute(control_action.joint_positions)
        control_action.joint_velocities = self.velocities_delay_buffer.compute(control_action.joint_velocities)
        control_action.joint_efforts = self.efforts_delay_buffer.compute(control_action.joint_efforts)
        # Compute actuator model
        return super().compute(control_action, joint_pos, joint_vel)


@configclass
class DelayedImplicitActuatorCfg(ImplicitActuatorCfg):
    """Configuration for a delayed implicit actuator."""

    class_type: type = DelayedImplicitActuator

    min_delay: int = 0
    """Minimum number of physics time-steps with which the actuator command may be delayed. Defaults to 0."""

    max_delay: int = 0
    """Maximum number of physics time-steps with which the actuator command may be delayed. Defaults to 0."""
