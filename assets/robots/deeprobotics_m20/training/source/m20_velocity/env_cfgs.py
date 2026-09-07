"""Deeprobotics M20 velocity environment configurations.

Rewritten against the official DeepRoboticsLab training truth
(``logs/.../params/env.yaml`` in the source repository, BSD-3-Clause):

- 57-dim rl_sdk observation layout: ang_vel x0.25 (body), projected gravity,
  command, 16-dim joint_pos relative (wheel slots zeroed), 16-dim joint_vel
  x0.05, raw 16-dim action.
- 21-term reward table (tracking +2/+1, penalties per env.yaml, wheel
  torque/acc split from legs).
- Threshold velocity command: small linear commands snap to zero.
- Actions: 12 leg position (hipx 0.125, hipy/knee 0.25) + 4 wheel velocity
  (scale 5.0).

Known simplifications vs the source: symmetric actor/critic (the source adds
a critic-only 187-point height scan and base linear velocity), no gait-phase
GaitReward terms (absent from the verified training run env.yaml).
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp.actions import JointPositionActionCfg, JointVelocityActionCfg
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.utils.noise import UniformNoiseCfg as Unoise

from . import mdp
from .base import (
    M20_LEG_JOINT_NAMES,
    M20_WHEEL_JOINT_NAMES,
    get_m20_robot_cfg,
    m20_leg_joint_cfg,
    m20_wheel_joint_cfg,
    m20_wheel_ground_contact_cfg,
)
from .mdp.m20_rewards import (
    UniformThresholdVelocityCommandM20,
    ang_vel_xy_l2,
    base_height_l2,
    contact_forces,
    feet_contact_without_cmd,
    flat_orientation_l2,
    joint_mirror,
    joint_pos_penalty,
    joint_pos_rel_zero_wheel,
    joint_power,
    lin_vel_z_l2,
    stand_still_joint_deviation_l1,
    undesired_contacts,
    upward,
)
from .velocity_env_cfg import make_velocity_env_cfg
from .rl_cfg import (
  m20_ppo_runner_cfg,
  m20_rough_ppo_runner_cfg,
  m20_rough_finetune_ppo_runner_cfg,
)

_ALL_JOINTS = tuple(
    [f"{lr}_{seg}_joint" for lr in ("fl", "fr", "hl", "hr") for seg in ("hipx", "hipy", "knee")]
    + [f"{lr}_wheel_joint" for lr in ("fl", "fr", "hl", "hr")]
)

_ACTION_SCALES = {**{j: (0.125 if "hipx" in j else 0.25) for j in _ALL_JOINTS[:12]},
                  **{j: 5.0 for j in _ALL_JOINTS[12:]}}


def m20_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """M20 rough-terrain velocity configuration (official reward recipe)."""
    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = 500
    cfg.sim.contact_sensor_maxmatch = 500
    cfg.scene.entities = {"robot": get_m20_robot_cfg()}

    all_joint_cfg = SceneEntityCfg("robot", joint_names=list(_ALL_JOINTS), preserve_order=True)
    leg_joint_cfg = m20_leg_joint_cfg()
    wheel_joint_cfg = m20_wheel_joint_cfg()
    non_wheel_body_cfg = SceneEntityCfg("robot", body_names=[r"^(?!.*_wheel).*"])
    wheel_body_cfg = SceneEntityCfg("robot", body_names=[r".*_wheel"])

    ##
    # Actions: legs position + wheels velocity
    ##
    cfg.actions["joint_pos"] = JointPositionActionCfg(
        entity_name="robot",
        actuator_names=M20_LEG_JOINT_NAMES,
        preserve_order=True,
        scale=_ACTION_SCALES,
        use_default_offset=True,
    )
    cfg.actions["wheel_vel"] = JointVelocityActionCfg(
        entity_name="robot",
        actuator_names=M20_WHEEL_JOINT_NAMES,
        preserve_order=True,
        scale=5.0,
        offset=0.0,
        use_default_offset=False,
    )

    ##
    # Sensors
    ##
    wheel_ground_cfg = m20_wheel_ground_contact_cfg()
    wheel_contact_forces = ContactSensorCfg(
        name="wheel_contact_forces",
        primary=ContactMatch(mode="body", pattern=r".*_wheel", entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain", entity="robot"),
        fields=("force",),
        reduce="netforce",
        num_slots=1,
    )
    non_wheel_contact = ContactSensorCfg(
        name="non_wheel_contact",
        primary=ContactMatch(mode="body", pattern=r"^(?!.*_wheel).*", entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain", entity="robot"),
        fields=("force",),
        reduce="netforce",
        num_slots=1,
    )
    cfg.scene.sensors = (cfg.scene.sensors or ()) + (wheel_ground_cfg, wheel_contact_forces, non_wheel_contact)

    if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
        cfg.scene.terrain.terrain_generator.curriculum = True
        cfg.scene.terrain.max_init_terrain_level = 5

    ##
    # Commands: threshold-sampled SE(2) velocity
    ##
    twist_cmd = cfg.commands["twist"]
    assert isinstance(twist_cmd, UniformVelocityCommandCfg)
    twist_cmd.class_type = UniformThresholdVelocityCommandM20
    twist_cmd.heading_command = True
    twist_cmd.resampling_time_range = (10.0, 10.0)
    twist_cmd.ranges.lin_vel_x = (-2.0, 2.0)
    twist_cmd.ranges.lin_vel_y = (-1.0, 1.0)
    twist_cmd.ranges.ang_vel_z = (-1.0, 1.0)
    twist_cmd.ranges.heading = (-3.14, 3.14)

    ##
    # Observations: 57-dim rl_sdk layout
    ##
    for group_name in ("policy", "critic"):
        cfg.observations[group_name].terms = {
            "base_ang_vel": ObservationTermCfg(
                func=envs_mdp.base_ang_vel, noise=Unoise(n_min=-0.2, n_max=0.2) if group_name == "policy" else None
            ),
            "projected_gravity": ObservationTermCfg(
                func=envs_mdp.projected_gravity,
                noise=Unoise(n_min=-0.05, n_max=0.05) if group_name == "policy" else None,
            ),
            "command": ObservationTermCfg(func=envs_mdp.generated_commands, params={"command_name": "twist"}),
            "joint_pos_rel": ObservationTermCfg(
                func=mdp.joint_pos_rel_zero_wheel,
                params={"all_cfg": all_joint_cfg, "wheel_cfg": wheel_joint_cfg},
                noise=Unoise(n_min=-0.01, n_max=0.01) if group_name == "policy" else None,
            ),
            "joint_vel_rel": ObservationTermCfg(
                func=envs_mdp.joint_vel_rel,
                params={"asset_cfg": all_joint_cfg},
                noise=Unoise(n_min=-1.5, n_max=1.5) if group_name == "policy" else None,
            ),
            "actions": ObservationTermCfg(func=envs_mdp.last_action),
        }

    ##
    # Rewards: official env.yaml table
    ##
    cfg.rewards = {
        "lin_vel_z_l2": RewardTermCfg(func=lin_vel_z_l2, weight=-2.0),
        "ang_vel_xy_l2": RewardTermCfg(func=ang_vel_xy_l2, weight=-0.02),
        "flat_orientation_l2": RewardTermCfg(func=flat_orientation_l2, weight=-2.0),
        "base_height_l2": RewardTermCfg(
            func=base_height_l2, weight=-0.5, params={"target_height": 0.4}
        ),
        "joint_torques_l2": RewardTermCfg(
            func=envs_mdp.joint_torques_l2, weight=-2.5e-05, params={"asset_cfg": leg_joint_cfg}
        ),
        "joint_acc_l2": RewardTermCfg(
            func=envs_mdp.joint_acc_l2, weight=-2e-07, params={"asset_cfg": leg_joint_cfg}
        ),
        "joint_acc_wheel_l2": RewardTermCfg(
            func=envs_mdp.joint_acc_l2, weight=-1e-07, params={"asset_cfg": wheel_joint_cfg}
        ),
        "joint_pos_limits": RewardTermCfg(
            func=envs_mdp.joint_pos_limits, weight=-5.0, params={"asset_cfg": leg_joint_cfg}
        ),
        "joint_power": RewardTermCfg(
            func=joint_power, weight=-2e-05, params={"asset_cfg": leg_joint_cfg}
        ),
        "hipx_joint_pos_penalty": RewardTermCfg(
            func=joint_pos_penalty,
            weight=-0.4,
            params={
                "command_name": "twist",
                "asset_cfg": SceneEntityCfg(
                    "robot",
                    joint_names=["fl_hipx_joint", "fr_hipx_joint", "hl_hipx_joint", "hr_hipx_joint"],
                    preserve_order=True,
                ),
                "stand_still_scale": 5.0,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
            },
        ),
        "hipy_joint_pos_penalty": RewardTermCfg(
            func=joint_pos_penalty,
            weight=-0.1,
            params={
                "command_name": "twist",
                "asset_cfg": SceneEntityCfg(
                    "robot",
                    joint_names=["fl_hipy_joint", "fr_hipy_joint", "hl_hipy_joint", "hr_hipy_joint"],
                    preserve_order=True,
                ),
                "stand_still_scale": 5.0,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
            },
        ),
        "knee_joint_pos_penalty": RewardTermCfg(
            func=joint_pos_penalty,
            weight=-0.1,
            params={
                "command_name": "twist",
                "asset_cfg": SceneEntityCfg(
                    "robot",
                    joint_names=["fl_knee_joint", "fr_knee_joint", "hl_knee_joint", "hr_knee_joint"],
                    preserve_order=True,
                ),
                "stand_still_scale": 5.0,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
            },
        ),
        "joint_mirror": RewardTermCfg(
            func=joint_mirror,
            weight=-0.03,
            params={
                "asset_cfg": all_joint_cfg,
                "mirror_joints": [
                    ["fl_(hipx|hipy|knee).*", "hr_(hipx|hipy|knee).*"],
                    ["fr_(hipx|hipy|knee).*", "hl_(hipx|hipy|knee).*"],
                ],
            },
        ),
        "action_rate_l2": RewardTermCfg(func=envs_mdp.action_rate_l2, weight=-0.01),
        "undesired_contacts": RewardTermCfg(
            func=undesired_contacts,
            weight=-1.0,
            params={"sensor_cfg": non_wheel_body_cfg, "threshold": 1.0},
        ),
        "contact_forces": RewardTermCfg(
            func=contact_forces,
            weight=-0.00015,
            params={"sensor_cfg": wheel_body_cfg, "threshold": 100.0},
        ),
        "track_lin_vel_xy_exp": RewardTermCfg(
            func=velocity_mdp.track_linear_velocity,
            weight=2.0,
            params={"command_name": "twist", "std": 0.7071067811865476},
        ),
        "track_ang_vel_z_exp": RewardTermCfg(
            func=velocity_mdp.track_angular_velocity,
            weight=1.0,
            params={"command_name": "twist", "std": 0.7071067811865476},
        ),
        "feet_contact_without_cmd": RewardTermCfg(
            func=feet_contact_without_cmd,
            weight=0.1,
            params={"command_name": "twist", "sensor_cfg": wheel_body_cfg},
        ),
        "stand_still": RewardTermCfg(
            func=stand_still_joint_deviation_l1,
            weight=-2.0,
            params={"command_name": "twist", "asset_cfg": leg_joint_cfg},
        ),
        "upward": RewardTermCfg(func=upward, weight=0.08),
    }

    ##
    # Viewer / events
    ##
    cfg.viewer.body_name = "base_link"
    cfg.viewer.distance = 1.5
    cfg.viewer.elevation = -10.0

    cfg.events["base_com"].params["asset_cfg"].body_names = ("base_link",)

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["policy"].enable_corruption = False
        cfg.events.pop("push_robot", None)
        cfg.terminations.pop("out_of_terrain_bounds", None)
        cfg.curriculum = {}
        if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
            terrain = cfg.scene.terrain.terrain_generator
            terrain.curriculum = False
            terrain.num_cols = 5
            terrain.num_rows = 5
            terrain.border_width = 10.0
    return cfg


def m20_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """M20 flat-ground variant: plane terrain, no height scan / terrain curriculum."""
    cfg = m20_rough_env_cfg(play=play)
    cfg.sim.njmax = 300
    cfg.sim.mujoco.ccd_iterations = 50
    cfg.sim.contact_sensor_maxmatch = 64
    cfg.sim.nconmax = None
    assert cfg.scene.terrain is not None
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.scene.sensors = tuple(
        s for s in (cfg.scene.sensors or ()) if s.name != "terrain_scan"
    )
    for group in ("policy", "critic"):
        cfg.observations[group].terms.pop("height_scan", None)
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.curriculum.pop("terrain_levels", None)
    return cfg
