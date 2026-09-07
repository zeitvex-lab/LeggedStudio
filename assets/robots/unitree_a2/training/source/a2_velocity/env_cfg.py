"""Unitree A2 velocity environment configurations.

Quadruped flat/rough velocity tasks built from the package-local robot
constants and mjlab's shared velocity base.  The wiring mirrors the A2
tuning documented in the package manifest (root body ``base_link``, four
leg feet, 0.5 m command z-offset) so the trained policy matches the
deployed sim2sim contract.
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers import TerminationTermCfg
from mjlab.sensor import (
    ContactMatch,
    ContactSensorCfg,
    ObjRef,
    RayCastSensorCfg,
    RingPatternCfg,
    TerrainHeightSensorCfg,
)
from mjlab.tasks.velocity import mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg

from .robot_constants import A2_ACTION_SCALE, get_a2_robot_cfg

_QUAD_FEET = ("FR", "FL", "RR", "RL")
_QUAD_GEOMS = tuple(f"{name}_foot_collision" for name in _QUAD_FEET)
_ROOT_BODY = "base_link"


def _configure_height_sensors(cfg: ManagerBasedRlEnvCfg) -> None:
    for sensor in cfg.scene.sensors or ():
        if sensor.name == "terrain_scan":
            assert isinstance(sensor, RayCastSensorCfg)
            assert isinstance(sensor.frame, ObjRef)
            sensor.frame.name = _ROOT_BODY
        elif sensor.name == "foot_height_scan":
            assert isinstance(sensor, TerrainHeightSensorCfg)
            sensor.frame = tuple(
                ObjRef(type="site", name=name, entity="robot") for name in _QUAD_FEET
            )
            sensor.pattern = RingPatternCfg.single_ring(radius=0.04, num_samples=4)


def _contact_sensors() -> tuple[ContactSensorCfg, ContactSensorCfg]:
    feet = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(
            mode="geom", pattern=_QUAD_GEOMS, entity="robot"
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    other = ContactSensorCfg(
        name="nonfoot_ground_touch",
        primary=ContactMatch(mode="geom", pattern=".*_collision", entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    return feet, other


def _configure_posture(cfg: ManagerBasedRlEnvCfg) -> None:
    cfg.rewards["pose"].params["std_standing"] = {
        r".*_(hip|thigh)_joint.*": 0.05,
        r".*_calf_joint.*": 0.1,
    }
    moving = {
        r".*_(hip|thigh)_joint.*": 0.3,
        r".*_calf_joint.*": 0.6,
    }
    cfg.rewards["pose"].params["std_walking"] = moving
    cfg.rewards["pose"].params["std_running"] = moving


def make_a2_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Rough-terrain A2 velocity configuration."""
    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = 500
    cfg.sim.contact_sensor_maxmatch = 500
    cfg.sim.nconmax = None
    cfg.scene.entities = {"robot": get_a2_robot_cfg()}

    _configure_height_sensors(cfg)
    feet_sensor, other_sensor = _contact_sensors()
    cfg.scene.sensors = (cfg.scene.sensors or ()) + (feet_sensor, other_sensor)

    if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
        cfg.scene.terrain.terrain_generator.curriculum = True

    action = cfg.actions["joint_pos"]
    assert isinstance(action, JointPositionActionCfg)
    action.scale = A2_ACTION_SCALE

    cfg.viewer.body_name = _ROOT_BODY
    cfg.viewer.distance = 1.5
    cfg.viewer.elevation = -10.0
    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.viz.z_offset = 0.5

    cfg.events["foot_friction"].params["asset_cfg"].geom_names = _QUAD_GEOMS
    cfg.events["base_com"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    _configure_posture(cfg)
    cfg.rewards["upright"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    for name in ("foot_clearance", "foot_slip"):
        cfg.rewards[name].params["asset_cfg"].site_names = _QUAD_FEET

    cfg.terminations.pop("fell_over", None)
    cfg.terminations["illegal_contact"] = TerminationTermCfg(
        func=mdp.illegal_contact,
        params={"sensor_name": other_sensor.name, "force_threshold": 10.0},
    )

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["actor"].enable_corruption = False
        cfg.events.pop("push_robot", None)
        cfg.terminations.pop("out_of_terrain_bounds", None)
        cfg.curriculum = {}
        cfg.events["randomize_terrain"] = EventTermCfg(
            func=envs_mdp.randomize_terrain,
            mode="reset",
            params={},
        )
        if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
            terrain = cfg.scene.terrain.terrain_generator
            terrain.curriculum = False
            terrain.num_cols = 5
            terrain.num_rows = 5
            terrain.border_width = 10.0
    return cfg


def make_a2_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground A2 velocity configuration."""
    cfg = make_a2_rough_env_cfg(play=play)
    cfg.sim.njmax = 300
    cfg.sim.mujoco.ccd_iterations = 50
    cfg.sim.contact_sensor_maxmatch = 64
    cfg.sim.nconmax = None
    assert cfg.scene.terrain is not None
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.scene.sensors = tuple(
        sensor for sensor in (cfg.scene.sensors or ()) if sensor.name != "terrain_scan"
    )
    cfg.observations["actor"].terms.pop("height_scan", None)
    cfg.observations["critic"].terms.pop("height_scan", None)
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.curriculum.pop("terrain_levels", None)
    if play:
        command = cfg.commands["twist"]
        assert isinstance(command, UniformVelocityCommandCfg)
        command.ranges.lin_vel_x = (-1.0, 1.5)
        command.ranges.lin_vel_y = (-0.5, 0.5)
        command.ranges.ang_vel_z = (-0.7, 0.7)
    return cfg


def a2_flat_env_cfg(*, play: bool = False):
    return make_a2_flat_env_cfg(play=play)


def a2_rough_env_cfg(*, play: bool = False):
    return make_a2_rough_env_cfg(play=play)


def a2_runner_cfg():
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
        experiment_name="a2_velocity",
        save_interval=100,
        num_steps_per_env=24,
        max_iterations=10000,
    )
