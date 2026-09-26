"""站姿类技能（handstand / rear_stand）的族级环境工厂 —— 一份实现，两个奖励档。

来源：`go2_skills/{hand_stand,rear_stand}/config.py`。两个技能**共享同一套装配机制**
（同内核、同动作项、同终止、同 play 收尾），差异只在"奖励表选哪些项、命令口径、
事件微调、runner 对称开关、几何目标高" —— 按变体分支 + `StanceProfile` 数据表达。

去机型化：
* `JOINT_NAMES` → `binding.joint_order`（动作项序）；
* `handstand_robot_cfg()` / `rear_stand_robot_cfg()` → `binding.robot_cfg()`
  （两台在源里的出生高与初始姿**本来就相同**，都是 0.42 + 同一张关节表）；
* `body_names=("base_link",)` → `binding.root_body`；腿杆 body 正则 `(FL|FR|RL|RR)_.*`
  → 由 `binding.leg_ids` 派生；
* 传感器块 `replace_sensors` / `replace_rear_stand_sensors` 在源里是**同一个实现**
  （后者只多一行注释）→ 族级 `replace_sensors` 一份；
* `mdp.events.*` → 族级 `..mdp.events`（同名同实现）。

**任务常量就地保留**：两张奖励权重表、事件采样区间、命令范围（数值上逐项来自源配置）。
"""

from __future__ import annotations

from copy import deepcopy

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as env_mdp
from mjlab.envs.mdp import dr
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
from ..mdp.commands import HandstandVelocityCommandCfg, RearStandVelocityCommandCfg
from ..mdp.events import (
    add_root_velocity,
    overwrite_root_velocity,
    reset_joints_by_scale,
    sample_restitution_label,
)
from ..mdp.sensors import BASE_SENSOR, FEET_SENSOR, PENALIZED_SENSOR, replace_sensors
from ..mdp.terminations import base_contact
from . import observations as stance_observations
from . import rewards as stance_rewards
from .profile import StanceProfile

VARIANT_NAMES: tuple[str, ...] = ("handstand", "rear_stand")

#: 变体 → "哪一端"的用词（两档互为镜像：handstand 是**后**腿离地，rear_stand 是**前**腿）。
_ENDS = {
    "handstand": {"air": "rear", "contact": "front", "height_exp": "rear"},
    "rear_stand": {"air": "front", "contact": "rear", "height_exp": "front"},
}

#: 变体 → 观测帧类（两档各自一对，均在族级内核里）。
_OBSERVATION_FUNCS = {
    "handstand": (
        stance_observations.HandstandActorObservation,
        stance_observations.HandstandCriticObservation,
    ),
    "rear_stand": (
        stance_observations.RearStandActorObservation,
        stance_observations.RearStandCriticObservation,
    ),
}


def _command_cfg(profile: StanceProfile) -> UniformVelocityCommandCfg:
    cls = HandstandVelocityCommandCfg if profile.variant == "handstand" else RearStandVelocityCommandCfg
    return cls(
        resampling_time_range=(profile.command_resample_s, profile.command_resample_s),
        debug_vis=True,
        entity_name="robot",
        heading_command=profile.heading_command,
        rel_standing_envs=0.0,
        rel_heading_envs=profile.rel_heading_envs,
        ranges=UniformVelocityCommandCfg.Ranges(
            lin_vel_x=profile.lin_vel_x,
            lin_vel_y=(0.0, 0.0),
            ang_vel_z=profile.ang_vel_z,
            heading=profile.heading,
        ),
    )


def _rewards(profile: StanceProfile) -> dict[str, RewardTermCfg]:
    """两张奖励表（源 `_handstand_rewards` / `_rear_stand_rewards` 逐项照搬）。

    两档共用的项（跟踪 / 姿态 / 力矩 / 落地 / 默认姿 …）在这里只写一次，
    差异项按变体补 —— 这样"两档差在哪"在一处可读。
    """
    r = stance_rewards
    common = {
        "tracking_lin_vel": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_tracking_lin_vel"),
            weight=2.5,
            params={"command_name": "twist", "sigma": 0.25},
        ),
        "tracking_ang_vel": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_tracking_ang_vel"),
            weight=2.5,
            params={"command_name": "twist", "sigma": 0.25},
        ),
        "lin_vel_z": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_lin_vel_z"), weight=0.2
        ),
        "ang_vel_xy": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_ang_vel_xy"), weight=0.2
        ),
        "orientation": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_orientation"), weight=-1.0
        ),
        "torques": RewardTermCfg(func=r.absolute_torques, weight=-0.0002),
        "dof_acc": RewardTermCfg(func=r.DofAcceleration, weight=-2.5e-7),
        "base_height": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_base_height"),
            weight=1.5 if profile.variant == "rear_stand" else 1.0,
            params={"target_height": profile.base_height_target},
        ),
        "feet_on_air": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_{_ENDS[profile.variant]['air']}_feet_air"),
            weight=0.4,
            params={"sensor_name": FEET_SENSOR},
        ),
        "collision": RewardTermCfg(
            func=r.collision,
            weight=-2.0 if profile.variant == "rear_stand" else -1.0,
            params={"sensor_name": PENALIZED_SENSOR},
        ),
        "action_rate": RewardTermCfg(func=r.action_rate, weight=-0.05),
        "default_pos": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_default_pos"),
            weight=-0.1 if profile.variant == "rear_stand" else -0.05,
        ),
        "default_hip_pos": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_default_hip_pos"), weight=-0.1
        ),
        "feet_clearance": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_feet_clearance"),
            weight=0.4,
            params={
                "cycle_time": profile.cycle_time,
                "target_foot_height": profile.target_foot_height,
            },
        ),
        "ang_xz": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_roll"), weight=-0.5
        ),
        "contact": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_{_ENDS[profile.variant]['contact']}_contact"),
            weight=0.3,
            params={"sensor_name": FEET_SENSOR},
        ),
        "symmetric_joints": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_symmetric_joints"), weight=-0.1
        ),
        "feet_height_exp": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_{_ENDS[profile.variant]['height_exp']}_feet_height_exp"),
            weight=5.0,
        ),
        "default_pos_reward": RewardTermCfg(
            func=getattr(r, f"{profile.variant}_default_pos_reward"), weight=0.5
        ),
    }
    if profile.variant == "rear_stand":
        # 源 rear_stand 档的**变体名与原实现一致**（`rear_stand_orientation` 等）；
        # 这里把共享项的名字按源配置的公开名回填，保证 term 名校验与日志口径不变。
        common |= {
            "rear_stand_orientation": common.pop("orientation"),
            "rear_stand_feet_on_air": common.pop("feet_on_air"),
            "rear_stand_feet_height_exp": common.pop("feet_height_exp"),
        }
        common["orientation_symmetry"] = RewardTermCfg(
            func=r.rear_stand_orientation_symmetry, weight=-0.5
        )
        common["feet_height_symmetry"] = RewardTermCfg(
            func=r.rear_stand_feet_height_symmetry, weight=-0.2
        )
        common["dof_pos_limits"] = RewardTermCfg(
            func=r.rear_stand_dof_pos_limits, weight=-2.0
        )
        common["alive"] = RewardTermCfg(func=r.alive, weight=1.0)
        return common

    # handstand 档额外的三项 + 目标引导 + 反"摔死即最优"的兜底（见源配置里的注释）。
    common |= {
        "handstand_orientation": common.pop("orientation"),
        "handstand_feet_on_air": common.pop("feet_on_air"),
        "handstand_feet_height_exp": common.pop("feet_height_exp"),
        "tracking_lin_vel_zero": RewardTermCfg(
            func=r.handstand_tracking_lin_vel_zero,
            weight=-0.2,
            params={"command_name": "twist", "sigma": 0.25},
        ),
        "tracking_ang_vel_zero": RewardTermCfg(
            func=r.handstand_tracking_ang_vel_zero,
            weight=-0.2,
            params={"command_name": "twist"},
        ),
        "feet_air_time": RewardTermCfg(
            func=r.HandstandFeetAirTime, weight=2.0, params={"sensor_name": FEET_SENSOR}
        ),
        # PhysX 的接触瞬态让源配方在"终止项权重为 0"的情况下仍能发现可行盆地；
        # MuJoCo 里这个缺口会让"立刻摔倒"成为主导局部最优。这两项补上该缺口，
        # 其余 22 项源塑形项不变（源配置同注释）。
        "alive": RewardTermCfg(func=env_mdp.is_alive, weight=1.0),
        "termination": RewardTermCfg(func=r.terminal_cost, weight=-5.0),
        "from_zero_guidance": RewardTermCfg(
            func=r.handstand_from_zero_guidance,
            weight=1.0,
            params={
                "target_steps": 9_600,
                "fade_steps": 4_800,
                "initial_foot_height": 0.022,
                "target_foot_height": 0.67,
                "initial_base_height": 0.30,
                "target_base_height": profile.base_height_target,
            },
        ),
    }
    return common


def _events(cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding, profile: StanceProfile) -> None:
    """源 `_rear_stand_events` 的整表；handstand 档在其上覆盖四项（源实现同序）。"""
    joints = SceneEntityCfg("robot", joint_names=binding.joint_order, preserve_order=True)
    all_actuators = SceneEntityCfg("robot", actuator_names=[".*"])
    legs_pattern = f"({'|'.join(binding.leg_ids)})_.*"
    cfg.events = {
        "reset_base": EventTermCfg(
            func=env_mdp.reset_root_state_uniform,
            mode="reset",
            params={
                "pose_range": {},
                "velocity_range": {
                    "x": (-0.5, 0.5),
                    "y": (-0.5, 0.5),
                    "z": (-0.5, 0.5),
                    "roll": (-0.5, 0.5),
                    "pitch": (-0.5, 0.5),
                    "yaw": (-0.5, 0.5),
                },
            },
        ),
        "reset_robot_joints": EventTermCfg(
            func=reset_joints_by_scale,
            mode="reset",
            params={"scale_range": (0.5, 1.5), "entity_name": "robot"},
        ),
        "push_robot": EventTermCfg(
            func=overwrite_root_velocity,
            mode="interval",
            interval_range_s=(8.0, 8.0),
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
        "restitution_label": EventTermCfg(
            func=sample_restitution_label,
            mode="startup",
            params={"low": 0.0, "high": 0.3},
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
                "ranges": {0: (-0.05, 0.05), 1: (-0.05, 0.05), 2: (-0.05, 0.05)},
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
            params={"bias_range": (-0.035, 0.035), "asset_cfg": joints},
        ),
        "joint_friction": EventTermCfg(
            func=dr.joint_friction,
            mode="startup",
            params={
                "asset_cfg": joints,
                "ranges": profile.joint_friction_range,
                "operation": "abs",
                "shared_random": True,
            },
        ),
        "joint_damping": EventTermCfg(
            func=dr.joint_damping,
            mode="startup",
            params={
                "asset_cfg": joints,
                "ranges": profile.joint_damping_range,
                "operation": "abs",
                "shared_random": True,
            },
        ),
        "joint_armature": EventTermCfg(
            func=dr.joint_armature,
            mode="startup",
            params={
                "asset_cfg": joints,
                "ranges": profile.joint_armature_range,
                "operation": "abs",
                "shared_random": True,
            },
        ),
    }
    cfg.events["restitution_label"].params["attribute_name"] = profile.restitution_attribute
    if profile.push_max_vel_xy is not None:
        # handstand 档：源实现改成"加一个世界系速度冲量"，并放宽到 1.0/1.0。
        cfg.events["push_robot"].func = add_root_velocity
        cfg.events["push_robot"].params = {
            "max_push_vel_xy": profile.push_max_vel_xy,
            "max_push_ang_vel": profile.push_max_ang_vel,
        }


def make_env_cfg(
    binding: QuadrupedSkillBinding,
    profile: StanceProfile,
    *,
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """Create the family-level stance environment for one robot and one reward tier."""
    if profile.variant not in VARIANT_NAMES:
        raise ValueError(f"未知站姿变体 {profile.variant!r}（可用：{VARIANT_NAMES}）")
    actor_func, critic_func = _OBSERVATION_FUNCS[profile.variant]

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
            delay_min_lag=0,
            delay_max_lag=3,
            delay_update_period=4,
        )
    }
    cfg.commands = {"twist": _command_cfg(profile)}
    cfg.observations = {
        "actor": ObservationGroupCfg(
            terms={
                "frame": ObservationTermCfg(
                    func=actor_func,
                    params={"command_name": "twist", "add_noise": True},
                    clip=(-100.0, 100.0),
                )
            },
            enable_corruption=True,
        ),
        "critic": ObservationGroupCfg(
            terms={
                "frame": ObservationTermCfg(
                    func=critic_func,
                    params={"sensor_name": FEET_SENSOR},
                    clip=(-100.0, 100.0),
                )
            },
            enable_corruption=False,
        ),
    }
    cfg.rewards = _rewards(profile)
    _events(cfg, binding, profile)
    cfg.terminations = {
        "time_out": TerminationTermCfg(func=env_mdp.time_out, time_out=True),
        "base_contact": TerminationTermCfg(
            func=base_contact,
            params={"sensor_name": BASE_SENSOR, "force_threshold": 1.0},
        ),
    }
    cfg.curriculum = {}

    if play:
        cfg = deepcopy(cfg)
        cfg.scene.num_envs = 1
        cfg.observations["actor"].enable_corruption = False
        cfg.observations["actor"].terms["frame"].params["add_noise"] = False
        cfg.events.pop("push_robot", None)
    return cfg


def make_runner_cfg(profile: StanceProfile) -> RslRlOnPolicyRunnerCfg:
    """族级 runner；`mirror_loss=True` 的档按族级对称模块接线（源仅 rear_stand 档开）。"""
    symmetry_cfg = None
    if profile.mirror_loss:
        symmetry_cfg = {
            "data_augmentation_func": (
                "adapters.mjlab.kits.quadruped_kit.skills.stance.symmetry:rear_stand_symmetry"
            ),
            "use_data_augmentation": False,
            "use_mirror_loss": True,
            "mirror_loss_coeff": 1.0,
        }
    cfg = shared_rl.make_ppo_runner_cfg(
        profile.experiment_name,
        max_iterations=profile.max_iterations,
        save_interval=profile.save_interval,
        symmetry_cfg=symmetry_cfg,
    )
    cfg.seed = profile.seed
    cfg.clip_actions = 100.0
    cfg.actor.obs_normalization = False
    cfg.critic.obs_normalization = False
    cfg.algorithm.learning_rate = profile.learning_rate
    if profile.mirror_loss:
        cfg.algorithm.class_name = (
            "adapters.mjlab.kits.quadruped_kit.skills.mdp.symmetry:SourceSymmetricPPO"
        )
    return cfg
