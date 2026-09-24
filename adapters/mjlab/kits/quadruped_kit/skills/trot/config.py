"""Trot 技能的族级环境/运行器工厂。

来源：`go2_skills/trot/config.py`。除下列去机型化改动外逐字一致：

* 平地起点：源实现调该机型 velocity 的 `make_flat_env_cfg(profile)`，这里用
  `flat_base_env_cfg(binding)`（等价余项，见 `base_env_cfg.py`）；
* 机机器人工厂：源实现 `trot_robot_cfg()`，这里 `binding.robot_cfg()`（契约默认姿 + 契约 PD）；
* 关节名/序：源实现写死 `JOINT_NAMES`，这里 `binding.joint_order`；
* 事件表里写死的 body/leg 名（`base_link`、`(FL|FR|RL|RR)_.*`）由绑定派生；
* `experiment_name` / 学习率由 profile 携带。

`trot_events` 同时被 jump 复用（源实现 `from ..trot.config import _trot_events`）。
"""

from copy import deepcopy

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as env_mdp
from mjlab.envs.mdp import dr
from mjlab.managers import (
    CurriculumTermCfg,
    EventTermCfg,
    ObservationGroupCfg,
    ObservationTermCfg,
    RewardTermCfg,
    SceneEntityCfg,
    TerminationTermCfg,
)
from mjlab.rl import RslRlOnPolicyRunnerCfg
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

from ..binding import QuadrupedSkillBinding
from ..base_env_cfg import flat_base_env_cfg
from ..mdp import actions as shared_actions
from ..mdp import commands as shared_commands
from ..mdp import curriculums as shared_curriculums
from ..mdp import events as shared_events
from ..mdp import observations as shared_observations
from ..mdp import rl as shared_rl
from ..mdp import terminations as shared_terminations
from ..mdp.sensors import BASE_SENSOR, FEET_SENSOR, PENALIZED_SENSOR, replace_sensors
from . import rewards as trot_rewards
from .profile import TrotProfile


def _trot_observations(cfg: ManagerBasedRlEnvCfg, profile: TrotProfile) -> None:
    cfg.observations = {
        "actor": ObservationGroupCfg(
            terms={
                "history": ObservationTermCfg(
                    func=shared_observations.TrotActorHistory,
                    params={
                        "command_name": "twist",
                        "cycle_time": profile.cycle_time,
                        "add_noise": True,
                    },
                    clip=(-100.0, 100.0),
                )
            },
            enable_corruption=True,
        ),
        "critic": ObservationGroupCfg(
            terms={
                "history": ObservationTermCfg(
                    func=shared_observations.TrotCriticHistory,
                    params={
                        "command_name": "twist",
                        "sensor_name": FEET_SENSOR,
                        "cycle_time": profile.cycle_time,
                    },
                    clip=(-100.0, 100.0),
                )
            },
            enable_corruption=False,
        ),
    }


def _trot_rewards(cfg: ManagerBasedRlEnvCfg, profile: TrotProfile) -> None:
    gait = {
        "sensor_name": FEET_SENSOR,
        "command_name": "twist",
        "cycle_time": profile.cycle_time,
    }
    cfg.rewards = {
        "tracking_lin_vel": RewardTermCfg(
            func=trot_rewards.tracking_lin_vel,
            weight=2.0,
            params={**gait, "sigma": 0.25},
        ),
        "tracking_ang_vel": RewardTermCfg(
            func=trot_rewards.tracking_ang_vel,
            weight=2.0,
            params={**gait, "sigma": 0.25},
        ),
        "lin_vel_z": RewardTermCfg(func=trot_rewards.lin_vel_z, weight=-2.0),
        "ang_vel_xy": RewardTermCfg(func=trot_rewards.ang_vel_xy, weight=-0.05),
        "orientation": RewardTermCfg(func=trot_rewards.orientation, weight=-2.0),
        "torques": RewardTermCfg(func=trot_rewards.torques, weight=-0.0001),
        "dof_acc": RewardTermCfg(func=trot_rewards.DofAcceleration, weight=-2.5e-7),
        "collision": RewardTermCfg(
            func=trot_rewards.collision,
            weight=-1.0,
            params={"sensor_name": PENALIZED_SENSOR},
        ),
        "action_rate": RewardTermCfg(func=trot_rewards.action_rate, weight=-0.01),
        "stand_still": RewardTermCfg(
            func=trot_rewards.stand_still,
            weight=-1.0,
            params={"command_name": "twist"},
        ),
        "base_height": RewardTermCfg(
            func=trot_rewards.base_height,
            weight=-5.0,
            params={"target_height": profile.base_height_target},
        ),
        "trot": RewardTermCfg(func=trot_rewards.trot, weight=0.8, params=gait),
        "feet_clearance": RewardTermCfg(
            func=trot_rewards.feet_clearance,
            weight=0.1,
            params={
                "command_name": "twist",
                "cycle_time": profile.cycle_time,
                "target_foot_height": profile.target_foot_height,
            },
        ),
        "default_hip_pos": RewardTermCfg(func=trot_rewards.default_hip_pos, weight=-0.2),
        "default_pos": RewardTermCfg(func=trot_rewards.default_pos, weight=-0.1),
        "contact_without_command": RewardTermCfg(
            func=trot_rewards.contact_without_command,
            weight=1.0,
            params={"sensor_name": FEET_SENSOR, "command_name": "twist"},
        ),
    }


def trot_events(cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding) -> None:
    """trot / jump 共用的初始事件表（名字与参数与源实现一致）。"""
    all_actuators = SceneEntityCfg("robot", actuator_names=[".*"])
    legs_pattern = "(" + "|".join(binding.leg_ids) + ")_.*"
    cfg.events = {
        "reset_base": EventTermCfg(
            func=env_mdp.reset_root_state_uniform,
            mode="reset",
            params={"pose_range": {}, "velocity_range": {}},
        ),
        "reset_robot_joints": EventTermCfg(
            func=env_mdp.reset_joints_by_offset,
            mode="reset",
            params={
                "position_range": (-0.1, 0.1),
                "velocity_range": (0.0, 0.0),
                "asset_cfg": SceneEntityCfg(
                    "robot", joint_names=binding.joint_order, preserve_order=True
                ),
            },
        ),
        "push_robot": EventTermCfg(
            func=shared_events.overwrite_root_velocity,
            mode="interval",
            interval_range_s=(4.0, 4.0),
            is_global_time=True,
            params={"max_push_vel_xy": 0.4, "max_push_ang_vel": 0.6},
        ),
        "friction": EventTermCfg(
            func=dr.geom_friction,
            mode="startup",
            params={
                "asset_cfg": SceneEntityCfg("robot", geom_names=(r".*_collision",)),
                "ranges": (0.2, 1.2),
                "operation": "abs",
                "shared_random": True,
            },
        ),
        "base_mass": EventTermCfg(
            func=dr.body_mass,
            mode="startup",
            params={
                "asset_cfg": SceneEntityCfg("robot", body_names=(binding.root_body,)),
                "ranges": (-1.0, 2.0),
                "operation": "add",
            },
        ),
        "link_mass": EventTermCfg(
            func=dr.body_mass,
            mode="startup",
            params={
                "asset_cfg": SceneEntityCfg("robot", body_names=(legs_pattern,)),
                "ranges": (0.9, 1.1),
                "operation": "scale",
            },
        ),
        "base_com": EventTermCfg(
            func=dr.body_com_offset,
            mode="startup",
            params={
                "asset_cfg": SceneEntityCfg("robot", body_names=(binding.root_body,)),
                "ranges": {0: (-0.03, 0.03), 1: (-0.03, 0.03), 2: (-0.03, 0.03)},
                "operation": "add",
            },
        ),
        "pd_gains": EventTermCfg(
            func=dr.pd_gains,
            mode="startup",
            params={
                "asset_cfg": all_actuators,
                "kp_range": (0.9, 1.1),
                "kd_range": (0.9, 1.1),
                "operation": "scale",
            },
        ),
        "motor_zero_offset": EventTermCfg(
            func=dr.encoder_bias,
            mode="startup",
            params={"bias_range": (-0.035, 0.035)},
        ),
    }


def make_env_cfg(
    binding: QuadrupedSkillBinding, profile: TrotProfile, *, play: bool = False
) -> ManagerBasedRlEnvCfg:
    """Build the family Trot task from its source implementation."""
    cfg = flat_base_env_cfg(binding)
    cfg.scene.entities = {"robot": binding.robot_cfg()}
    cfg.scene.num_envs = profile.num_envs
    cfg.episode_length_s = profile.episode_length_s
    cfg.decimation = profile.decimation
    cfg.sim.mujoco.timestep = profile.physics_dt
    cfg.scale_rewards_by_dt = True
    cfg.metrics = {}
    cfg.recorders = {}
    replace_sensors(cfg, binding)
    cfg.actions = {
        "joint_pos": shared_actions.EpisodeDelayedJointPositionActionCfg(
            entity_name="robot",
            actuator_names=binding.joint_order,
            preserve_order=True,
            scale=profile.action_scale,
            use_default_offset=True,
            delay_min_lag=1,
            delay_max_lag=3,
        )
    }
    cfg.commands = {
        "twist": shared_commands.TrotVelocityCommandCfg(
            resampling_time_range=(5.0, 5.0),
            debug_vis=True,
            entity_name="robot",
            heading_command=False,
            rel_standing_envs=0.0,
            rel_heading_envs=0.0,
            ranges=UniformVelocityCommandCfg.Ranges(
                lin_vel_x=(-1.0, 1.0),
                lin_vel_y=(-1.0, 1.0),
                ang_vel_z=(-1.0, 1.0),
                heading=None,
            ),
        )
    }
    _trot_observations(cfg, profile)
    _trot_rewards(cfg, profile)
    trot_events(cfg, binding)
    cfg.terminations = {
        "time_out": TerminationTermCfg(func=env_mdp.time_out, time_out=True),
        "base_contact": TerminationTermCfg(
            func=shared_terminations.base_contact,
            params={"sensor_name": BASE_SENSOR, "force_threshold": 1.0},
        ),
    }
    cfg.curriculum = {
        "command_velocity": CurriculumTermCfg(
            func=shared_curriculums.source_trot_command_curriculum,
            params={"command_name": "twist", "max_curriculum": 2.0},
        )
    }
    if play:
        cfg = deepcopy(cfg)
        cfg.scene.num_envs = 1
        cfg.observations["actor"].enable_corruption = False
        cfg.observations["actor"].terms["history"].params["add_noise"] = False
        cfg.events.pop("push_robot")
        cfg.curriculum = {}
    return cfg


def make_runner_cfg(profile: TrotProfile) -> RslRlOnPolicyRunnerCfg:
    cfg = shared_rl.make_ppo_runner_cfg(
        profile.experiment_name,
        max_iterations=profile.max_iterations,
        save_interval=100,
    )
    cfg.seed = 1
    cfg.clip_actions = 100.0
    cfg.actor.obs_normalization = False
    cfg.critic.obs_normalization = False
    cfg.algorithm.learning_rate = profile.learning_rate
    return cfg
