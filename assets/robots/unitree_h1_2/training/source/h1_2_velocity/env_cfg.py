"""Unitree H1_2 velocity environment configurations.

Humanoid flat/rough velocity tasks built from the package-local robot
constants and mjlab's shared velocity base.  Tuning follows the H1_2
contract documented in the package manifest (root body ``pelvis``, viewer
body ``torso_link``, per-foot height scan, self-collision penalty,
1.55 m command z-offset).
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

from .robot_constants import H1_2_ACTION_SCALE, get_h1_2_robot_cfg

_SITES = ("left_foot", "right_foot")
_FOOT_GEOMS = tuple(
    f"{side}_foot{i}_collision" for side in ("left", "right") for i in range(1, 8)
)
_ROOT_BODY = "pelvis"
_VIEWER_BODY = "torso_link"
_FOOT_CONTACT = r"^(left_ankle_roll_link|right_ankle_roll_link)$"


def _configure_height_sensors(cfg: ManagerBasedRlEnvCfg) -> None:
    for sensor in cfg.scene.sensors or ():
        if sensor.name == "terrain_scan":
            assert isinstance(sensor, RayCastSensorCfg)
            assert isinstance(sensor.frame, ObjRef)
            sensor.frame.name = _ROOT_BODY
        elif sensor.name == "foot_height_scan":
            assert isinstance(sensor, TerrainHeightSensorCfg)
            sensor.frame = tuple(
                ObjRef(type="site", name=name, entity="robot") for name in _SITES
            )
            sensor.pattern = RingPatternCfg.single_ring(radius=0.03, num_samples=6)


def _contact_sensors() -> tuple[ContactSensorCfg, ContactSensorCfg]:
    feet = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(
            mode="subtree", pattern=_FOOT_CONTACT, entity="robot"
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    other = ContactSensorCfg(
        name="self_collision",
        primary=ContactMatch(mode="subtree", pattern=_ROOT_BODY, entity="robot"),
        secondary=ContactMatch(mode="subtree", pattern=_ROOT_BODY, entity="robot"),
        fields=("found", "force"),
        reduce="none",
        num_slots=1,
        history_length=4,
    )
    return feet, other


def _configure_posture(cfg: ManagerBasedRlEnvCfg) -> None:
    cfg.rewards["pose"].params["std_standing"] = {".*": 0.05}
    moving = {
        r".*hip_pitch.*": 0.3,
        r".*hip_(roll|yaw).*": 0.15,
        r".*knee.*": 0.35,
        r".*ankle_pitch.*": 0.25,
        r".*ankle_roll.*": 0.1,
        r".*(waist|torso).*": 0.2,
        r".*shoulder.*": 0.15,
        r".*elbow.*": 0.15,
        r".*wrist.*": 0.3,
    }
    cfg.rewards["pose"].params["std_walking"] = moving
    cfg.rewards["pose"].params["std_running"] = moving


def make_h1_2_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Rough-terrain H1_2 velocity configuration."""
    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = 500
    cfg.sim.contact_sensor_maxmatch = 500
    cfg.sim.nconmax = 70
    cfg.scene.entities = {"robot": get_h1_2_robot_cfg()}

    _configure_height_sensors(cfg)
    feet_sensor, other_sensor = _contact_sensors()
    cfg.scene.sensors = (cfg.scene.sensors or ()) + (feet_sensor, other_sensor)

    if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
        cfg.scene.terrain.terrain_generator.curriculum = True

    action = cfg.actions["joint_pos"]
    assert isinstance(action, JointPositionActionCfg)
    action.scale = H1_2_ACTION_SCALE

    cfg.viewer.body_name = _VIEWER_BODY
    cfg.viewer.distance = 1.5
    cfg.viewer.elevation = -10.0
    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.viz.z_offset = 1.55

    cfg.events["foot_friction"].params["asset_cfg"].geom_names = _FOOT_GEOMS
    cfg.events["base_com"].params["asset_cfg"].body_names = (_VIEWER_BODY,)
    _configure_posture(cfg)
    cfg.rewards["upright"].params["asset_cfg"].body_names = (_VIEWER_BODY,)
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = (_VIEWER_BODY,)
    for name in ("foot_clearance", "foot_slip"):
        cfg.rewards[name].params["asset_cfg"].site_names = _SITES

    cfg.rewards["body_ang_vel"].weight = -0.05
    cfg.rewards["angular_momentum"].weight = -0.02
    cfg.rewards["self_collisions"] = RewardTermCfg(
        func=mdp.self_collision_cost,
        weight=-1.0,
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


def make_h1_2_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground H1_2 velocity configuration."""
    cfg = make_h1_2_rough_env_cfg(play=play)
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


def h1_2_flat_env_cfg(*, play: bool = False):
    return make_h1_2_flat_env_cfg(play=play)


def h1_2_rough_env_cfg(*, play: bool = False):
    return make_h1_2_rough_env_cfg(play=play)


def h1_2_runner_cfg():
    from mjlab.rl import RslRlOnPolicyRunnerCfg

    return RslRlOnPolicyRunnerCfg(
        actor={
            "class_name": "ActorCritic",
            "init_noise_std": 1.0,
            "activation": "elu",
            "hidden_dims": (512, 256, 128),
        },
        critic={
            "class_name": "ActorCritic",
            "init_noise_std": 1.0,
            "activation": "elu",
            "hidden_dims": (512, 256, 128),
        },
        algorithm={
            "class_name": "PPO",
            "value_loss_coef": 1.0,
            "use_clipped_value_loss": True,
            "clip_param": 0.2,
            "entropy_coef": 0.01,
            "num_learning_epochs": 5,
            "num_mini_batches": 4,
            "learning_rate": 1.0e-3,
            "schedule": "adaptive",
            "gamma": 0.99,
            "lam": 0.95,
            "max_grad_norm": 1.0,
        },
        policy={
            "reset_after_every_episode": False,
            "save_best_after": 100,
            "load_run": None,
            "resume": False,
        },
        runner={
            "max_iterations": 30_000,
            "save_interval": 100,
            "experiment_name": "h1_2_velocity",
        },
    )
