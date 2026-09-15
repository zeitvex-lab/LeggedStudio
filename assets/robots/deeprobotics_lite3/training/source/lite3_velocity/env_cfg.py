"""Deeprobotics Lite3 velocity environment configurations.

Rewritten against the official DeepRoboticsLab training configuration
(``rl_training .../config/quadruped/deeprobotics_lite3/rough_env_cfg.py``,
BSD-3-Clause).  Differences from the generic B2-style base:

- foot contact sensors on the shank bodies (Lite3 has no dedicated foot
  link; the shank tip sphere is the contact point),
- gait_level curriculum scalar fed by the terrain curriculum and gating
  several rewards,
- official reward table (24 terms incl. Bezier swing tracking, trot gait
  sync, command-gated air times, foot impact velocity),
- push / external-force / COM randomization disabled (source Lite3 cfg),
- illegal-contact termination disabled (bad_orientation kept).
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers import TerminationTermCfg
from mjlab.managers.observation_manager import ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import (
    ContactMatch,
    ContactSensorCfg,
    ObjRef,
    RayCastSensorCfg,
    RingPatternCfg,
    TerrainHeightSensorCfg,
)
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise

import mujoco

from . import lite3_rewards as lite3_mdp
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg
from .robot_constants import get_lite3_robot_cfg

# Root body name must match the MJCF root body (robot.xml:47 <body name="TORSO">);
# "base_link" does not exist in the MJCF and breaks mjlab raycast sensor init
# (ValueError: Invalid name 'robot/base_link').
_ROOT_BODY = "TORSO"
FOOT_PATTERN = r".*_SHANK"
FOOT_BODIES = [f"{lr}_SHANK" for lr in ("FL", "FR", "HL", "HR")]
NON_FOOT_PATTERN = r"^(?!.*_SHANK).*"

JOINT_GROUPS = {
    "hipx": [f"{lr}_HipX_joint" for lr in ("FL", "FR", "HL", "HR")],
    "hipy": [f"{lr}_HipY_joint" for lr in ("FL", "FR", "HL", "HR")],
    "knee": [f"{lr}_Knee_joint" for lr in ("FL", "FR", "HL", "HR")],
}
ALL_JOINTS = JOINT_GROUPS["hipx"] + JOINT_GROUPS["hipy"] + JOINT_GROUPS["knee"]



def _configure_height_sensors(cfg: ManagerBasedRlEnvCfg) -> None:
    for sensor in cfg.scene.sensors or ():
        if sensor.name == "terrain_scan":
            assert isinstance(sensor, RayCastSensorCfg)
            assert isinstance(sensor.frame, ObjRef)
            sensor.frame.name = _ROOT_BODY
        elif sensor.name == "foot_height_scan":
            assert isinstance(sensor, TerrainHeightSensorCfg)
            # 帧=足端 body(MJCF robot.xml:68/92/115/138),site 不存在故用 body,语义=足端原点不变
            sensor.frame = tuple(
                ObjRef(type="body", name=f"{lr}_FOOT", entity="robot")
                for lr in ("FL", "FR", "HL", "HR")
            )
            sensor.pattern = RingPatternCfg.single_ring(radius=0.04, num_samples=4)


def _lite3_robot_cfg_with_named_sensors():
    """Lite3 robot EntityCfg with all MJCF sensors named.

    robot.xml:192-193 defines an unnamed <accelerometer>/<gyro> on imu_site.
    Scene._add_sensors auto-wraps every spec sensor via
    BuiltinSensor.from_existing(sns.name); an unnamed sensor yields '' and
    env construction dies at mj_model.sensor('') (KeyError: Invalid name '').
    Fix here (only env_cfg.py is editable): give unnamed sensors stable names
    (robot/imu_accelerometer, robot/imu_gyro after entity prefixing). Sensor
    type/site/semantics unchanged.
    """
    robot_cfg = get_lite3_robot_cfg()
    base_spec_fn = robot_cfg.spec_fn

    _TYPE_NAMES = {
        int(mujoco.mjtSensor.mjSENS_ACCELEROMETER): "imu_accelerometer",
        int(mujoco.mjtSensor.mjSENS_GYRO): "imu_gyro",
    }

    def spec_fn():
        spec = base_spec_fn()
        for sensor in spec.sensors:
            if not sensor.name:
                sensor.name = _TYPE_NAMES.get(
                    int(sensor.type), f"imu_sensor_{int(sensor.type)}"
                )
        return spec

    robot_cfg.spec_fn = spec_fn
    return robot_cfg

def lite3_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Lite3 rough-terrain configuration (official reward recipe)."""
    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = 500
    cfg.sim.contact_sensor_maxmatch = 500
    cfg.sim.nconmax = None  # full-body contact sensors need headroom
    cfg.scene.entities = {"robot": _lite3_robot_cfg_with_named_sensors()}
    _configure_height_sensors(cfg)

    all_joint_cfg = SceneEntityCfg("robot", joint_names=list(ALL_JOINTS), preserve_order=True)
    hipx_cfg = SceneEntityCfg("robot", joint_names=list(JOINT_GROUPS["hipx"]), preserve_order=True)
    hipy_cfg = SceneEntityCfg("robot", joint_names=list(JOINT_GROUPS["hipy"]), preserve_order=True)
    knee_cfg = SceneEntityCfg("robot", joint_names=list(JOINT_GROUPS["knee"]), preserve_order=True)
    foot_cfg = SceneEntityCfg("robot", body_names=FOOT_BODIES)
    # Reward functions look up contact sensors through ContactSensorRef.
    feet_sensor = lite3_mdp.ContactSensorRef("foot_contact", (0, 1, 2, 3))
    non_foot_sensor = lite3_mdp.ContactSensorRef("full_contact", None)
    non_foot_cfg = SceneEntityCfg("robot", body_names=[NON_FOOT_PATTERN])

    ##
    # Actions: position targets on all 12 joints
    ##
    cfg.actions["joint_pos"] = JointPositionActionCfg(
        entity_name="robot",
        actuator_names=r".*",
        preserve_order=True,
        scale={
            "FL_HipX_joint": 0.125, "FR_HipX_joint": 0.125,
            "HL_HipX_joint": 0.125, "HR_HipX_joint": 0.125,
            "FL_HipY_joint": 0.25, "FR_HipY_joint": 0.25,
            "HL_HipY_joint": 0.25, "HR_HipY_joint": 0.25,
            "FL_Knee_joint": 0.25, "FR_Knee_joint": 0.25,
            "HL_Knee_joint": 0.25, "HR_Knee_joint": 0.25,
        },
        use_default_offset=True,
    )

    ##
    # Sensors: shank contact (air time) + full-body contact forces
    ##
    foot_contact = ContactSensorCfg(
        name="foot_contact",
        primary=ContactMatch(mode="body", pattern=FOOT_PATTERN, entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("force",),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    full_contact = ContactSensorCfg(
        name="full_contact",
        primary=ContactMatch(mode="body", pattern=r".*", entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("force",),
        reduce="netforce",
        num_slots=1,
    )
    cfg.scene.sensors = (cfg.scene.sensors or ()) + (foot_contact, full_contact)

    ##
    # Terrain: random rough 0.4 + pyramid slopes 0.3/0.3 (boxes/stairs off)
    ##
    if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
        tg = cfg.scene.terrain.terrain_generator
        tg.curriculum = True
        tg.sub_terrains["random_rough"].proportion = 0.4
        tg.sub_terrains["random_rough"].noise_range = (0.01, 0.06)
        tg.sub_terrains["random_rough"].noise_step = 0.01
        if "hf_pyramid_slope" in tg.sub_terrains:
            tg.sub_terrains["hf_pyramid_slope"].proportion = 0.3
        if "hf_pyramid_slope_inv" in tg.sub_terrains:
            tg.sub_terrains["hf_pyramid_slope_inv"].proportion = 0.3
        for key in ("boxes", "pyramid_stairs", "pyramid_stairs_inv"):
            if key in tg.sub_terrains:
                tg.sub_terrains[key].proportion = 0.0

    ##
    # Commands
    ##
    twist_cmd = cfg.commands["twist"]
    assert isinstance(twist_cmd, UniformVelocityCommandCfg)
    twist_cmd.heading_command = True
    twist_cmd.resampling_time_range = (10.0, 10.0)
    twist_cmd.ranges.lin_vel_x = (-1.5, 1.5)
    twist_cmd.ranges.lin_vel_y = (-0.8, 0.8)
    twist_cmd.ranges.ang_vel_z = (-0.8, 0.8)
    twist_cmd.ranges.heading = (-3.14, 3.14)

    ##
    # Observations: 45-dim rl_sdk layout (no lin_vel, no height scan)
    ##
    for group_name in ("actor", "critic"):
        cfg.observations[group_name].terms = {
            "base_ang_vel": ObservationTermCfg(
                func=envs_mdp.base_ang_vel, noise=Unoise(n_min=-0.2, n_max=0.2) if group_name == "actor" else None
            ),
            "projected_gravity": ObservationTermCfg(
                func=envs_mdp.projected_gravity,
                noise=Unoise(n_min=-0.05, n_max=0.05) if group_name == "actor" else None,
            ),
            "command": ObservationTermCfg(func=envs_mdp.generated_commands, params={"command_name": "twist"}),
            "joint_pos_rel": ObservationTermCfg(
                func=envs_mdp.joint_pos_rel,
                params={"asset_cfg": all_joint_cfg},
                noise=Unoise(n_min=-0.01, n_max=0.01) if group_name == "actor" else None,
            ),
            "joint_vel_rel": ObservationTermCfg(
                func=envs_mdp.joint_vel_rel,
                params={"asset_cfg": all_joint_cfg},
                noise=Unoise(n_min=-1.5, n_max=1.5) if group_name == "actor" else None,
            ),
            "actions": ObservationTermCfg(func=envs_mdp.last_action),
        }

    ##
    # Events: Lite3 disables push / external force / COM randomization
    ##
    cfg.events.pop("push_robot", None)
    cfg.events.pop("randomize_apply_external_force_torque", None)
    cfg.events.pop("base_com", None)
    if "randomize_actuator_gains" in cfg.events:
        cfg.events["randomize_actuator_gains"].params["asset_cfg"].joint_names = list(ALL_JOINTS)

    ##
    # Rewards: official table
    ##
    cfg.rewards = {
        "track_lin_vel_xy_exp": RewardTermCfg(
            func=velocity_mdp.track_linear_velocity, weight=4.0, params={"command_name": "twist", "std": 0.425}
        ),
        "track_ang_vel_z_exp": RewardTermCfg(
            func=velocity_mdp.track_angular_velocity, weight=1.5, params={"command_name": "twist", "std": 0.425}
        ),
        "feet_air_time_lin_xy": RewardTermCfg(
            func=lite3_mdp.feet_air_time_lin_xy_cmd,
            weight=5.0,
            params={"command_name": "twist", "threshold": 0.5, "sensor_cfg": feet_sensor},
        ),
        "feet_air_time_ang_z": RewardTermCfg(
            func=lite3_mdp.feet_air_time_ang_z_cmd_lite3,
            weight=5.0,
            params={"command_name": "twist", "threshold": 0.5, "sensor_cfg": feet_sensor},
        ),
        "feet_gait": RewardTermCfg(
            func=lite3_mdp.feet_gait,
            weight=0.5,
            params={
                "command_name": "twist",
                "std": 0.5,
                "max_err": 0.5,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
                "sensor_cfg": feet_sensor,
                "synced_feet_pair_names": [["FL_SHANK", "HR_SHANK"], ["FR_SHANK", "HL_SHANK"]],
            },
        ),
        "phase_foot_trajectory_exp": RewardTermCfg(
            func=lite3_mdp.phase_foot_trajectory_exp,
            weight=2.0,
            params={
                "command_name": "twist",
                "asset_cfg": foot_cfg,
                "cycle_time": 0.425,
                "phase_offsets": (0.0, 1.0, 1.0, 0.0),
            },
        ),
        "feet_slide": RewardTermCfg(
            func=lite3_mdp.feet_slide, weight=-0.05, params={"sensor_cfg": feet_sensor, "asset_cfg": foot_cfg}
        ),
        "foot_impact_velocity": RewardTermCfg(
            func=lite3_mdp.foot_impact_velocity,
            weight=-2.0,
            params={"sensor_cfg": feet_sensor, "asset_cfg": foot_cfg},
        ),
        "stand_still": RewardTermCfg(
            func=lite3_mdp.stand_still_joint_deviation_l1,
            weight=-0.5,
            params={"command_name": "twist", "command_threshold": 0.1, "asset_cfg": all_joint_cfg},
        ),
        "feet_contact_without_cmd": RewardTermCfg(
            func=lite3_mdp.feet_contact_without_cmd,
            weight=0.1,
            params={"command_name": "twist", "sensor_cfg": feet_sensor},
        ),
        "contact_forces": RewardTermCfg(
            func=lite3_mdp.contact_forces, weight=-0.1, params={"sensor_cfg": feet_sensor, "threshold": 100.0}
        ),
        "lin_vel_z_l2": RewardTermCfg(func=lite3_mdp.lin_vel_z_l2, weight=-20.0),
        "ang_vel_xy_l2": RewardTermCfg(func=lite3_mdp.ang_vel_xy_l2, weight=-0.25),
        "flat_orientation_l2": RewardTermCfg(func=lite3_mdp.flat_orientation_l2, weight=-20.0),
        "base_height_l2": RewardTermCfg(
            func=lite3_mdp.base_height_l2, weight=-50.0, params={"target_height": 0.55}
        ),
        "undesired_contacts": RewardTermCfg(
            func=lite3_mdp.undesired_contacts,
            weight=-0.5,
            params={"sensor_cfg": non_foot_sensor, "threshold": 1.0},
        ),
        "joint_torques_l2": RewardTermCfg(
            func=envs_mdp.joint_torques_l2, weight=-2.5e-4, params={"asset_cfg": all_joint_cfg}
        ),
        "joint_acc_l2": RewardTermCfg(
            func=envs_mdp.joint_acc_l2, weight=-1e-8, params={"asset_cfg": all_joint_cfg}
        ),
        "joint_power": RewardTermCfg(
            func=lite3_mdp.joint_power, weight=-8e-4, params={"asset_cfg": all_joint_cfg}
        ),
        "joint_pos_limits": RewardTermCfg(
            func=envs_mdp.joint_pos_limits, weight=-5.0, params={"asset_cfg": all_joint_cfg}
        ),
        "joint_mirror": RewardTermCfg(
            func=lite3_mdp.joint_mirror,
            weight=-0.05,
            params={
                "asset_cfg": all_joint_cfg,
                "mirror_joints": [
                    ["FL_(HipX|HipY|Knee).*", "HR_(HipX|HipY|Knee).*"],
                    ["FR_(HipX|HipY|Knee).*", "HL_(HipX|HipY|Knee).*"],
                ],
            },
        ),
        "hipx_joint_pos_penalty": RewardTermCfg(
            func=lite3_mdp.joint_pos_penalty,
            weight=-0.4,
            params={
                "command_name": "twist",
                "asset_cfg": hipx_cfg,
                "stand_still_scale": 5.0,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
            },
        ),
        "hipy_joint_pos_penalty": RewardTermCfg(
            func=lite3_mdp.joint_pos_penalty,
            weight=0.0,
            params={
                "command_name": "twist",
                "asset_cfg": hipy_cfg,
                "stand_still_scale": 5.0,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
            },
        ),
        "knee_joint_pos_penalty": RewardTermCfg(
            func=lite3_mdp.joint_pos_penalty,
            weight=-2.0,
            params={
                "command_name": "twist",
                "asset_cfg": knee_cfg,
                "stand_still_scale": 5.0,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
            },
        ),
    }

    ##
    # Viewer / events / terminations / curriculum
    ##
    cfg.viewer.body_name = "TORSO"
    cfg.viewer.distance = 1.5
    cfg.viewer.elevation = -10.0

    cfg.terminations.pop("illegal_contact", None)
    cfg.curriculum.pop("command_vel", None)

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["actor"].enable_corruption = False
        cfg.curriculum = {}
        if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
            terrain = cfg.scene.terrain.terrain_generator
            terrain.curriculum = False
            terrain.num_cols = 5
            terrain.num_rows = 5
            terrain.border_width = 10.0
    return cfg


def lite3_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Lite3 flat-ground variant."""
    cfg = lite3_rough_env_cfg(play=play)
    cfg.sim.njmax = 300
    cfg.sim.mujoco.ccd_iterations = 50
    cfg.sim.contact_sensor_maxmatch = 64
    cfg.sim.nconmax = None
    assert cfg.scene.terrain is not None
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.curriculum.pop("terrain_levels", None)
    return cfg


def lite3_runner_cfg():
    """Official Lite3 PPO runner config (rl_training rsl_rl_ppo_cfg)."""
    from mjlab.rl import (
        RslRlModelCfg,
        RslRlOnPolicyRunnerCfg,
        RslRlPpoAlgorithmCfg,
    )

    return RslRlOnPolicyRunnerCfg(
        actor=RslRlModelCfg(
            hidden_dims=(512, 256, 128),
            activation="elu",
            obs_normalization=True,
            distribution_cfg={
                "class_name": "GaussianDistribution",
                "init_std": 1.0,
                "std_type": "scalar",
            },
        ),
        critic=RslRlModelCfg(
            hidden_dims=(512, 256, 128),
            activation="elu",
            obs_normalization=True,
        ),
        algorithm=RslRlPpoAlgorithmCfg(
            value_loss_coef=1.0,
            use_clipped_value_loss=True,
            clip_param=0.2,
            entropy_coef=0.01,
            num_learning_epochs=5,
            num_mini_batches=4,
            learning_rate=1.0e-3,
            schedule="adaptive",
            gamma=0.99,
            lam=0.95,
            desired_kl=0.01,
            max_grad_norm=1.0,
        ),
        experiment_name="lite3_velocity",
        save_interval=100,
        num_steps_per_env=24,
        max_iterations=10_000,
    )
