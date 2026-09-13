"""Base class for Genesis-native sensor wrappers.

Genesis sensors wrap a gs.sensors.* object that is added to the Genesis scene.
The base cfg provides build_genesis_sensor(gs_scene, lab_scene) so that
SceneBuilder can create the underlying sensor and inject it into the wrapper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from genesislab.utils.configclass import configclass

from ..sensor_base import SensorBase, SensorBaseCfg
from .genesis_sensor_types import GenesisSensorHandle

if TYPE_CHECKING:
    import genesis as gs
    from genesislab.engine.scene.lab_scene import LabScene


class GenesisSensorBase(SensorBase):
    """Base for sensors that wrap a Genesis gs.sensors.* object.

    The underlying Genesis sensor is created by the cfg's build_genesis_sensor()
    and passed in as genesis_sensor= in the constructor or via set_genesis_sensor().
    """

    cfg: "GenesisSensorBaseCfg"

    def set_genesis_sensor(self, genesis_sensor: GenesisSensorHandle) -> None:
        """Attach the underlying Genesis sensor. Override in subclasses if needed."""
        if hasattr(self, "_gs_sensor"):
            self._gs_sensor = genesis_sensor


@configclass
class GenesisSensorBaseCfg(SensorBaseCfg):
    """Base configuration for Genesis-native sensor wrappers.

    Subclasses must implement build_genesis_sensor(gs_scene, lab_scene) to
    create the gs.sensors.* instance and add it to the scene.
    """

    class_type: type["GenesisSensorBase"] = GenesisSensorBase
    entity_name: str = None
    """Entity name for sensors attached to a robot/entity (e.g. IMU, Contact)."""

    def build_genesis_sensor(
        self, gs_scene: "gs.Scene", lab_scene: "LabScene"
    ) -> GenesisSensorHandle:
        """Create and add the Genesis sensor to gs_scene; return the handle.

        Called by SceneBuilder before instantiating the wrapper. The returned
        handle is passed to the wrapper as genesis_sensor=.

        Args:
            gs_scene: The Genesis Scene (before or after build()).
            lab_scene: LabScene for resolving entity_name, num_envs, etc.

        Returns:
            The Genesis sensor object (e.g. from gs_scene.add_sensor(...)).
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement build_genesis_sensor(gs_scene, lab_scene)."
        )
