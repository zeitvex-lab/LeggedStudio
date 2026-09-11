"""LimX TRON1 wheel-foot velocity environment configuration (package-local).

Flat-ground velocity task built from the package-local robot constants and
mjlab's shared velocity base, adapted from ``tron1-rl-isaaclab``
``tasks/locomotion/robots/limx_wheelfoot_env_cfg.py``:

- Actions: 6 leg position (scale 0.25) + 2 wheel velocity (scale 1.0).
- Policy observation (history_length=10): command(3) + projected_gravity(3)
  + base_ang_vel(3) + joint_pos of legs only (6, wheels excluded) +
  joint_vel(all 8) + last_action(8).
- Command ranges: lin_vel_x +-1.0, lin_vel_y +-0.5, ang_vel_z +-1 (heading).
- Rewards: velocity tracking + keep_balance + dof_pos_limits + action_rate,
  plus shared biped terms (feet_distance / no_fly / foot_landing_vel) over the
  wheel bodies.
- Terminations: non-wheel body contact, bad orientation (70 deg), timeout.
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs.mdp.actions import JointPositionActionCfg, JointVelocityActionCfg
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

from .robot_constants import (
    LEG_JOINT_EXPR,
    get_tron1_wf_robot_cfg,
)

_SITES = ("foot_L", "foot_R")
_WHEEL_GEOMS = ("wheel_L_collision", "wheel_R_collision")
_WHEEL_BODIES = ("wheel_L_Link", "wheel_R_Link")
_ROOT_BODY = "base_Link"

_HISTORY_LEN = 10  # source frame_stack / c_frame_stack


def _configure_foot_height_sensor(cfg: ManagerBasedRlEnvCfg) -> None:
    for sensor in cfg.scene.sensors or ():
        if sensor.name == "foot_height_scan":
            assert isinstance(sensor, TerrainHeightSensorCfg)
            sensor.frame = tuple(
                ObjRef(type="site", name=name, entity="robot") for name in _SITES
            )
            sensor.pattern = RingPatternCfg.single_ring(radius=0.05, num_samples=6)


def _contact_sensors() -> tuple[ContactSensorCfg, ContactSensorCfg]:
    feet = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(mode="geom", pattern=_WHEEL_GEOMS, entity="robot"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    other = ContactSensorCfg(
        name="nonfoot_ground_touch",
        primary=ContactMatch(
            mode="geom", pattern=".*_collision", entity="robot", exclude=_WHEEL_GEOMS
        ),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    return feet, other


def _restructure_actor_obs(cfg: ManagerBasedRlEnvCfg) -> None:
    """Actor group: cmd, gravity, ang_vel, joint_pos(legs only), joint_vel(all), action."""
    actor = cfg.observations["actor"]
    terms = dict(actor.terms)

    command = terms.pop("command")
    gravity = terms.pop("projected_gravity")
    ang_vel = terms.pop("base_ang_vel")
    ang_vel.scale = 0.25  # source obs_scales.ang_vel
    joint_pos = terms.pop("joint_pos")
    # Observed joint positions exclude the wheels (unbounded angle).
    joint_pos.params = dict(getattr(joint_pos, "params", {}) or {})
    joint_pos.params["asset_cfg"] = SceneEntityCfg("robot", joint_names=LEG_JOINT_EXPR)
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
    cfg.observations["critic"].history_length = _HISTORY_LEN


def _configure_rewards(cfg: ManagerBasedRlEnvCfg) -> None:
    cfg.rewards["track_linear_velocity"].weight = 1.0
    cfg.rewards["track_angular_velocity"].weight = 1.0
    cfg.rewards["upright"].weight = 1.0
    cfg.rewards["body_ang_vel"].weight = -0.05
    cfg.rewards["dof_pos_limits"].weight = -2.0
    cfg.rewards["action_rate_l2"].weight = -0.01
    cfg.rewards["air_time"].weight = 1.0
    cfg.rewards["foot_clearance"].weight = -0.5
    cfg.rewards["foot_clearance"].params["target_height"] = 0.05
    cfg.rewards["foot_swing_height"].weight = 0.0
    cfg.rewards["soft_landing"].weight = 0.0
    cfg.rewards["foot_slip"].params["asset_cfg"].site_names = _SITES
    cfg.rewards["foot_clearance"].params["asset_cfg"].site_names = _SITES

    cfg.rewards["feet_distance"] = RewardTermCfg(
        func=feet_distance_ours,
        weight=-1.0,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=_WHEEL_BODIES),
            "min_dist": 0.115,
            "weight": 100.0,
        },
    )
    cfg.rewards["no_fly"] = RewardTermCfg(
        func=no_fly,
        weight=0.4,
        params={
            "sensor_cfg": SceneEntityCfg("feet_ground_contact"),
            "asset_cfg": SceneEntityCfg("robot", body_names=_WHEEL_BODIES),
            "air_time_threshold": 0.3,
        },
    )
    cfg.rewards["foot_landing_vel"] = RewardTermCfg(
        func=foot_landing_vel,
        weight=-0.15,
        params={
            "sensor_cfg": SceneEntityCfg("feet_ground_contact"),
            "asset_cfg": SceneEntityCfg("robot", body_names=_WHEEL_BODIES),
            "height_threshold": 0.05,
        },
    )

    cfg.rewards["pose"].params["std_standing"] = {r".*_Joint": 0.05}
    moving = {
        r".*(?:abad|hip)_.*_Joint": 0.15,
        r".*knee_.*_Joint": 0.35,
        r".*wheel_.*_Joint": 0.3,
    }
    cfg.rewards["pose"].params["std_walking"] = moving
    cfg.rewards["pose"].params["std_running"] = moving


def make_tron1_wf_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground TRON1-WF velocity configuration."""
    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = 50
    cfg.sim.contact_sensor_maxmatch = 64
    cfg.sim.nconmax = None
    cfg.scene.entities = {"robot": get_tron1_wf_robot_cfg()}

    _configure_foot_height_sensor(cfg)
    feet_sensor, other_sensor = _contact_sensors()
    cfg.scene.sensors = (cfg.scene.sensors or ()) + (feet_sensor, other_sensor)

    assert cfg.scene.terrain is not None
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.scene.sensors = tuple(
        sensor for sensor in (cfg.scene.sensors or ()) if sensor.name != "terrain_scan"
    )

    # Actions: legs position (0.25) + wheels velocity (1.0).
    cfg.actions["joint_pos"] = JointPositionActionCfg(
        entity_name="robot",
        actuator_names=LEG_JOINT_EXPR,
        scale=0.25,
        use_default_offset=True,
    )
    cfg.actions["wheel_vel"] = JointVelocityActionCfg(
        entity_name="robot",
        actuator_names=(".*wheel.*",),
        scale=1.0,
        use_default_offset=False,
    )

    cfg.viewer.body_name = _ROOT_BODY
    cfg.viewer.distance = 2.0
    cfg.viewer.elevation = -10.0

    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.resampling_time_range = (10.0, 10.0)
    command.ranges.lin_vel_x = (-1.0, 1.0)
    command.ranges.lin_vel_y = (-0.5, 0.5)
    command.ranges.ang_vel_z = (-1.0, 1.0)
    command.ranges.heading = (-3.14, 3.14)
    command.viz.z_offset = 0.85

    cfg.events["foot_friction"].params["asset_cfg"].geom_names = _WHEEL_GEOMS
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

    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.terminations["illegal_contact"] = TerminationTermCfg(
        func=mdp.illegal_contact,
        params={"sensor_name": other_sensor.name, "force_threshold": 10.0},
    )

    cfg.curriculum.pop("terrain_levels", None)
    cfg.curriculum.pop("command_vel", None)

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["actor"].enable_corruption = False
        cfg.events.pop("push_robot", None)
        cfg.events.pop("foot_friction", None)
        cfg.curriculum = {}

    return cfg


def wf_flat_env_cfg(*, play: bool = False):
    return make_tron1_wf_flat_env_cfg(play=play)


def wf_runner_cfg():
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
        experiment_name="tron1_wf_velocity",
        save_interval=100,
        num_steps_per_env=24,
        max_iterations=10_000,
    )
