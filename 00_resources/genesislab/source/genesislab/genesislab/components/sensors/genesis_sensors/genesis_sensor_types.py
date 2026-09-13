"""Typed handles for Genesis native sensors.

Use these types instead of Any for genesis_sensor parameters and
build_genesis_sensor return values. They reflect the interface each
wrapper expects from the underlying gs.sensors.* object.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GenesisSensorHandle(Protocol):
    """Base protocol for any Genesis sensor handle (Contact, IMU, Camera, Lidar, DepthCamera)."""

    pass


@runtime_checkable
class GenesisContactSensorHandle(Protocol):
    """Handle from gs.sensors.Contact; provides per-link contact booleans."""

    def read(self): ...
    """Return contact state (tensor or named tuple with contact/contacts field)."""


@runtime_checkable
class GenesisImuSensorHandle(Protocol):
    """Handle from gs.sensors.IMU; provides lin_acc and ang_vel."""

    def read(self): ...
    """Return named tuple with lin_acc and ang_vel (each 3D)."""


@runtime_checkable
class GenesisCameraSensorHandle(Protocol):
    """Handle from gs.sensors.RasterizerCameraOptions / Raytracer / BatchRenderer; provides RGB."""

    def read(self): ...
    """Return object with .rgb attribute (H,W,3) or (n_envs,H,W,3)."""


@runtime_checkable
class GenesisLidarSensorHandle(Protocol):
    """Handle from gs.sensors.Lidar; provides points and distances."""

    def read(self): ...
    """Return named tuple with points and distances."""


@runtime_checkable
class GenesisDepthCameraSensorHandle(Protocol):
    """Handle from gs.sensors.DepthCamera; provides depth image."""

    def read_image(self): ...
    """Return depth tensor (H,W) or (n_envs,H,W)."""
