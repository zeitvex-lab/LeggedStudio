"""后空翻（backflip）特技的族级环境/运行器工厂。

来源：`go2_skills/backflip/config.py`。去机型化改动：

* 平地起点 `make_flat_env_cfg(<机型 velocity profile>)` → `flat_base_env_cfg(binding)`
  （与 jump / trot 同一先例：技能层几乎覆盖全部段，基座只剩 sim 上限/平地/viewer 余项）；
* 机机器人工厂 `jump_robot_cfg()` → `binding.robot_cfg()`（契约默认姿 + 契约 PD + MJCF 碰撞）；
* `JOINT_NAMES` → `binding.joint_order`（动作项序）；
* 关节相关下标（髋外展列、腿数、角色数、镜像腿对）→ 绑定与技能 profile 派生；
* 几何目标（飞行/站姿高度）与速度/接触阈值 → `BackflipProfile`；
* 初始事件表 `_trot_events` → 族级 `trot_events(cfg, binding)`；
* runner 基座 `make_ppo_runner_cfg` → 族级 runner（同样的超参由 profile 携带）。

**任务常量就地保留**（奖励权重表、观测噪声向量、状态机常量、命令范围全零）——
与 `variants.py` 的口径一致：Kit 禁的是"机型数据"，不禁止"任务常量"。
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
from . import rewards as backflip_rewards
from . import terminations as backflip_terminations
from .commands import BackflipCommandCfg
from .observations import BackflipActorHistory, BackflipCriticHistory
from .profile import BackflipProfile


def _derived_indices(binding: QuadrupedSkillBinding) -> dict[str, object]:
    """绑定派生的、"可序列化"的关节下标参数（喂给奖励核，不传绑定对象本身）。"""
    roles = len(binding.leg_pattern)
    abduction = binding.role_joint_indices("hip_abduction")
    if not abduction:
        raise ValueError(
            f"{binding.robot_id}: 关节序里找不到髋外展角色，后空翻的对称/髋惩罚无法派生"
        )
    hip_columns = tuple(abduction)
    return {
        "legs": binding.legs,
        "roles": roles,
        "abduction_column": hip_columns[0] % roles,
        "hip_columns": hip_columns,
    }


def make_env_cfg(
    binding: QuadrupedSkillBinding,
    profile: BackflipProfile,
    *,
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """Create the family-level backflip environment for one robot."""
    indices = _derived_indices(binding)
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
    cfg.commands = {
        "flip": BackflipCommandCfg(
            resampling_time_range=(profile.command_resample_s, profile.command_resample_s),
            debug_vis=True,
            entity_name="robot",
            heading_command=False,
            rel_standing_envs=0.0,
            rel_heading_envs=0.0,
            takeoff_frame_range=profile.takeoff_frame_range,
            ranges=UniformVelocityCommandCfg.Ranges(
                lin_vel_x=(0.0, 0.0),
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
                    func=BackflipActorHistory,
                    params={"command_name": "flip", "add_noise": True},
                    clip=(-100.0, 100.0),
                )
            },
            enable_corruption=True,
        ),
        "critic": ObservationGroupCfg(
            terms={
                "history": ObservationTermCfg(
                    func=BackflipCriticHistory,
                    params={"command_name": "flip"},
                    clip=(-100.0, 100.0),
                )
            },
            enable_corruption=False,
        ),
    }

    rewards = backflip_rewards
    shared = {"command_name": "flip", "sensor_name": FEET_SENSOR}
    cfg.rewards = {
        "before_setting": RewardTermCfg(func=rewards.BeforeSetting, weight=5.0, params=shared),
        "line_z": RewardTermCfg(func=rewards.line_z, weight=25.0, params=shared),
        "angle_y": RewardTermCfg(func=rewards.angle_y, weight=10.0, params=shared),
        "base_height_flight": RewardTermCfg(
            func=rewards.height_flight,
            weight=5.0,
            params={**shared, "target_height": profile.flight_height},
        ),
        "base_height_stance": RewardTermCfg(
            func=rewards.height_stance,
            weight=10.0,
            params={
                **shared,
                "target_height": profile.stance_height,
                "min_height": profile.stance_min_height,
            },
        ),
        "orientation": RewardTermCfg(func=rewards.orientation, weight=10.0, params=shared),
        "orientation_before": RewardTermCfg(
            func=rewards.orientation_before,
            weight=2.0,
            params={"command_name": "flip"},
        ),
        "dof_pos": RewardTermCfg(func=rewards.dof_pos, weight=-0.2),
        "line_vel_stance": RewardTermCfg(func=rewards.line_vel_stance, weight=-1.0),
        "ang_vel_xy": RewardTermCfg(func=rewards.ang_xy, weight=-0.2),
        "torques": RewardTermCfg(func=rewards.torques, weight=-0.0001),
        "dof_pos_limits": RewardTermCfg(func=rewards.dof_pos_limits, weight=-10.0),
        "dof_vel_limits": RewardTermCfg(
            func=rewards.dof_vel_limits,
            weight=-2.0,
            params={"max_abs_joint_vel": profile.max_abs_joint_vel},
        ),
        "dof_vel": RewardTermCfg(func=rewards.dof_vel, weight=-0.001),
        "collision": RewardTermCfg(
            func=rewards.collision, weight=-10.0, params={"sensor_name": PENALIZED_SENSOR}
        ),
        "action_rate": RewardTermCfg(func=rewards.action_rate, weight=-0.01),
        "feet_contact_forces": RewardTermCfg(
            func=rewards.feet_force,
            weight=-0.1,
            params={
                "sensor_name": FEET_SENSOR,
                "max_contact_force": profile.max_contact_force,
            },
        ),
        "land_pos": RewardTermCfg(func=rewards.land_pos, weight=1.0, params=shared),
        "symmetric_joints": RewardTermCfg(
            func=rewards.symmetric_joints,
            weight=-0.3,
            params={
                "legs": indices["legs"],
                "roles": indices["roles"],
                "abduction_column": indices["abduction_column"],
                # 镜像腿对**由绑定派生**（族约定：含 R 不含 L 的是右腿）——
                # 两台机型腿序不同（go2 = FL,FR,RL,RR ⇒ (1,3)；b2 = FR,FL,RR,RL ⇒ (0,2)），
                # 照搬一台的常量会把左右镜像做反。profile 显式给值时以 profile 为准。
                "mirror_leg_indices": (
                    profile.mirror_leg_indices
                    if profile.mirror_leg_indices is not None
                    else binding.right_leg_indices()
                ),
            },
        ),
        "default_hip_pos": RewardTermCfg(
            func=rewards.hip, weight=-0.5, params={"hip_columns": indices["hip_columns"]}
        ),
    }

    trot_events(cfg, binding)
    low, high = profile.friction_buckets
    cfg.events["friction"] = EventTermCfg(
        func=source_friction_buckets,
        mode="startup",
        params={
            "low": low,
            "high": high,
            "num_buckets": profile.num_friction_buckets,
            "entity_name": "robot",
        },
    )
    cfg.events["base_mass"].params["ranges"] = profile.base_mass_range
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

    cfg.terminations = {
        "time_out": TerminationTermCfg(func=env_mdp.time_out, time_out=True),
        "below_height": TerminationTermCfg(
            func=backflip_terminations.below_reset_height,
            params={"reset_height": profile.below_reset_height},
        ),
        "base_contact": TerminationTermCfg(
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


def make_runner_cfg(profile: BackflipProfile) -> RslRlOnPolicyRunnerCfg:
    """族级 runner（源配方：不归一化观测、不裁动作、小学习率 + 长预算）。

    与 jump 同一先例：基座走 `shared_rl.make_ppo_runner_cfg`（包内上游 PPO 基座
    的族级实现），逐档数值由 profile 携带。
    """
    cfg = shared_rl.make_ppo_runner_cfg(
        profile.experiment_name,
        max_iterations=profile.max_iterations,
        save_interval=profile.save_interval,
    )
    cfg.seed = profile.seed
    cfg.clip_actions = 100.0
    cfg.actor.obs_normalization = False
    cfg.critic.obs_normalization = False
    cfg.algorithm.learning_rate = profile.learning_rate
    return cfg
