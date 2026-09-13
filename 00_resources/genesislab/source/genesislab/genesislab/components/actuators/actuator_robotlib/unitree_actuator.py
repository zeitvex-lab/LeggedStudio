"""Unitree actuator implementation.

This module provides the UnitreeActuator class, which implements a torque-speed curve
for Unitree actuators based on their specifications.
"""

from __future__ import annotations

from dataclasses import MISSING
from typing import TYPE_CHECKING

import torch

from genesislab.utils.configclass import configclass

from ..actuator_pd import IdealPDActuator
from ..articulation_actions import ArticulationActions
from ..actuator_pd_cfg import IdealPDActuatorCfg

if TYPE_CHECKING:
    pass


class UnitreeActuator(IdealPDActuator):
    """Unitree actuator class that implements a torque-speed curve for the actuators.

    The torque-speed curve is defined as follows:

            Torque, N·m
                ^
    Y2──────────|
                |──────────────Y1
                |              │\
                |              │ \
                |              │  \
                |              |   \
    ------------+--------------|------> velocity: rad/s
                              X1   X2

    Y1: Peak Torque Test (Torque and Speed in the Same Direction)
    Y2: Peak Torque Test (Torque and Speed in the Opposite Direction)
    X1: Maximum Speed at Full Torque (T-N Curve Knee Point)
    X2: No-Load Speed Test
    """

    cfg: "UnitreeActuatorCfg"

    def __init__(self, cfg: "UnitreeActuatorCfg", *args, **kwargs):
        super().__init__(cfg, *args, **kwargs)

        assert cfg.X1 < cfg.X2, "X1 must be less than X2"
        assert cfg.Y1 <= cfg.Y2, "Y1 must be less than or equal to Y2"

        self._joint_vel = torch.zeros_like(self.computed_effort)
        self._effort_y1 = torch.tensor(cfg.Y1, dtype=self.computed_effort.dtype, device=self.computed_effort.device)
        self._effort_y2 = torch.tensor(cfg.Y2, dtype=self.computed_effort.dtype, device=self.computed_effort.device)
        self._velocity_x1 = torch.tensor(cfg.X1, dtype=self.computed_effort.dtype, device=self.computed_effort.device)
        self._velocity_x2 = torch.tensor(cfg.X2, dtype=self.computed_effort.dtype, device=self.computed_effort.device)

    def compute(
        self, control_action: ArticulationActions, joint_pos: torch.Tensor, joint_vel: torch.Tensor
    ) -> ArticulationActions:
        # Save current joint vel (ensure shape matches)
        if joint_vel.shape == self._joint_vel.shape:
            self._joint_vel[:] = joint_vel
        else:
            # Reshape or slice to match actuator's joint count
            if joint_vel.shape[-1] > self._joint_vel.shape[-1]:
                # If joint_vel has more DOFs, take only the first num_joints
                self._joint_vel[:] = joint_vel[:, :self._joint_vel.shape[-1]]
            else:
                # If joint_vel has fewer DOFs, pad with zeros or expand
                self._joint_vel[:, :joint_vel.shape[-1]] = joint_vel
                self._joint_vel[:, joint_vel.shape[-1]:] = 0.0
        # Calculate the desired joint torques
        return super().compute(control_action, joint_pos, joint_vel)

    def _clip_effort(self, effort: torch.Tensor) -> torch.Tensor:
        # Ensure _joint_vel has the same shape as effort
        if self._joint_vel.shape != effort.shape:
            # Reshape _joint_vel to match effort shape
            if effort.shape[-1] <= self._joint_vel.shape[-1]:
                self._joint_vel = self._joint_vel[:, :effort.shape[-1]]
            else:
                # Pad with zeros if effort has more joints
                padded = torch.zeros_like(effort)
                padded[:, :self._joint_vel.shape[-1]] = self._joint_vel
                self._joint_vel = padded
        
        # Check if the effort is the same direction as the joint velocity
        same_direction = (self._joint_vel * effort) > 0
        
        # Ensure effort limits are scalar tensors for proper broadcasting
        # They should broadcast to (num_envs, num_joints) shape
        effort_y1 = self._effort_y1 if self._effort_y1.dim() == 0 else self._effort_y1.squeeze()
        effort_y2 = self._effort_y2 if self._effort_y2.dim() == 0 else self._effort_y2.squeeze()
        velocity_x1 = self._velocity_x1 if self._velocity_x1.dim() == 0 else self._velocity_x1.squeeze()
        
        max_effort = torch.where(same_direction, effort_y1, effort_y2)
        # Check if the joint velocity is less than the max speed at full torque
        max_effort = torch.where(
            self._joint_vel.abs() < velocity_x1, max_effort, self._compute_effort_limit(max_effort)
        )
        return torch.clip(effort, -max_effort, max_effort)

    def _compute_effort_limit(self, max_effort):
        # Ensure velocity limits are scalar tensors for proper broadcasting
        velocity_x1 = self._velocity_x1 if self._velocity_x1.dim() == 0 else self._velocity_x1.squeeze()
        velocity_x2 = self._velocity_x2 if self._velocity_x2.dim() == 0 else self._velocity_x2.squeeze()
        
        k = -max_effort / (velocity_x2 - velocity_x1)
        limit = k * (self._joint_vel.abs() - velocity_x1) + max_effort
        return limit.clip(min=0.0)


@configclass
class UnitreeActuatorCfg(IdealPDActuatorCfg):
    """Configuration for Unitree actuators."""

    class_type: type = UnitreeActuator

    X1: float = MISSING
    """Maximum Speed at Full Torque (T-N Curve Knee Point) Unit: rad/s"""

    X2: float = MISSING
    """No-Load Speed Test Unit: rad/s"""

    Y1: float = MISSING
    """Peak Torque Test (Torque and Speed in the Same Direction) Unit: N*m"""

    Y2: float = MISSING
    """Peak Torque Test (Torque and Speed in the Opposite Direction) Unit: N*m"""


# Predefined Unitree actuator configurations
@configclass
class UnitreeActuatorCfg_M107_15(UnitreeActuatorCfg):
    """Unitree M107-15 actuator configuration."""

    X1 = 14.0
    X2 = 25.6
    Y1 = 150.0
    Y2 = 102.8


@configclass
class UnitreeActuatorCfg_M107_24(UnitreeActuatorCfg):
    """Unitree M107-24 actuator configuration."""

    X1 = 8.8
    X2 = 16
    Y1 = 240
    Y2 = 292.5


@configclass
class UnitreeActuatorCfg_Go2HV(UnitreeActuatorCfg):
    """Unitree Go2HV actuator configuration."""

    X1 = 13.5
    X2 = 30
    Y1 = 20.2
    Y2 = 23.4


@configclass
class UnitreeActuatorCfg_N7520_14p3(UnitreeActuatorCfg):
    """Unitree N7520-14.3 actuator configuration."""

    X1 = 22.63
    X2 = 35.52
    Y1 = 71
    Y2 = 83.3


@configclass
class UnitreeActuatorCfg_N7520_22p5(UnitreeActuatorCfg):
    """Unitree N7520-22.5 actuator configuration."""

    X1 = 14.5
    X2 = 22.7
    Y1 = 111.0
    Y2 = 131.0


@configclass
class UnitreeActuatorCfg_N5010_16(UnitreeActuatorCfg):
    """Unitree N5010-16 actuator configuration."""

    X1 = 27.0
    X2 = 41.5
    Y1 = 9.5
    Y2 = 17.0


@configclass
class UnitreeActuatorCfg_N5020_16(UnitreeActuatorCfg):
    """Unitree N5020-16 actuator configuration."""

    X1 = 30.86
    X2 = 40.13
    Y1 = 24.8
    Y2 = 31.9


@configclass
class UnitreeActuatorCfg_W4010_25(UnitreeActuatorCfg):
    """Unitree W4010-25 actuator configuration."""

    X1 = 15.3
    X2 = 24.76
    Y1 = 4.8
    Y2 = 8.6
