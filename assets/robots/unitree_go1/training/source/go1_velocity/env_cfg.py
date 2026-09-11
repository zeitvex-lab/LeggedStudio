"""Unitree Go1 velocity environment configuration (package-local).

Flat-ground velocity task built from the package-local robot constants and
mjlab's shared velocity base, adapted from HIMLoco ``legged_gym/envs/go1``
(``Go1RoughCfg``) and walk-these-ways ``go1_gym``:

- Policy observation (history_length=5): command(3) + projected_gravity(3)
  + base_ang_vel(3) + joint_pos(12) + joint_vel(12) + last_action(12).
- Command ranges: lin_vel_x +-1.0, lin_vel_y +-1.0, ang_vel_z +-3.14 (heading).
- Rewards (source Go1RoughCfg.rewards.scales): tracking_lin 1.0,
  tracking_ang 0.5, ang_vel_xy -0.05, action_rate -0.01, foot_clearance -0.5.
- Terminations: non-foot body contact, bad orientation (70 deg), timeout.
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers import TerminationTermCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.tasks.velocity import mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg

from .robot_constants import GO1_ACTION_SCALE, get_go1_robot_cfg

_FOOT_GEOMS = ("FR_foot_collision", "FL_foot_collision", "RL_foot_collision", "RR_foot_collision")
_ROOT_BODY = "base_link"

_HISTORY_LEN = 5


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
    """Actor group: cmd, projected_gravity, ang_vel, joint_pos, joint_vel, action."""
    actor = cfg.observations["actor"]
    terms = dict(actor.terms)

    command = terms.pop("command")
    gravity = terms.pop("projected_gravity")
    ang_vel = terms.pop("base_ang_vel")
    ang_vel.scale = 0.25  # source obs_scales.ang_vel
    joint_pos = terms.pop("joint_pos")
    joint_vel = terms.pop("joint_vel")
    joint_vel.scale = 0.05  # source obs_scales.dof_vel
    actions = terms.pop("actions")
    for drop in ("base_lin_vel", "height_scan", "foot_height", "foot_air_time", "foot_contact"):
        terms.pop(drop, None)

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
    critic.history_length = _HISTORY_LEN
    for drop in ("height_scan", "foot_height", "foot_air_time", "foot_contact"):
        critic.terms.pop(drop, None)


def _configure_rewards(cfg: ManagerBasedRlEnvCfg) -> None:
    cfg.rewards["track_linear_velocity"].weight = 1.0  # tracking_lin_vel
    cfg.rewards["track_angular_velocity"].weight = 0.5  # tracking_ang_vel
    cfg.rewards["body_ang_vel"].weight = -0.05  # ang_vel_xy
    cfg.rewards["action_rate_l2"].weight = -0.01  # action_rate
    cfg.rewards["dof_pos_limits"].weight = -2.0
    cfg.rewards["air_time"].weight = 0.0  # feet_air_time (source 0.0)
    # go1's feet are the calf bodies (no dedicated foot sites), so every term
    # that depends on the foot height scan / foot sites is removed.
    for name in ("foot_clearance", "foot_swing_height", "soft_landing", "foot_slip"):
        cfg.rewards.pop(name, None)
    cfg.rewards["pose"].params["std_standing"] = {r".*_joint": 0.05}
    moving = {
        r".*_hip_joint": 0.15,
        r".*_thigh_joint": 0.3,
        r".*_calf_joint": 0.35,
    }
    cfg.rewards["pose"].params["std_walking"] = moving
    cfg.rewards["pose"].params["std_running"] = moving


def make_go1_env_cfg(play: bool = False, *, rough: bool = False) -> ManagerBasedRlEnvCfg:
    """Go1 velocity configuration (flat or rough).

    ``rough`` keeps mjlab's rough terrain generator, the root-body terrain scan
    sensor and the height-scan termination/observation (source HIMLoco
    ``Go1RoughCfg``, ``terrain.measure_heights = True``); ``flat`` drops them
    (source walk-these-ways / flat evaluation).
    """
    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = 500 if rough else 50
    cfg.sim.contact_sensor_maxmatch = 500 if rough else 64
    cfg.sim.nconmax = None
    if rough and cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
        cfg.scene.terrain.terrain_generator.curriculum = True
    cfg.scene.entities = {"robot": get_go1_robot_cfg()}

    feet_sensor, other_sensor = _contact_sensors()
    cfg.scene.sensors = (cfg.scene.sensors or ()) + (feet_sensor, other_sensor)

    assert cfg.scene.terrain is not None
    if not rough:
        cfg.scene.terrain.terrain_type = "plane"
        cfg.scene.terrain.terrain_generator = None
    # go1 has no dedicated foot sites, so the site-based foot height scan is
    # always dropped; the root-body terrain scan is kept for rough only.
    drop_sensors = ("foot_height_scan",) if rough else ("terrain_scan", "foot_height_scan")
    cfg.scene.sensors = tuple(
        sensor for sensor in (cfg.scene.sensors or ())
        if sensor.name not in drop_sensors
    )

    action = cfg.actions["joint_pos"]
    assert isinstance(action, JointPositionActionCfg)
    action.scale = GO1_ACTION_SCALE

    cfg.viewer.body_name = _ROOT_BODY
    cfg.viewer.distance = 2.0
    cfg.viewer.elevation = -10.0

    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.resampling_time_range = (10.0, 10.0)
    command.ranges.lin_vel_x = (-1.0, 1.0)
    command.ranges.lin_vel_y = (-1.0, 1.0)
    command.ranges.ang_vel_z = (-3.14, 3.14)
    command.ranges.heading = (-3.14, 3.14)
    command.viz.z_offset = 0.5

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
        "x": (-1.0, 1.0), "y": (-1.0, 1.0), "z": (-0.4, 0.4),
    }

    _configure_rewards(cfg)
    cfg.rewards["upright"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = (_ROOT_BODY,)

    _restructure_actor_obs(cfg)
    if not rough:
        cfg.observations["critic"].terms.pop("height_scan", None)

    if not rough:
        cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.terminations["illegal_contact"] = TerminationTermCfg(
        func=mdp.illegal_contact,
        params={"sensor_name": other_sensor.name, "force_threshold": 10.0},
    )

    if not rough:
        cfg.curriculum.pop("terrain_levels", None)
    cfg.curriculum.pop("command_vel", None)

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["actor"].enable_corruption = False
        cfg.events.pop("push_robot", None)
        cfg.events.pop("foot_friction", None)
        cfg.curriculum = {}

    return cfg


def make_go1_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground Go1 velocity configuration."""
    return make_go1_env_cfg(play, rough=False)


def make_go1_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Rough-terrain Go1 velocity configuration (source HIMLoco Go1RoughCfg)."""
    return make_go1_env_cfg(play, rough=True)


def go1_flat_env_cfg(*, play: bool = False):
    return make_go1_flat_env_cfg(play=play)


def go1_rough_env_cfg(*, play: bool = False):
    return make_go1_rough_env_cfg(play=play)


def go1_runner_cfg():
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
        experiment_name="go1_velocity",
        save_interval=100,
        num_steps_per_env=24,
        max_iterations=10_000,
    )
