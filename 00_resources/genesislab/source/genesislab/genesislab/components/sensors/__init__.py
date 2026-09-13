"""Sensor implementations for GenesisLab.

Two groups:

* **Fake sensors** (``fake_sensors``): Use only privileged/framework data (e.g.
  entity state, contact forces from the engine). No Genesis gs.sensors.* object.
* **Genesis sensors** (``genesis_sensors``): Wrap a gs.sensors.* instance that is
  added to the Genesis scene. SceneBuilder creates the underlying sensor and
  injects it into the wrapper.
"""

from .sensor_base import SensorBase, SensorBaseCfg
from .fake_sensors import (
    FakeSensorBase,
    FakeSensorBaseCfg,
    FakeContactSensor,
    FakeContactSensorCfg,
)
from .genesis_sensors import (
    GenesisSensorBase,
    GenesisSensorBaseCfg,
    GenesisContactBoolSensor,
    GenesisContactBoolSensorCfg,
    GenesisImuSensor,
    GenesisImuSensorCfg,
    GenesisCameraSensor,
    GenesisCameraSensorCfg,
    GenesisLidarSensor,
    GenesisLidarSensorCfg,
    GenesisDepthCameraSensor,
    GenesisDepthCameraSensorCfg,
)

__all__ = [
    "SensorBase",
    "SensorBaseCfg",
    "FakeSensorBase",
    "FakeSensorBaseCfg",
    "FakeContactSensor",
    "FakeContactSensorCfg",
    "GenesisSensorBase",
    "GenesisSensorBaseCfg",
    "GenesisContactBoolSensor",
    "GenesisContactBoolSensorCfg",
    "GenesisImuSensor",
    "GenesisImuSensorCfg",
    "GenesisCameraSensor",
    "GenesisCameraSensorCfg",
    "GenesisLidarSensor",
    "GenesisLidarSensorCfg",
    "GenesisDepthCameraSensor",
    "GenesisDepthCameraSensorCfg",
]
