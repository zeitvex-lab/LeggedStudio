"""弹簧跳（spring jump）特技的族级环境/运行器工厂。

来源：`go2_skills/spring_jump/config.py`。去机型化改动与 backflip 同构：

* 平地起点 `make_flat_env_cfg(<机型 velocity profile>)` → `flat_base_env_cfg(binding)`；
* 机机器人工厂 `spring_jump_robot_cfg()` → `binding.robot_cfg()`；
* `JOINT_NAMES` → `binding.joint_order`；髋外展列与足端 site 名由绑定派生；
* 几何目标/阈值 → `SpringJumpProfile`；初始事件表 → 族级 `trot_events`。

**runner 的对称接线**也族级化：`symmetry_cfg.data_augmentation_func` 与
`algorithm.class_name` 指向族级 `skills/spring_jump/symmetry.py`（源指向包内路径）。
"""

from __future__ import annotations

from copy import deepcopy

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as env_mdp
from mjlab.managers import (
    EventTermCfg,
    ObservationGroupCfg,
    ObservationTermCfg,
    RewardTermCfg,
    SceneEntityCfg,
    TerminationTermCfg,
)
from mjlab.rl import RslRlOnPolicyRunnerCfg
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

from ..base_env_cfg import flat_base_env_cfg
from ..binding import QuadrupedSkillBinding
from ..mdp import rl as shared_rl
from ..mdp.actions import EpisodeDelayedJointPositionActionCfg
from ..mdp.events import source_friction_buckets
from ..mdp.sensors import BASE_SENSOR, FEET_SENSOR, PENALIZED_SENSOR, replace_sensors
from ..mdp.terminations import base_contact
from ..trot.config import trot_events
from . import rewards as spring_rewards
from .commands import SpringJumpCommandCfg
from .observations import SpringActorHistory, SpringCriticHistory
from .profile import SpringJumpProfile

#: 对称接线指向本技能**族级**模块（源指向包内 `spring_jump.mdp.symmetry`）。
_SYMMETRY_MODULE = "adapters.mjlab.kits.quadruped_kit.skills.spring_jump.symmetry"
SYMMETRY_FUNC = f"{_SYMMETRY_MODULE}:spring_jump_symmetry"
SYMMETRIC_PPO = f"{_SYMMETRY_MODULE}:SourceSymmetricPPO"


def _hip_columns(binding: QuadrupedSkillBinding) -> tuple[int, ...]:
    columns = binding.role_joint_indices("hip_abduction")
    if not columns:
        raise ValueError(f"{binding.robot_id}: 关节序里找不到髋外展角色，弹簧跳的髋惩罚无法派生")
    return tuple(columns)


def make_env_cfg(
    binding: QuadrupedSkillBinding,
    profile: SpringJumpProfile,
    *,
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """Create the family-level spring-jump environment for one robot."""
    hip_columns = _hip_columns(binding)
    foot_sites = binding.foot_sites()
    cfg = flat_base_env_cfg(binding)
    robot_cfg = binding.robot_cfg()
    # 出生高是**本技能的任务级参数**（源配方 0.39 m，与 jump 的 0.42 不同），
    # 契约里没有这一项 —— 由 profile 携带并在此覆盖。
    robot_cfg.init_state.pos = (0.0, 0.0, float(profile.init_base_height))
    cfg.scene.entities = {"robot": robot_cfg}
    cfg.scene.num_envs = profile.num_envs
    cfg.episode_length_s = profile.episode_length_s
    cfg.decimation = profile.decimation
    cfg.sim.mujoco.timestep = profile.physics_dt
    cfg.scale_rewards_by_dt = True
    cfg.metrics = {}
    cfg.recorders = {}
    replace_sensors(cfg, binding)

    cfg.actions = {
        "joint_pos": EpisodeDelayedJointPositionActionCfg(
            entity_name="robot",
            actuator_names=binding.joint_order,
            preserve_order=True,
            scale=profile.action_scale,
            use_default_offset=True,
            delay_min_lag=1,
            delay_max_lag=3,
        )
    }
    low, high = profile.target_lin_vel_x
    cfg.commands = {
        "jump_target": SpringJumpCommandCfg(
            resampling_time_range=(profile.command_resample_s, profile.command_resample_s),
            debug_vis=True,
            entity_name="robot",
            heading_command=False,
            rel_standing_envs=0.0,
            rel_heading_envs=0.0,
            takeoff_frame_range=profile.takeoff_frame_range,
            ranges=UniformVelocityCommandCfg.Ranges(
                lin_vel_x=(low, high),
                lin_vel_y=(0.0, 0.0),
                ang_vel_z=(0.0, 0.0),
                heading=None,
            ),
        )
    }
    cfg.observations = {
        "actor": ObservationGroupCfg(
            terms={
                "history": ObservationTermCfg(
                    func=SpringActorHistory,
                    params={"command_name": "jump_target", "add_noise": True},
                    clip=(-100.0, 100.0),
                )
            },
            enable_corruption=True,
        ),
        "critic": ObservationGroupCfg(
            terms={
                "history": ObservationTermCfg(
                    func=SpringCriticHistory,
                    params={"command_name": "jump_target", "sensor_name": FEET_SENSOR},
                    clip=(-100.0, 100.0),
                )
            },
            enable_corruption=False,
        ),
    }

    rewards = spring_rewards
    shared = {"command_name": "jump_target", "sensor_name": FEET_SENSOR}
    cfg.rewards = {
        "before_setting": RewardTermCfg(func=rewards.BeforeSetting, weight=5.0, params=shared),
        "line_z": RewardTermCfg(func=rewards.line_z, weight=16.0, params=shared),
        "flight": RewardTermCfg(func=rewards.flight, weight=2.0, params=shared),
        "base_height_flight": RewardTermCfg(
            func=rewards.base_height_flight,
            weight=3.0,
            params={**shared, "target_height": profile.flight_height},
        ),
        "base_height_stance": RewardTermCfg(
            func=rewards.base_height_stance,
            weight=-10.0,
            params={
                **shared,
                "target_height": profile.stance_height,
                "min_height": profile.stance_min_height,
            },
        ),
        "orientation": RewardTermCfg(func=rewards.orientation, weight=2.0),
        "dof_pos": RewardTermCfg(func=rewards.dof_pos, weight=-0.1),
        "dof_hip_pos": RewardTermCfg(
            func=rewards.hip_pos, weight=-1.0, params={"hip_columns": hip_columns}
        ),
        "ang_vel_xy": RewardTermCfg(func=rewards.ang_vel_xy, weight=-0.2),
        "torques": RewardTermCfg(func=rewards.torques, weight=-0.0001),
        "dof_pos_limits": RewardTermCfg(func=rewards.dof_pos_limits, weight=-10.0),
        "dof_vel_limits": RewardTermCfg(
            func=rewards.dof_vel_limits,
            weight=-1.0,
            params={"max_abs_joint_vel": profile.max_abs_joint_vel},
        ),
        "dof_vel": RewardTermCfg(func=rewards.dof_vel, weight=-0.001),
        "collision": RewardTermCfg(
            func=rewards.collision, weight=-50.0, params={"sensor_name": PENALIZED_SENSOR}
        ),
        "action_rate": RewardTermCfg(func=rewards.action_rate, weight=-0.01),
        "land_pos": RewardTermCfg(
            func=rewards.land_pos,
            weight=25.0,
            params={
                **shared,
                "min_flight_height": profile.min_flight_height,
                "max_landing_tilt": profile.max_landing_tilt,
            },
        ),
        "tracking_lin_vel": RewardTermCfg(
            func=rewards.tracking_lin_vel,
            weight=5.0,
            params={**shared, "gain": profile.tracking_lin_gain},
        ),
        "line_vel_stance": RewardTermCfg(
            func=rewards.line_vel_stance, weight=-3.0, params=shared
        ),
        "feet_contact_forces": RewardTermCfg(
            func=rewards.feet_contact_forces,
            weight=-0.1,
            params={
                "sensor_name": FEET_SENSOR,
                "max_contact_force": profile.max_contact_force,
            },
        ),
        "foot_clearance": RewardTermCfg(
            func=rewards.foot_clearance,
            weight=-3.0,
            params={
                **shared,
                "foot_sites": foot_sites,
                "target_height": profile.foot_clearance_target,
            },
        ),
    }

    trot_events(cfg, binding)
    # 源配方重置为**精确的默认**关节/根状态（与 trot 的 q 偏移不同）。
    cfg.events["reset_robot_joints"] = EventTermCfg(
        func=env_mdp.reset_joints_by_offset,
        mode="reset",
        params={
            "position_range": (0.0, 0.0),
            "velocity_range": (0.0, 0.0),
            "asset_cfg": SceneEntityCfg(
                "robot", joint_names=binding.joint_order, preserve_order=True
            ),
        },
    )
    bucket_low, bucket_high = profile.friction_buckets
    cfg.events["friction"] = EventTermCfg(
        func=source_friction_buckets,
        mode="startup",
        params={
            "low": bucket_low,
            "high": bucket_high,
            "num_buckets": profile.num_friction_buckets,
            "entity_name": "robot",
        },
    )
    cfg.events["base_mass"].params["ranges"] = profile.base_mass_range

    cfg.terminations = {
        "time_out": TerminationTermCfg(func=env_mdp.time_out, time_out=True),
        "base_contact": TerminationTermCfg(
            func=spring_rewards.below_reset_height,
            params={"reset_height": profile.below_reset_height},
        ),
        "base_collision": TerminationTermCfg(
            func=base_contact,
            params={
                "sensor_name": BASE_SENSOR,
                "force_threshold": profile.base_contact_force_threshold,
            },
        ),
    }
    cfg.curriculum = {}

    if play:
        cfg = deepcopy(cfg)
        cfg.scene.num_envs = 1
        cfg.observations["actor"].enable_corruption = False
        cfg.observations["actor"].terms["history"].params["add_noise"] = False
        cfg.events.pop("push_robot", None)
    return cfg


def make_runner_cfg(profile: SpringJumpProfile) -> RslRlOnPolicyRunnerCfg:
    """族级 runner：源配方 PPO 档 + **对称数据增强**（镜像函数与算法类均指向族级）。"""
    cfg = shared_rl.make_ppo_runner_cfg(
        profile.experiment_name,
        max_iterations=profile.max_iterations,
        save_interval=profile.save_interval,
        symmetry_cfg={
            "data_augmentation_func": SYMMETRY_FUNC,
            "use_data_augmentation": False,
            "use_mirror_loss": True,
            "mirror_loss_coeff": 1.0,
        },
    )
    cfg.seed = profile.seed
    cfg.clip_actions = 100.0
    cfg.actor.obs_normalization = False
    cfg.critic.obs_normalization = False
    cfg.algorithm.learning_rate = profile.learning_rate
    cfg.algorithm.class_name = SYMMETRIC_PPO
    return cfg
