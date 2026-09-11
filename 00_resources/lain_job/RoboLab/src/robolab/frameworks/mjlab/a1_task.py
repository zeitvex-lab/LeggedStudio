"""RoboLab-owned MJLab velocity task for the canonical Unitree A1 MJCF.

The task lives in the RoboLab adapter rather than inside the vendored MJLab
tree.  This keeps the robot binding, asset provenance, and cross-framework
semantic choices under RoboLab's control while still using MJLab's native
ManagerBased environment and RSL-RL runner.
"""

from __future__ import annotations

from pathlib import Path

import mujoco

from mjlab.actuator import BuiltinPositionActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg
from mjlab.tasks.registry import register_mjlab_task
from mjlab.tasks.velocity import mdp
from mjlab.tasks.velocity.config.go1.rl_cfg import unitree_go1_ppo_runner_cfg
from mjlab.tasks.velocity.rl import VelocityOnPolicyRunner
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg

from robolab.robots.unitree_a1.bindings.mjlab import (
    A1_DEFAULT_JOINT_POSITIONS,
    canonical_mjcf,
)
from robolab.robots.unitree_a1.spec import UNITREE_A1_JOINT_ORDER


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def get_a1_spec() -> mujoco.MjSpec:
    """Load the canonical A1 MJCF and normalize it for MJLab's entity API.

    The source XML contains motor actuators with joint-name aliases.  MJLab owns
    position control here, so the runtime copy gives the legacy actuators distinct
    names before adding its own position actuators.  The physical robot asset is
    not modified.
    """

    spec = mujoco.MjSpec.from_file(str(canonical_mjcf(_repository_root())))
    for actuator in spec.actuators:
        actuator.name = f"legacy_{actuator.name}"
    for sensor in spec.sensors:
        if sensor.name == "linear-velocity":
            sensor.name = "imu_lin_vel"
        elif sensor.name == "angular-velocity":
            sensor.name = "imu_ang_vel"
    return spec


def get_a1_robot_cfg() -> EntityCfg:
    """Return a fresh A1 entity configuration for one MJLab environment."""

    return EntityCfg(
        init_state=EntityCfg.InitialStateCfg(
            pos=(0.0, 0.0, 0.42),
            joint_pos=A1_DEFAULT_JOINT_POSITIONS,
            joint_vel={".*": 0.0},
        ),
        spec_fn=get_a1_spec,
        articulation=EntityArticulationInfoCfg(
            actuators=(
                BuiltinPositionActuatorCfg(
                    target_names_expr=(".*_joint",),
                    stiffness=20.0,
                    damping=0.5,
                    effort_limit=33.5,
                    armature=0.01,
                ),
            ),
            soft_joint_pos_limit_factor=0.9,
        ),
    )


def unitree_a1_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Build a flat-ground A1 velocity task using the shared velocity semantics."""

    cfg = make_velocity_env_cfg()
    cfg.scene.entities = {"robot": get_a1_robot_cfg()}
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.scene.sensors = ()
    cfg.sim.nconmax = None
    cfg.sim.njmax = 300
    cfg.viewer.body_name = "robot"
    cfg.viewer.distance = 1.5

    cfg.observations["actor"].terms.pop("base_lin_vel", None)
    for group in (cfg.observations["actor"], cfg.observations["critic"]):
        group.terms.pop("height_scan", None)
    cfg.observations["actor"].terms["base_ang_vel"].params["sensor_name"] = (
        "robot/imu_ang_vel"
    )
    cfg.observations["critic"].terms["base_lin_vel"].params["sensor_name"] = (
        "robot/imu_lin_vel"
    )
    cfg.observations["critic"].terms["base_ang_vel"].params["sensor_name"] = (
        "robot/imu_ang_vel"
    )
    for name in ("foot_height", "foot_air_time", "foot_contact", "foot_contact_forces"):
        cfg.observations["critic"].terms.pop(name, None)

    for name in (
        "air_time",
        "angular_momentum",
        "foot_clearance",
        "foot_swing_height",
        "foot_slip",
        "soft_landing",
    ):
        cfg.rewards.pop(name, None)
    cfg.rewards["upright"].params["asset_cfg"] = SceneEntityCfg(
        "robot", body_names=("robot",)
    )
    cfg.rewards["pose"].params["std_standing"] = {
        r".*_(hip|thigh)_joint.*": 0.05,
        r".*_calf_joint.*": 0.1,
    }
    cfg.rewards["pose"].params["std_walking"] = {
        r".*_(hip|thigh)_joint.*": 0.3,
        r".*_calf_joint.*": 0.6,
    }
    cfg.rewards["pose"].params["std_running"] = {
        r".*_(hip|thigh)_joint.*": 0.3,
        r".*_calf_joint.*": 0.6,
    }
    cfg.rewards["body_ang_vel"].params["asset_cfg"] = SceneEntityCfg(
        "robot", body_names=("robot",)
    )
    cfg.events.pop("foot_friction", None)
    cfg.events["base_com"].params["asset_cfg"].body_names = ("robot",)
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.curriculum = {}

    joint_pos_action = cfg.actions["joint_pos"]
    joint_pos_action.actuator_names = UNITREE_A1_JOINT_ORDER
    joint_pos_action.preserve_order = True
    joint_pos_action.scale = 0.25

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["actor"].enable_corruption = False
        cfg.events.pop("push_robot", None)
        cfg.commands["twist"].ranges.lin_vel_x = (-1.5, 2.0)
        cfg.commands["twist"].ranges.ang_vel_z = (-0.7, 0.7)

    return cfg


def unitree_a1_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    """Use MJLab's native PPO runner with an A1-specific experiment name."""

    cfg = unitree_go1_ppo_runner_cfg()
    cfg.experiment_name = "a1_velocity"
    return cfg


register_mjlab_task(
    task_id="RoboLab-Velocity-Flat-Unitree-A1",
    env_cfg=unitree_a1_flat_env_cfg(),
    play_env_cfg=unitree_a1_flat_env_cfg(play=True),
    rl_cfg=unitree_a1_ppo_runner_cfg(),
    runner_cls=VelocityOnPolicyRunner,
)


__all__ = [
    "get_a1_robot_cfg",
    "get_a1_spec",
    "unitree_a1_flat_env_cfg",
    "unitree_a1_ppo_runner_cfg",
]
