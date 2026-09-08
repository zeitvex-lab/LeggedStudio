"""LimX TRON1 point-foot velocity environment configuration.

Flat-ground velocity task built from the package-local robot constants and
mjlab's shared velocity base, adapted from LeggedGym-Ex
``legged_gym/envs/tron1pf/tron1pf_config.py`` (BSD-3):

- Policy observation: 27 dims = cmd(3) + projected_gravity(3) + ang_vel(3)
  + joint_pos(6) + joint_vel(6) + last_action(6), stacked with
  ``history_length=5`` (source ``frame_stack=5`` -> 135-dim policy input).
- Command ranges: lin_vel_x +-0.5, lin_vel_y +-0.6, ang_vel_z +-1 (heading mode).
- Rewards mapped to the source table: tracking 1.0/0.5, keep_balance 1.0,
  dof_pos_limits -2.0, feet_air_time 1.0, foot_clearance (target 0.07 m,
  source offset 0.032 m is the foot-sphere centre height), ang_vel_xy -0.05,
  action_rate -0.01, plus shared biped terms ``feet_distance_ours`` (-100),
  ``no_fly`` (0.5) and ``foot_landing_vel`` (-0.15) from
  ``adapters/mjlab/shared_rewards``.
- Terminations: base/non-foot contact (source ``terminate_after_contacts_on``
  base/abad), bad orientation (70 deg), timeout.
"""

from __future__ import annotations

from math import sqrt

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers import TerminationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import (
    ContactMatch,
    ContactSensorCfg,
    ObjRef,
    RingPatternCfg,
    TerrainHeightSensorCfg,
)
from mjlab.tasks.velocity import mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg

from shared_rewards import feet_distance_ours, foot_landing_vel, no_fly

from .robot_constants import TRON1_PF_ACTION_SCALE, get_tron1_pf_robot_cfg

_SITES = ("foot_L", "foot_R")
_FOOT_GEOMS = ("foot_L_collision", "foot_R_collision")
_FOOT_BODIES = ("foot_L_Link", "foot_R_Link")
_ROOT_BODY = "base_Link"

_HISTORY_LEN = 5  # source env.frame_stack / c_frame_stack


def _configure_foot_height_sensor(cfg: ManagerBasedRlEnvCfg) -> None:
    for sensor in cfg.scene.sensors or ():
        if sensor.name == "foot_height_scan":
            assert isinstance(sensor, TerrainHeightSensorCfg)
            sensor.frame = tuple(
                ObjRef(type="site", name=name, entity="robot") for name in _SITES
            )
            # Ring radius ~ foot sphere radius (0.032 m).
            sensor.pattern = RingPatternCfg.single_ring(radius=0.032, num_samples=4)


def _contact_sensors() -> tuple[ContactSensorCfg, ContactSensorCfg]:
    feet = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(mode="geom", pattern=_FOOT_GEOMS, entity="robot"),
            fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    other = ContactSensorCfg(
        name="nonfoot_ground_touch",
        primary=ContactMatch(
            mode="geom", pattern=".*_collision", entity="robot", exclude=_FOOT_GEOMS
        ),
            fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    return feet, other


def _restructure_actor_obs(cfg: ManagerBasedRlEnvCfg) -> None:
    """Rebuild the actor group to the source 27-dim layout and stack history.

    Source order: cmd, projected_gravity, ang_vel, dof_pos, dof_vel, action.
    ``base_lin_vel`` stays available to the critic only (privileged).
    """
    actor = cfg.observations["actor"]
    terms = dict(actor.terms)

    command = terms.pop("command")
    gravity = terms.pop("projected_gravity")
    ang_vel = terms.pop("base_ang_vel")
    ang_vel.scale = 0.25  # source obs_scales.ang_vel
    joint_pos = terms.pop("joint_pos")  # biased: dof_pos - default (scale 1.0)
    joint_vel = terms.pop("joint_vel")
    joint_vel.scale = 0.05  # source obs_scales.dof_vel
    actions = terms.pop("actions")
    terms.pop("base_lin_vel", None)
    terms.pop("height_scan", None)

    actor.terms = {
        "command": command,
        "projected_gravity": gravity,
        "base_ang_vel": ang_vel,
        "joint_pos": joint_pos,
        "joint_vel": joint_vel,
        "actions": actions,
    }
    actor.history_length = _HISTORY_LEN
    critic = cfg.observations["critic"]
    critic.history_length = _HISTORY_LEN  # source c_frame_stack


def _configure_rewards(cfg: ManagerBasedRlEnvCfg) -> None:
    cfg.rewards["track_linear_velocity"].weight = 1.0  # tracking_lin_vel
    cfg.rewards["track_angular_velocity"].weight = 0.5  # tracking_ang_vel
    cfg.rewards["upright"].weight = 1.0  # keep_balance
    cfg.rewards["body_ang_vel"].weight = -0.05  # ang_vel_xy
    cfg.rewards["dof_pos_limits"].weight = -2.0
    cfg.rewards["action_rate_l2"].weight = -0.01  # action_rate
    cfg.rewards["air_time"].weight = 1.0  # feet_air_time
    cfg.rewards["foot_clearance"].weight = -0.5
    cfg.rewards["foot_clearance"].params["target_height"] = 0.07
    cfg.rewards["foot_swing_height"].weight = 0.0
    cfg.rewards["soft_landing"].weight = 0.0
    cfg.rewards["foot_slip"].params["asset_cfg"].site_names = _SITES
    cfg.rewards["foot_clearance"].params["asset_cfg"].site_names = _SITES

    cfg.rewards["feet_distance"] = RewardTermCfg(
        func=feet_distance_ours,
        weight=-1.0,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=_FOOT_BODIES),
            "min_dist": 0.115,  # source rewards.foot_distance_threshold
            "weight": 100.0,  # source rewards.scales.feet_distance
        },
    )
    cfg.rewards["no_fly"] = RewardTermCfg(
        func=no_fly,
        weight=0.5,
        params={
            "sensor_cfg": SceneEntityCfg("feet_ground_contact"),
            "asset_cfg": SceneEntityCfg("robot", body_names=_FOOT_BODIES),
            "air_time_threshold": 0.3,
        },
    )
    cfg.rewards["foot_landing_vel"] = RewardTermCfg(
        func=foot_landing_vel,
        weight=-0.15,
        params={
            "sensor_cfg": SceneEntityCfg("feet_ground_contact"),
            "asset_cfg": SceneEntityCfg("robot", body_names=_FOOT_BODIES),
            "height_threshold": 0.1,  # source rewards.about_landing_threshold
        },
    )

    # Posture regularisation (variable_posture); source has no explicit
    # posture reward -- keep it light so the gait terms dominate.
    cfg.rewards["pose"].params["std_standing"] = {r".*_Joint": 0.05}
    moving = {r".*_Joint": 0.5}
    cfg.rewards["pose"].params["std_walking"] = moving
    cfg.rewards["pose"].params["std_running"] = moving


def make_tron1_pf_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground TRON1-PF velocity configuration (source trains on plane)."""
    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = 50
    cfg.sim.contact_sensor_maxmatch = 64
    cfg.sim.nconmax = None
    cfg.scene.entities = {"robot": get_tron1_pf_robot_cfg()}

    _configure_foot_height_sensor(cfg)
    feet_sensor, other_sensor = _contact_sensors()
    cfg.scene.sensors = (cfg.scene.sensors or ()) + (feet_sensor, other_sensor)

    assert cfg.scene.terrain is not None
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.scene.sensors = tuple(
        sensor for sensor in (cfg.scene.sensors or ()) if sensor.name != "terrain_scan"
    )

    action = cfg.actions["joint_pos"]
    assert isinstance(action, JointPositionActionCfg)
    action.scale = TRON1_PF_ACTION_SCALE

    cfg.viewer.body_name = _ROOT_BODY
    cfg.viewer.distance = 2.0
    cfg.viewer.elevation = -10.0

    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.resampling_time_range = (10.0, 10.0)  # source commands.resampling_time
    command.ranges.lin_vel_x = (-0.5, 0.5)
    command.ranges.lin_vel_y = (-0.6, 0.6)
    command.ranges.ang_vel_z = (-1.0, 1.0)
    command.ranges.heading = (-3.14, 3.14)
    command.viz.z_offset = 0.85

    # Domain randomisation (source domain_rand).
    cfg.events["foot_friction"].params["asset_cfg"].geom_names = _FOOT_GEOMS
    cfg.events["foot_friction"].params["ranges"] = (0.5, 1.25)
    cfg.events["base_com"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    cfg.events["base_com"].params["ranges"] = {
        0: (-0.03, 0.03),
        1: (-0.03, 0.03),
        2: (-0.03, 0.03),
    }
    cfg.events["push_robot"].params["interval_range_s"] = (10.0, 10.0)
    cfg.events["push_robot"].params["velocity_range"] = {
        "x": (-1.0, 1.0),
        "y": (-1.0, 1.0),
        "z": (-0.4, 0.4),
    }

    _configure_rewards(cfg)
    cfg.rewards["upright"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = (_ROOT_BODY,)

    _restructure_actor_obs(cfg)
    cfg.observations["critic"].terms.pop("height_scan", None)

    # Terminations: keep bad_orientation + time_out, add non-foot contact.
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.terminations["illegal_contact"] = TerminationTermCfg(
        func=mdp.illegal_contact,
        params={"sensor_name": other_sensor.name, "force_threshold": 10.0},
    )

    # Fixed command ranges: drop the mjlab velocity-stage curriculum (its later
    # stages go far beyond the TRON1 source command envelope).
    cfg.curriculum.pop("terrain_levels", None)
    cfg.curriculum.pop("command_vel", None)

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["actor"].enable_corruption = False
        cfg.events.pop("push_robot", None)
        cfg.events.pop("foot_friction", None)
        cfg.curriculum = {}

    return cfg


def pf_flat_env_cfg(*, play: bool = False):
    return make_tron1_pf_flat_env_cfg(play=play)


def pf_runner_cfg():
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
        experiment_name="tron1_pf_velocity",
        save_interval=100,
        num_steps_per_env=24,
        max_iterations=10_000,
    )
