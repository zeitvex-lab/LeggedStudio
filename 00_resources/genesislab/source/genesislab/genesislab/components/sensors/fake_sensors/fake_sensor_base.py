"""Base class for fake sensors in GenesisLab.

Fake sensors are built from privileged information within our framework (e.g.
entity state, contact forces from the engine) and do not require a Genesis
sensor object. They share common config such as entity_name for attachment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from genesislab.utils.configclass import configclass

from ..sensor_base import SensorBase, SensorBaseCfg


class FakeSensorBase(SensorBase):
    """Base for sensors that use only framework/privileged data (no gs.sensors.*).

    Subclasses typically read from a LabEntity or raw entity (e.g. contact
    forces) and expose a SensorBase-compatible :attr:`data` interface.
    """

    cfg: "FakeSensorBaseCfg"


@configclass
class FakeSensorBaseCfg(SensorBaseCfg):
    """Base configuration for fake sensors.

    Common options:
        entity_name: Name of the scene entity this sensor is attached to
            (e.g. "robot"). Used by SceneBuilder to inject the entity.
    """

    class_type: type["FakeSensorBase"] = FakeSensorBase
    entity_name: str = None
