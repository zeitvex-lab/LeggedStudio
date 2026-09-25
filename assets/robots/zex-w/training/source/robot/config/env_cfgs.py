"""ZEX-W 训练配置入口：flat / rough 是族级竞赛配方的薄委托，crawl 仍是本包自己的任务。

* `flat_env_cfg` / `rough_env_cfg`（2026-09-25 技能族级化）：装配真值在轮足族 Kit 的
  `adapters/mjlab/kits/wheel_leg_kit/skills/velocity/competition.py`（**竞赛配方**——
  延时低通动作 + 阈值命令 + 逐档奖励表，与 reference / 官方两份配方是三条不同的任务）。
  本模块只把绑定的机器人装配（`robot.velocity.binding.ZEXW`）与该档数据
  （`robot.velocity.profile` 的 `FLAT` / `ROUGH`）接上去，入口名与签名一字不动。
* `crawl_env_cfg`：**另一条任务**（趴姿越障：自己的实体配置 `get_robot_crawl_cfg`、
  自己的奖励表/终止口径、`rc_low_bar` 地形与 `terrain_levels_vel` 课程），不属于速度
  跟踪技能，故**不并入**竞赛配方，与 `_make_base_env_cfg` 一起原样保留在本模块。

`_make_base_env_cfg` 因此只服务 crawl（族级化之前它是三档共用的基座）。两处刻意不互相
引用：crawl 的数值与竞赛配方的数值各自独立，改一边不会牵动另一边。
"""

import math
import sys
from pathlib import Path

# 仓库根自举（见 kits/wheel_leg_kit 模块注释）：worker / schema-dump / 冒烟三种运行
# 环境都只把 ``training/source``（或包根）放进 sys.path；沿目录向上找 ``adapters/mjlab``
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp import dr as envs_dr
from mjlab.sim import SimulationCfg, MujocoCfg
from mjlab.managers.action_manager import ActionTermCfg
from mjlab.managers.command_manager import CommandTermCfg
from mjlab.managers.curriculum_manager import CurriculumTermCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.metrics_manager import MetricsTermCfg
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.scene import SceneCfg
from mjlab.sensor import (
    ContactMatch,
    ContactSensorCfg,
    ObjRef,
    RayCastSensorCfg,
    GridPatternCfg,
)
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.terrains import (
    TerrainEntityCfg,
    TerrainGeneratorCfg,
    BoxFlatTerrainCfg,
    BoxRandomGridTerrainCfg,
    HfPerlinNoiseTerrainCfg,
)
# 族级竞赛配方（技能实现 + 本机型的绑定与数据）：flat / rough 两个入口的装配真值。
# 2026-09-25 技能族级化：原先内联在本文件里的"基座 + flat + rough"三段已上移为
# `kits/wheel_leg_kit/skills/velocity/competition.py`（逐字对拍等价），本文件只留
# crawl 的基座与入口。
from adapters.mjlab.kits.wheel_leg_kit.skills import make_velocity_env_cfg  # noqa: E402
from ..terrains import RCLowBarTerrainCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise
from mjlab.viewer import ViewerConfig

from ..robot_cfg import get_robot_crawl_cfg
from ..mdp.lowpass_actions import JointPositionDelayedLowPassActionCfg, JointVelocityDelayedLowPassActionCfg
from ..mdp.only_positive_rewards import enable_only_positive_rewards
from ..mdp.rewards import (
    track_linear_velocity,
    track_angular_velocity,
    base_height_l2,
    safe_base_lin_vel,
    safe_foot_contact,
    safe_height_scan,
    wheel_roll_tracking,
    adaptive_leg_motion_penalty,
    contact_fraction_reward,
    stand_still,
    joint_deviation_l2,
    flat_orientation_l2,
    lin_vel_z_l2,
    crawl_height_reward,
)
from ..mdp.commands import UniformThresholdVelocityCommandCfg
from ..velocity import FLAT, ROUGH
from ..velocity.binding import ZEXW

# Constant Definitions
WHEEL_NAMES = ("fl", "fr", "rl", "rr")


def _make_base_env_cfg() -> ManagerBasedRlEnvCfg:
    """Create the base environment configuration containing sensors, commands, and default policies."""
    
    # ------------------
    # Sensors Definition
    # ------------------
    feet_ground_cfg = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(
            mode="body",
            pattern=tuple(f"{w}_wheel_Link" for w in WHEEL_NAMES),
            entity="robot",
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="none",
        num_slots=1,
        history_length=3,
        track_air_time=True,
    )

    base_ground_cfg = ContactSensorCfg(
        name="base_ground_contact",
        primary=ContactMatch(mode="body", pattern="base_link", entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found",),
        reduce="none",
        num_slots=1,
        history_length=4,
    )

    body_collision_cfg = ContactSensorCfg(
        name="body_collision",
        primary=ContactMatch(
            mode="body",
            pattern=(".*_hip_abduction_Link", ".*_hip_pitch_Link", ".*_knee_Link"),
            entity="robot",
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="none",
        num_slots=1,
        history_length=4,
    )

    terrain_scan = RayCastSensorCfg(
        name="height_scanner",
        frame=ObjRef(type="body", name="base_link", entity="robot"),
        pattern=GridPatternCfg(resolution=0.08, size=(1.6, 1.0)),
        ray_alignment="yaw",
        max_distance=5.0,
        exclude_parent_body=True,
        include_geom_groups=(0,),
        debug_vis=False,
    )

    # ------------------
    # Observations Setup
    # ------------------
    actor_terms = {
        "base_ang_vel": ObservationTermCfg(
            func=envs_mdp.base_ang_vel, scale=0.25,
            noise=Unoise(n_min=-0.2, n_max=0.2),
        ),
        "projected_gravity": ObservationTermCfg(
            func=velocity_mdp.projected_gravity,
            noise=Unoise(n_min=-0.05, n_max=0.05),
        ),
        "command": ObservationTermCfg(
            func=velocity_mdp.generated_commands,
            params={"command_name": "twist"},
        ),
        "joint_pos": ObservationTermCfg(
            func=envs_mdp.joint_pos_rel,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=(
                ".*_hip_abduction_joint", ".*_hip_pitch_joint", ".*_knee_joint",
            ))},
            noise=Unoise(n_min=-0.01, n_max=0.01),
        ),
        "joint_vel": ObservationTermCfg(
            func=envs_mdp.joint_vel_rel,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=(
                ".*_hip_abduction_joint", ".*_hip_pitch_joint", ".*_knee_joint",
            ))},
            scale=0.05, noise=Unoise(n_min=-1.5, n_max=1.5),
        ),
        "wheel_vel": ObservationTermCfg(
            func=envs_mdp.joint_vel_rel,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=(".*_wheel_joint",))},
            scale=0.05, noise=Unoise(n_min=-1.0, n_max=1.0),
        ),
        "actions": ObservationTermCfg(func=velocity_mdp.last_action),
    }

    critic_terms = {
        **actor_terms,
        "base_lin_vel": ObservationTermCfg(func=safe_base_lin_vel, scale=2.0),
        "foot_contact": ObservationTermCfg(
            func=safe_foot_contact, params={"sensor_name": "feet_ground_contact"},
        ),
        "height_scan": ObservationTermCfg(
            func=safe_height_scan, params={"sensor_name": "height_scanner"},
            clip=(-1.0, 1.0),
        ),
    }

    observations = {
        "actor": ObservationGroupCfg(
            terms=actor_terms, concatenate_terms=True,
            enable_corruption=True,
        ),
        "critic": ObservationGroupCfg(
            terms=critic_terms, concatenate_terms=True, enable_corruption=False,
        ),
    }

    # ------------------
    # Actions & Commands
    # ------------------
    actions: dict[str, ActionTermCfg] = {
        "leg_joint_pos": JointPositionDelayedLowPassActionCfg(
            entity_name="robot",
            actuator_names=(".*_hip_abduction_joint", ".*_hip_pitch_joint", ".*_knee_joint"),
            scale={".*_hip_abduction_joint": 0.125, "^(?!.*_hip_abduction_joint).*": 0.25}, use_default_offset=True,
            control_frequency=50.0, cut_off_frequency=5.0,
            min_delay=0, max_delay=2,
        ),
        "wheel_joint_vel": JointVelocityDelayedLowPassActionCfg(
            entity_name="robot", actuator_names=(".*_wheel_joint",),
            scale=5.0, offset=0.0, use_default_offset=False,
            control_frequency=50.0, cut_off_frequency=15.0,
            min_delay=0, max_delay=2,
        ),
    }

    commands: dict[str, CommandTermCfg] = {
        "twist": UniformThresholdVelocityCommandCfg(
            entity_name="robot", resampling_time_range=(10.0, 10.0),
            rel_standing_envs=0.15, rel_heading_envs=1.0, heading_command=True,
            heading_control_stiffness=0.6,
            rel_forward_envs=0.40,
            ranges=UniformThresholdVelocityCommandCfg.Ranges(
                lin_vel_x=(-1.0, 1.0), lin_vel_y=(-0.5, 0.5),
                ang_vel_z=(-1.0, 1.0), heading=(-math.pi, math.pi),
            ),
        )
    }

    # ------------------
    # Domain Randomization (Events)
    # ------------------
    events = {
        "reset_scene": EventTermCfg(func=envs_mdp.reset_scene_to_default, mode="reset"),
        "reset_base": EventTermCfg(
            func=envs_mdp.reset_root_state_uniform, mode="reset",
            params={
                "pose_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5), "yaw": (-math.pi, math.pi)},
                "velocity_range": {
                    "x": (-0.5, 0.5),
                    "y": (-0.5, 0.5),
                    "z": (-0.5, 0.5),
                    "roll": (-0.5, 0.5),
                    "pitch": (-0.5, 0.5),
                    "yaw": (-0.5, 0.5),
                },
                "asset_cfg": SceneEntityCfg("robot"),
            },
        ),
        "push_robot": EventTermCfg(
            func=envs_mdp.push_by_setting_velocity, mode="interval",
            interval_range_s=(10.0, 15.0),
            params={"velocity_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5)}, "asset_cfg": SceneEntityCfg("robot")},
        ),
        "base_com": EventTermCfg(
            func=envs_dr.body_com_offset, mode="startup",
            params={"asset_cfg": SceneEntityCfg("robot", body_names=("base_link",)),
                    "operation": "add", "ranges": {0: (-0.05, 0.05), 1: (-0.05, 0.05), 2: (-0.05, 0.05)}},
        ),
        "body_friction": EventTermCfg(
            func=envs_dr.geom_friction, mode="startup",
            params={"asset_cfg": SceneEntityCfg("robot", geom_names=(".*",)), "operation": "abs", "ranges": (0.3, 1.0)},
        ),
        "actuator_stiffness": EventTermCfg(
            func=envs_dr.joint_stiffness, mode="startup",
            params={"asset_cfg": SceneEntityCfg("robot"), "ranges": (0.9, 1.1), "operation": "scale", "distribution": "log_uniform"},
        ),
        "actuator_damping": EventTermCfg(
            func=envs_dr.joint_damping, mode="startup",
            params={"asset_cfg": SceneEntityCfg("robot"), "ranges": (0.9, 1.1), "operation": "scale", "distribution": "log_uniform"},
        ),
        "body_mass_base": EventTermCfg(
            func=envs_dr.body_mass, mode="startup",
            params={
                "asset_cfg": SceneEntityCfg("robot", body_names=("base_link",)),
                "operation": "add",
                "ranges": (-1.0, 3.0),
            },
        ),
    }

    # ------------------
    # Rewards Setup
    # ------------------
    rewards = {
        "track_lin_vel": RewardTermCfg(func=track_linear_velocity, weight=2.5, params={"std": 0.5, "command_name": "twist"}),
        "track_ang_vel": RewardTermCfg(func=track_angular_velocity, weight=2.5, params={"std": 0.5, "command_name": "twist"}),
        "upright": RewardTermCfg(func=velocity_mdp.upright, weight=1.0, params={"std": 0.5, "asset_cfg": SceneEntityCfg("robot", body_names=("base_link",))}),
        "base_height_l2": RewardTermCfg(func=base_height_l2, weight=-2.0, params={"target_height": 0.36}),
        "body_ang_vel": RewardTermCfg(func=velocity_mdp.body_angular_velocity_penalty, weight=-0.1, params={"asset_cfg": SceneEntityCfg("robot", body_names=("base_link",))}),
        "is_terminated": RewardTermCfg(func=envs_mdp.is_terminated, weight=-200.0),
        "joint_torques": RewardTermCfg(func=envs_mdp.joint_torques_l2, weight=-2.0e-4),
        "joint_acc": RewardTermCfg(func=envs_mdp.joint_acc_l2, weight=-2.5e-7),
        "action_rate": RewardTermCfg(func=envs_mdp.action_rate_l2, weight=-0.01),
        "joint_pos_limits": RewardTermCfg(func=envs_mdp.joint_pos_limits, weight=-10.0),
        "wheel_roll_tracking": RewardTermCfg(func=wheel_roll_tracking, weight=2.0, params={"command_name": "twist", "wheel_radius": 0.10, "wheel_track": 0.32, "std": 3.0, "asset_cfg": SceneEntityCfg("robot", joint_names=(".*_wheel_joint",))}),
        "wheel_contact_bonus": RewardTermCfg(func=contact_fraction_reward, weight=0.5, params={"sensor_name": "feet_ground_contact"}),
        "feet_air_time": RewardTermCfg(func=velocity_mdp.feet_air_time, weight=0.5, params={"sensor_name": "feet_ground_contact", "threshold_min": 0.1, "threshold_max": 0.5, "command_name": "twist", "command_threshold": 0.1}),
        "leg_motion_penalty": RewardTermCfg(func=adaptive_leg_motion_penalty, weight=-0.02, params={"command_name": "twist", "sensor_name": "feet_ground_contact", "command_threshold": 0.05, "tilt_relax_start": 0.08, "tilt_relax_end": 0.30, "contact_target": 0.85, "min_penalty_scale": 0.2, "asset_cfg": SceneEntityCfg("robot", joint_names=(".*_hip_abduction_joint", ".*_hip_pitch_joint", ".*_knee_joint"))}),
        "stand_still": RewardTermCfg(func=stand_still, weight=-0.2, params={"command_name": "twist", "command_threshold": 0.1}),
        "body_collision": RewardTermCfg(func=velocity_mdp.self_collision_cost, weight=-1.0, params={"sensor_name": "body_collision"}),
    }

    # ------------------
    # Terminations
    # ------------------
    terminations = {
        "time_out": TerminationTermCfg(func=envs_mdp.time_out, time_out=True),
        "bad_orientation": TerminationTermCfg(func=envs_mdp.bad_orientation, params={"limit_angle": 1.0}),
        "base_ground_contact": TerminationTermCfg(func=velocity_mdp.illegal_contact, params={"sensor_name": "base_ground_contact"}),
        "nan_detection": TerminationTermCfg(func=envs_mdp.nan_detection),
    }

    curriculum: dict[str, CurriculumTermCfg] = {}

    metrics = {"mean_leg_action_acc": MetricsTermCfg(func=velocity_mdp.mean_action_acc)}

    return ManagerBasedRlEnvCfg(
        scene=SceneCfg(
            num_envs=2048, env_spacing=2.5,
            terrain=TerrainEntityCfg(terrain_type="generator", terrain_generator=TerrainGeneratorCfg(
                size=(8.0, 8.0), border_width=20.0, num_rows=10, num_cols=20,
                sub_terrains={"flat": BoxFlatTerrainCfg(proportion=1.0)},
            )),
            sensors=(feet_ground_cfg, base_ground_cfg, body_collision_cfg, terrain_scan),
        ),
        commands=commands, actions=actions, observations=observations,
        rewards=rewards, terminations=terminations, events=events,
        metrics=metrics, curriculum=curriculum, decimation=4, episode_length_s=20.0,
        sim=SimulationCfg(mujoco=MujocoCfg(timestep=0.005, impratio=100, cone="elliptic")),
        viewer=ViewerConfig(body_name="base_link", distance=3.0, elevation=-20.0, azimuth=45.0),
    )


def flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """平地档（族级竞赛配方 `competition_flat`：只含平地的地块生成器 + 基座奖励表）。"""
    return make_velocity_env_cfg(ZEXW, FLAT, variant="competition_flat", play=play)


def rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """越障档（族级竞赛配方 `competition_rough`：族级竞赛课程 + 越障奖励表 + 命令课程）。

    原先 ~320 行的手写覆盖（地形/课程/命令/事件/奖励/指标）已逐字上移为族级配方的具名
    分支；本档的数值与结构现在分别住在 `robot.velocity.profile.ROUGH` 与
    `kits/wheel_leg_kit/skills/velocity/competition.py`。
    """
    return make_velocity_env_cfg(ZEXW, ROUGH, variant="competition_rough", play=play)


def crawl_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Crawling and ducking configuration for climbing obstacles under low clearing heights."""
    enable_only_positive_rewards()

    cfg = _make_base_env_cfg()
    cfg.scene.entities = {"robot": get_robot_crawl_cfg()}

    # ------------------
    # Terrain Definition
    # ------------------
    cfg.scene.terrain = TerrainEntityCfg(
        terrain_type="generator",
        terrain_generator=TerrainGeneratorCfg(
            size=(8.0, 8.0), border_width=20.0, num_rows=10, num_cols=20, curriculum=True,
            sub_terrains={
                "flat": BoxFlatTerrainCfg(proportion=0.25),
                "rc_low_bar": RCLowBarTerrainCfg(proportion=0.35, clearance_range=(0.24, 0.32)),
                "random_grid": BoxRandomGridTerrainCfg(proportion=0.20, grid_width=0.45, grid_height_range=(0.0, 0.05)),
                "perlin_noise": HfPerlinNoiseTerrainCfg(proportion=0.20, height_range=(0.0, 0.05), octaves=2, persistence=0.4, lacunarity=2.0, horizontal_scale=0.20, resolution=0.20, border_width=0.50, base_thickness_ratio=100.0),
            },
        ),
        max_init_terrain_level=0,
    )

    # Disable command vel curriculum and setup base command ranges
    cfg.curriculum.pop("command_vel", None)
    cfg.curriculum["terrain_levels"] = CurriculumTermCfg(func=velocity_mdp.terrain_levels_vel, params={"command_name": "twist"})

    cfg.commands["twist"].heading_command = False
    cfg.commands["twist"].rel_heading_envs = 0.0
    cfg.commands["twist"].ranges.heading = None
    cfg.commands["twist"].rel_standing_envs = 0.05  # 减少静止比例，匍匐任务需要持续运动。
    cfg.commands["twist"].rel_forward_envs = 0.40  # 40% 纯前向命令，用于低杆直穿地形。
    # ------------------
    # Events & Reset
    # ------------------
    cfg.events["joint_friction"] = EventTermCfg(func=envs_dr.joint_friction, mode="startup", params={"asset_cfg": SceneEntityCfg("robot"), "ranges": (0.7, 1.3), "operation": "scale"})
    cfg.events["reset_joints"] = EventTermCfg(func=envs_mdp.reset_joints_by_offset, mode="reset", params={"position_range": (0.0, 0.1), "velocity_range": (0.0, 0.0), "asset_cfg": SceneEntityCfg("robot", joint_names=(".*",))})
    
    cfg.events["reset_base"] = EventTermCfg(
        func=envs_mdp.reset_root_state_uniform, mode="reset",
        params={
            "pose_range": {"z": (0.00, 0.04), "yaw": (-math.pi, math.pi)},
            "velocity_range": {"x": (-0.1, 0.1), "y": (-0.05, 0.05), "yaw": (-0.1, 0.1)},
            "asset_cfg": SceneEntityCfg("robot"),
        },
    )
    cfg.events["push_robot"] = EventTermCfg(
        func=envs_mdp.push_by_setting_velocity, mode="interval",
        interval_range_s=(5.0, 10.0),
        params={"velocity_range": {"x": (-0.3, 0.3), "y": (-0.3, 0.3)}, "asset_cfg": SceneEntityCfg("robot")},
    )

    # ------------------
    # Rewards Integration
    # ------------------
    cfg.rewards["track_lin_vel"].weight = 3.0
    cfg.rewards["track_lin_vel"].params["std"] = 0.5
    cfg.rewards["track_ang_vel"].weight = 1.5
    cfg.rewards["track_ang_vel"].params["std"] = 0.5
    
    cfg.rewards["lin_vel_z"] = RewardTermCfg(func=lin_vel_z_l2, weight=-1.0)
    cfg.rewards["ang_vel_xy"] = RewardTermCfg(func=velocity_mdp.body_angular_velocity_penalty, weight=-0.05, params={"asset_cfg": SceneEntityCfg("robot", body_names=("base_link",))})
    
    cfg.rewards["upright"].weight = 1.0
    cfg.rewards["upright"].params["std"] = 0.5
    cfg.rewards["action_rate"].weight = -0.001
    cfg.rewards["joint_torques"].weight = -1e-4
    cfg.rewards["joint_acc"].weight = 0.0
    cfg.rewards["joint_pos_limits"].weight = -1.0
    cfg.rewards["leg_motion_penalty"].weight = -5.0
    cfg.rewards["is_terminated"].weight = -50.0

    # Under-crawling height reward: maximum bonus when body stays under 0.22m
    cfg.rewards.pop("base_height_l2", None)
    cfg.rewards["crawl_height_reward"] = RewardTermCfg(
        func=crawl_height_reward,
        weight=1.5,
        params={"target_height": 0.22, "std": 0.05}
    )

    cfg.rewards.pop("stand_still", None)
    
    cfg.rewards.pop("hip_deviation", None)
    cfg.rewards["leg_joint_deviation"] = RewardTermCfg(
        func=joint_deviation_l2,
        weight=-15.0,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=(".*_hip_abduction_joint", ".*_hip_pitch_joint", ".*_knee_joint"))},
    )
    
    # 🌟 强力引入轮子滚动跟踪奖励，引导机器人完全依靠轮子的正向滚动进行平地/低矮处的推进
    cfg.rewards["wheel_roll_tracking"] = RewardTermCfg(
        func=wheel_roll_tracking, 
        weight=4.0, 
        params={
            "command_name": "twist", 
            "wheel_radius": 0.10, 
            "wheel_track": 0.32, 
            "std": 3.0, 
            "asset_cfg": SceneEntityCfg("robot", joint_names=(".*_wheel_joint",))
        }
    )

    if "body_collision" in cfg.rewards:
        cfg.rewards["body_collision"].weight = -0.1

    cfg.rewards["flat_orientation"] = RewardTermCfg(func=flat_orientation_l2, weight=-1.0)

    for key in ("wheel_roll_tracking", "feet_air_time", "wheel_contact_bonus", "body_ang_vel"):
        cfg.rewards.pop(key, None)

    cfg.episode_length_s = 30.0
    cfg.sim = SimulationCfg(contact_sensor_maxmatch=128, mujoco=MujocoCfg(timestep=0.005, impratio=100, cone="elliptic", ccd_iterations=80))

    # Loosen orientation bad threshold to 80 degrees for steep crawling tilts
    cfg.terminations["bad_orientation"].params["limit_angle"] = math.radians(80.0)
    
    # Remove base ground contact termination to facilitate crawl under bars
    cfg.terminations.pop("base_ground_contact", None)

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["actor"].enable_corruption = False
        cfg.events.pop("push_robot", None)
        cfg.curriculum = {}
        if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
            cfg.scene.terrain.terrain_generator.curriculum = False
            cfg.scene.terrain.terrain_generator.num_cols = 5
            cfg.scene.terrain.terrain_generator.num_rows = 5
            cfg.scene.terrain.terrain_generator.border_width = 10.0

    return cfg
