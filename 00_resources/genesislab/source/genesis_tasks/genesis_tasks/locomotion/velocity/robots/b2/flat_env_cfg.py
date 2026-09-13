"""Configuration for Unitree B2 velocity tracking task on flat terrain."""

from genesislab.components.terrains import TerrainCfg
from genesislab.utils.configclass import configclass

from .rough_env_cfg import UnitreeB2RoughEnvCfg


@configclass
class UnitreeB2FlatEnvCfg(UnitreeB2RoughEnvCfg):
    """Configuration for Unitree B2 velocity tracking on flat terrain."""

    def __post_init__(self):
        # Post init of parent
        super().__post_init__()

        # Override rewards (follow IsaacLab-style flat config)
        self.rewards.flat_orientation_l2.weight = -2.5
        if hasattr(self.rewards, "feet_air_time") and self.rewards.feet_air_time is not None:
            self.rewards.feet_air_time.params["sensor_cfg"] = "contact_forces"
            self.rewards.feet_air_time.params["command_name"] = "base_velocity"
            self.rewards.feet_air_time.params["threshold"] = 0.5
            self.rewards.feet_air_time.weight = 0.25

        # Change terrain to flat
        self.scene.terrain = TerrainCfg(terrain_type="plane")
        if self.curriculum is not None:
            self.curriculum.terrain_levels = None


@configclass
class UnitreeB2FlatEnvCfg_PLAY(UnitreeB2FlatEnvCfg):
    """Configuration for Unitree B2 velocity tracking on flat terrain (play mode)."""

    def __post_init__(self):
        # Post init of parent
        super().__post_init__()

        # Make a smaller scene for play
        self.scene.num_envs = 50
        self.scene.env_spacing = (2.5, 2.5)
        # Disable randomization for play
        self.observations.policy.enable_corruption = False
