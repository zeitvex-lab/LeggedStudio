"""Base configuration for velocity tracking locomotion tasks.

This module provides base configuration classes and factory functions for velocity tracking
locomotion tasks, following the same design patterns as mjlab/IsaacLab's velocity locomotion
environments.
"""

import math
from dataclasses import MISSING

from genesislab.engine.scene import SceneCfg, TerrainCfg
from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnvCfg
from genesislab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from genesislab.managers.action_manager import ActionTermCfg
from genesislab.managers.reward_manager import RewardTermCfg
from genesislab.managers.termination_manager import TerminationTermCfg
from genesislab.managers.command_manager import CommandTermCfg
from genesislab.managers.curriculum_manager import CurriculumTermCfg
from genesislab.managers import SceneEntityCfg, EventTermCfg
from genesislab.utils.configclass import configclass

import genesis_tasks.locomotion.velocity.mdp as mdp

from genesislab.components.sensors.fake_sensors import FakeContactSensorCfg
from genesislab.components.terrains import (
    GenesisTerrainMorphCfg,
    TerrainSurfaceCfg,
)

##
# MDP settings (configclass-based, for direct use in task configs)
##

@configclass
class VelocitySceneCfg(SceneCfg):
    num_envs    : int = 4096
    env_spacing : tuple = (2.5, 2.5)
    dt          : float = 0.005
    substeps    : int = 1
    backend     : str = "cuda"
    viewer      : bool = False

    # Terrain: Genesis native rough heightfield based on genesis-forge example
    terrain     : TerrainCfg = TerrainCfg(
        terrain_type="genesisbase",
        terrain_details_cfg=GenesisTerrainMorphCfg(
            pos=(-12.0, -12.0, 0.0),
            n_subterrains=(1, 1),
            subterrain_size=(24.0, 24.0),
            vertical_scale=0.001,
            subterrain_types=[["random_uniform_terrain"]],
        ),
        surface_cfg=TerrainSurfaceCfg(
            # Default surface; users can override color/texture in task-specific cfgs
            diffuse_color=None,
        ),
    )
    robots      : dict = {"robot": None}
    sensors     : dict = {
        "contact_forces": FakeContactSensorCfg(
            entity_name="robot",
            history_length=3,
            track_air_time=True,
        )
    }

@configclass
class CommandsCfg:
    """Command specifications for the MDP."""

    base_velocity: mdp.UniformVelocityCommandCfg = mdp.UniformVelocityCommandCfg(
        asset_name="robot",
        resampling_time_range=(10.0, 10.0),
        rel_standing_envs=0.02,
        rel_heading_envs=1.0,
        heading_command=True,
        heading_control_stiffness=0.5,
        init_velocity_prob=0.0,
        ranges=mdp.UniformVelocityCommandCfg.Ranges(
            lin_vel_x=(-1.0, 1.0),
            lin_vel_y=(-1.0, 1.0),
            ang_vel_z=(-1.0, 1.0),
            heading=(-math.pi, math.pi),
        ),
    )
    """Base velocity command configuration."""


@configclass
class ActionsCfg:
    """Action specifications for the MDP."""

    joint_pos: mdp.JointPositionActionCfg = mdp.JointPositionActionCfg(
            entity_name="robot",
            joint_names=[".*"],
            scale=0.5,
            use_default_offset=True,
        )
    """Joint position action configuration."""


@configclass
class ObservationsCfg:
    """Observation specifications for the MDP."""

    @configclass
    class PolicyCfg(ObservationGroupCfg):
        """Observations for policy group."""

        # Observation terms (order preserved)
        base_lin_vel: ObservationTermCfg = ObservationTermCfg(func=mdp.base_lin_vel)
        base_ang_vel: ObservationTermCfg = ObservationTermCfg(func=mdp.base_ang_vel)
        projected_gravity: ObservationTermCfg = ObservationTermCfg(func=mdp.projected_gravity)
        velocity_commands: ObservationTermCfg = ObservationTermCfg(
            func=mdp.generated_commands, params={"command_name": "base_velocity"}
        )
        joint_pos: ObservationTermCfg = ObservationTermCfg(func=mdp.joint_pos_rel)
        joint_vel: ObservationTermCfg = ObservationTermCfg(func=mdp.joint_vel_rel)
        actions: ObservationTermCfg = ObservationTermCfg(func=mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    # Observation groups
    policy: PolicyCfg = PolicyCfg()


@configclass
class RewardsCfg:
    """Reward terms for the MDP."""

    # Task rewards
    track_lin_vel_xy_exp: RewardTermCfg = RewardTermCfg(
        func=mdp.track_lin_vel_xy_exp,
        weight=2.5,
        params={"command_name": "base_velocity", "std": math.sqrt(0.25)},
    )
    track_ang_vel_z_exp: RewardTermCfg = RewardTermCfg(
        func=mdp.track_ang_vel_z_exp,
        weight=1.0,
        params={"command_name": "base_velocity", "std": math.sqrt(0.25)},
    )

    # Penalties
    lin_vel_z_l2: RewardTermCfg = RewardTermCfg(func=mdp.lin_vel_z_l2, weight=-0.1)
    ang_vel_xy_l2: RewardTermCfg = RewardTermCfg(func=mdp.ang_vel_xy_l2, weight=-0.1)
    dof_torques_l2: RewardTermCfg = RewardTermCfg(func=mdp.joint_torques_l2, weight=-1.0e-5)
    dof_acc_l2: RewardTermCfg = RewardTermCfg(func=mdp.joint_acc_l2, weight=-2.5e-7)
    action_rate_l2: RewardTermCfg = RewardTermCfg(func=mdp.action_rate_l2, weight=-0.01)

    # feet_air_time: RewardTermCfg = RewardTermCfg(
    #     func=mdp.feet_air_time,
    #     weight=0.125,
    #     params={
    #         "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_calf"),
    #         "command_name": "base_velocity",
    #         "threshold": 0.5,
    #     },
    # )
    
    undesired_contacts: RewardTermCfg = RewardTermCfg(
        func=mdp.undesired_contacts,
        weight=-0.0,
        params={
            # Default to "base" for quadrupeds; humanoids like G1 override or disable
            # this in their task-specific configs if needed.
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names="base"),
            "threshold": 1.0,
        },
    )
    alive: RewardTermCfg = RewardTermCfg(func=mdp.alive, weight=0.1)
    # Optional penalties
    flat_orientation_l2: RewardTermCfg = RewardTermCfg(func=mdp.flat_orientation_l2, weight=0.0)
    dof_pos_limits: RewardTermCfg = RewardTermCfg(func=mdp.joint_pos_limits, weight=0.0)


@configclass
class TerminationsCfg:
    """Termination terms for the MDP."""

    time_out: TerminationTermCfg = TerminationTermCfg(func=mdp.time_out, time_out=True)

    # IsaacLab-style contact-based termination (currently a no-op without contact sensors,
    # but kept for configuration compatibility).
    base_contact: TerminationTermCfg = TerminationTermCfg(
        func=mdp.illegal_contact,
        time_out=False,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names="base"), "threshold": 1.0},
    )


@configclass
class CurriculumCfg:
    """Curriculum terms for the MDP."""

    terrain_levels: CurriculumTermCfg = None
    """Terrain levels curriculum (optional)."""


@configclass
class EventsCfg:
    """Event terms for the MDP (startup/reset/interval events)."""

    # Startup events (domain randomization-style; currently lightweight/no-op).
    physics_material: EventTermCfg = EventTermCfg(
        func=mdp.randomize_rigid_body_material,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg(entity_name="robot", body_names=".*"),
            "scale_range": (1.0, 1.0),
        },
    )

    add_base_mass: EventTermCfg = EventTermCfg(
        func=mdp.randomize_rigid_body_mass,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg(entity_name="robot", body_names="base"),
            "mass_distribution_params": (-0.0, 0.0),
            "operation": "add",
        },
    )

    base_com: EventTermCfg = EventTermCfg(
        func=mdp.randomize_rigid_body_com,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg(entity_name="robot", body_names="base"),
            "com_range": {"x": (-0.0, 0.0), "y": (-0.0, 0.0), "z": (-0.0, 0.0)},
        },
    )

    # Reset events (pose/joint state randomization).
    base_external_force_torque: EventTermCfg = EventTermCfg(
        func=mdp.apply_external_force_torque,
        mode="reset",
        params={
            "asset_cfg": SceneEntityCfg(entity_name="robot", body_names="base"),
            "force_range": (0.0, 0.0),
            "torque_range": (0.0, 0.0),
        },
    )

    reset_base: EventTermCfg = EventTermCfg(
        func=mdp.reset_root_state_uniform,
        mode="reset",
        params={
            "pose_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5), "z": (0.0, 0.0), "roll": (0.0, 0.0), "pitch": (0.0, 0.0), "yaw": (-3.14, 3.14)},
            "velocity_range": {
                "x": (-0.5, 0.5),
                "y": (-0.5, 0.5),
                "z": (-0.5, 0.5),
                "roll": (-0.5, 0.5),
                "pitch": (-0.5, 0.5),
                "yaw": (-0.5, 0.5),
            },
        },
    )

    reset_robot_joints: EventTermCfg = EventTermCfg(
        func=mdp.reset_joints_by_scale,
        mode="reset",
        params={
            "position_range": (0.5, 1.5),
            "velocity_range": (0.0, 0.0),
        },
    )

    # Interval events (occasional perturbations).
    push_robot: EventTermCfg = EventTermCfg(
        func=mdp.push_by_setting_velocity,
        mode="interval",
        interval_range_s=(10.0, 15.0),
        params={"velocity_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5), "z": (0.0, 0.0), "roll": (0.0, 0.0), "pitch": (0.0, 0.0), "yaw": (0.0, 0.0)}},
    )
