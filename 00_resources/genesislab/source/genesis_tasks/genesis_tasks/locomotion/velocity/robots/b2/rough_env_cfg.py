"""Configuration for Unitree B2 velocity tracking task on rough terrain."""

from genesislab.managers import SceneEntityCfg
from genesislab.utils.configclass import configclass

from ...base_velocity_env_cfg import BaseVelocityEnvCfg
from genesis_assets.robots import UNITREE_B2_CFG
import genesis_tasks.locomotion.velocity.mdp as mdp


@configclass
class UnitreeB2RoughEnvCfg(BaseVelocityEnvCfg):
    """Configuration for Unitree B2 velocity tracking on rough terrain."""

    def __post_init__(self):
        # Post init of parent
        super().__post_init__()

        self.scene.robots["robot"] = UNITREE_B2_CFG

        # Scale down terrains for small robot
        if hasattr(self.scene.terrain, "terrain_generator") and self.scene.terrain.terrain_generator is not None:
            if hasattr(self.scene.terrain.terrain_generator, "sub_terrains"):
                sub_terrains = self.scene.terrain.terrain_generator.sub_terrains
                if "boxes" in sub_terrains:
                    sub_terrains["boxes"].grid_height_range = (0.025, 0.1)
                if "random_rough" in sub_terrains:
                    sub_terrains["random_rough"].noise_range = (0.01, 0.06)
                    sub_terrains["random_rough"].noise_step = 0.01

        # Actions: align with genesis-forge style (B2 has multiple actuator groups, no single actuator_name)
        self.actions.joint_pos.scale = 0.25
        self.actions.joint_pos.use_default_offset = True

        # Rewards: align with IsaacLab-style velocity config
        self.rewards.dof_torques_l2.weight = -0.001
        self.rewards.track_lin_vel_xy_exp.weight = 2.5
        self.rewards.track_ang_vel_z_exp.weight = 1.25
        self.rewards.dof_acc_l2.weight = -2.5e-7

        # Events: align with IsaacLab-style config
        if getattr(self, "events", None) is not None:
            self.events.push_robot = None
            if getattr(self.events, "add_base_mass", None) is not None:
                self.events.add_base_mass.params["mass_distribution_params"] = (-1.0, 3.0)
                if isinstance(self.events.add_base_mass.params.get("asset_cfg"), SceneEntityCfg):
                    self.events.add_base_mass.params["asset_cfg"].body_names = "base"
            if getattr(self.events, "base_external_force_torque", None) is not None:
                if isinstance(self.events.base_external_force_torque.params.get("asset_cfg"), SceneEntityCfg):
                    self.events.base_external_force_torque.params["asset_cfg"].body_names = "base"
            if getattr(self.events, "reset_robot_joints", None) is not None:
                self.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)
            if getattr(self.events, "reset_base", None) is not None:
                self.events.reset_base.params = {
                    "pose_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5), "z": (0.0, 0.0), "roll": (0.0, 0.0), "pitch": (0.0, 0.0), "yaw": (-3.14, 3.14)},
                    "velocity_range": {
                        "x": (0.0, 0.0),
                        "y": (0.0, 0.0),
                        "z": (0.0, 0.0),
                        "roll": (0.0, 0.0),
                        "pitch": (0.0, 0.0),
                        "yaw": (0.0, 0.0),
                    },
                }
            if getattr(self.events, "base_com", None) is not None:
                self.events.base_com = None

        # Feet air-time and undesired contacts
        if hasattr(self.rewards, "feet_air_time") and self.rewards.feet_air_time is not None:
            self.rewards.feet_air_time.params["sensor_cfg"] = "contact_forces"
            self.rewards.feet_air_time.params["command_name"] = "base_velocity"
            self.rewards.feet_air_time.params["threshold"] = 0.5
            self.rewards.feet_air_time.weight = 0.01

        if hasattr(self.rewards, "undesired_contacts"):
            self.rewards.undesired_contacts = None


@configclass
class UnitreeB2RoughEnvCfg_PLAY(UnitreeB2RoughEnvCfg):
    """Configuration for Unitree B2 velocity tracking on rough terrain (play mode)."""

    def __post_init__(self):
        # Post init of parent
        super().__post_init__()

        # Make a smaller scene for play
        self.scene.num_envs = 50
        self.scene.env_spacing = (2.5, 2.5)
        if hasattr(self.scene.terrain, "max_init_terrain_level"):
            self.scene.terrain.max_init_terrain_level = None
        if hasattr(self.scene.terrain, "terrain_generator") and self.scene.terrain.terrain_generator is not None:
            terrain_gen = self.scene.terrain.terrain_generator
            if hasattr(terrain_gen, "num_rows"):
                terrain_gen.num_rows = 5
            if hasattr(terrain_gen, "num_cols"):
                terrain_gen.num_cols = 5
            if hasattr(terrain_gen, "curriculum"):
                terrain_gen.curriculum = False

        # Disable randomization for play
        self.observations.policy.enable_corruption = False
        if getattr(self, "events", None) is not None:
            if hasattr(self.events, "base_external_force_torque"):
                self.events.base_external_force_torque = None
            if hasattr(self.events, "push_robot"):
                self.events.push_robot = None
