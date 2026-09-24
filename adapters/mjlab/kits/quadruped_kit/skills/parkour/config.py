"""越障（parkour / PIE）技能的族级环境/运行器工厂。

来源：`local_tasks/robots/unitree/go2/tasks/parkour/config/go2/{env_cfgs,rl_cfg}.py`
（逐字上移，2026-09-25 四足族级化）。**去机型化的改动只有这几类**：

| 源实现里的机型事实 | 族级做法 |
|---|---|
| `get_go2_robot_cfg()` / PIE 大腿限位 | 调用方传入**配方就绪的实体配置** `robot_cfg`（技能层不重造物理；限位由 `binding.with_thigh_upper_limit` 从族角色派生） |
| `base_link`（根 body，出现在地形射线帧 / 姿态奖励 / 随机化事件 / 视角） | `binding.root_body`（MJCF 真值） |
| `_FOOT_NAMES` / `_FOOT_GEOMS`（写死的腿序与几何名） | `profile.foot_slot_order`（配方常量，**校验**为契约腿标记的排列）+ `binding.foot_geoms` |
| `.*_hip_joint`（写死的角色关节正则） | `binding.role_joint_pattern("hip_abduction")`（族角色派生，结果同形） |
| 相机 `name/pos/quat/fovy/width/height` 与深度观测项参数（字面量） | `registry/cameras.json` 的**档位声明**（`camera.py`，缺项 fail-closed） |
| 观测/奖励/终止/课程/命令实现 | `mdp/`（逐字上移）；PIE 模型与 PPO 扩展在 `rl/`（逐字上移） |
| 地形集 | `terrains.py`（逐字上移，配方常量） |

**注意**：动作项 `joint_pos` 的 `actuator_names=(".*",)`、命令采样区间、奖励权重等
都是**配方常量**（族内共享），不属于机型差异，故保持字面量 —— 迁移后逐字段等价是硬要求。
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from dataclasses import replace

from mjlab.entity import EntityCfg
from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp import dr
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers.action_manager import ActionTermCfg
from mjlab.managers.command_manager import CommandTermCfg
from mjlab.managers.curriculum_manager import CurriculumTermCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.rl import RslRlModelCfg, RslRlOnPolicyRunnerCfg
from mjlab.scene import SceneCfg
from mjlab.sensor import (
    CameraSensorCfg,
    ContactMatch,
    ContactSensorCfg,
    GridPatternCfg,
    ObjRef,
    RayCastSensorCfg,
)
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.terrains import TerrainEntityCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise
from mjlab.viewer import ViewerConfig

from ..binding import QuadrupedSkillBinding
from . import mdp
from .binding import (
    foot_geom_by_leg,
    foot_ray_frames,
    foot_site_names,
    foot_slot_order,
)
from .camera import resolve_depth_declaration
from .mdp.velocity_command import TerrainAwareVelocityCommandCfg
from .profile import ParkourProfile
from .rl import PIEPpoAlgorithmCfg
from .terrains import PIE_TERRAINS_CFG

#: PIE 配方在 rsl_rl 里按 `class_name` 解析的两处实现（族级模块路径 = 唯一真值）。
PIE_ACTOR_CLASS_NAME = (
    "adapters.mjlab.kits.quadruped_kit.skills.parkour.rl.pie_model:PIEActorModel"
)
PIE_PPO_CLASS_NAME = "adapters.mjlab.kits.quadruped_kit.skills.parkour.rl.ppo:PIEPPO"

#: 相机在场景里的传感器名之外的装配常量（域随机化的位姿/俯仰抖动幅度）。
_CAMERA_POS_JITTER = 0.01
_CAMERA_PITCH_RANGE_DEG = 1.0


def _proprio_terms(*, noisy: bool) -> dict[str, ObservationTermCfg]:
    """The 45-dimensional proprioceptive vector from the PIE paper."""
    return {
        "base_ang_vel": ObservationTermCfg(
            func=mdp.builtin_sensor,
            params={"sensor_name": "robot/imu_ang_vel"},
            noise=Unoise(n_min=-0.2, n_max=0.2) if noisy else None,
        ),
        "projected_gravity": ObservationTermCfg(
            func=mdp.projected_gravity,
            noise=Unoise(n_min=-0.05, n_max=0.05) if noisy else None,
        ),
        "command": ObservationTermCfg(
            func=mdp.generated_commands,
            params={"command_name": "twist"},
        ),
        "joint_pos": ObservationTermCfg(
            func=mdp.joint_pos_rel,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=(".*",))},
            noise=Unoise(n_min=-0.01, n_max=0.01) if noisy else None,
        ),
        "joint_vel": ObservationTermCfg(
            func=mdp.joint_vel_rel,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=(".*",))},
            noise=Unoise(n_min=-1.5, n_max=1.5) if noisy else None,
        ),
        "actions": ObservationTermCfg(func=mdp.last_action),
    }


def make_env_cfg(
    binding: QuadrupedSkillBinding,
    profile: ParkourProfile,
    robot_cfg: Callable[[], EntityCfg],
    *,
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """Create the family-level, stair-focused PIE environment for one member.

    `robot_cfg` 由机型侧提供（"配方就绪"的实体配置：契约/MJCF 的物理 + 配方级限位调整）——
    技能层不重造物理，只按配方装配场景/观测/奖励。
    """
    depth = resolve_depth_declaration(profile, robot_id=binding.robot_id)
    foot_order = foot_slot_order(binding, profile)
    foot_geoms = tuple(foot_geom_by_leg(binding)[leg] for leg in foot_order)
    # 配方就绪的 spec 真值（机型侧给）：足端帧（site 优先、几何回退）与足端 site 名都从它读。
    spec = robot_cfg().spec_fn()
    foot_sites = foot_site_names(binding, profile, spec)

    terrain_scan = RayCastSensorCfg(
        name="terrain_scan",
        frame=ObjRef(type="body", name=binding.root_body, entity="robot"),
        ray_alignment="yaw",
        # Inclusive sampling gives 18 x 11 = 198 privileged height samples.
        pattern=GridPatternCfg(size=(1.7, 1.0), resolution=0.1),
        max_distance=5.0,
        exclude_parent_body=True,
        include_geom_groups=(0, 1, 2),
        debug_vis=False,
    )

    foot_rays = tuple(
        RayCastSensorCfg(
            name=sensor_name,
            frame=frame,
            ray_alignment="world",
            pattern=GridPatternCfg(size=(0.02, 0.02), resolution=0.02),
            max_distance=0.6,
            exclude_parent_body=True,
            include_geom_groups=(0, 1, 2),
            debug_vis=False,
        )
        for sensor_name, frame in foot_ray_frames(binding, profile, spec)
    )
    foot_ray_names = tuple(sensor.name for sensor in foot_rays)

    feet_ground = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(mode="geom", pattern=foot_geoms, entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
        history_length=4,
    )
    nonfoot_ground = ContactSensorCfg(
        name="nonfoot_ground_touch",
        primary=ContactMatch(
            mode="geom",
            entity="robot",
            pattern=r".*_collision\d*$",
            exclude=foot_geoms,
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="none",
        num_slots=1,
        history_length=4,
    )

    # MuJoCo cameras look along local -Z with local +Y as image-up.  The
    # declaration carries the optical axis transform (forward and pitched
    # down) plus the resolution and the *horizontal* field of view; MuJoCo
    # takes a vertical FOV, so convert through the declared aspect ratio and
    # let the depth observation apply the declared column crop.
    depth_camera = CameraSensorCfg(
        name=depth.sensor_name,
        parent_body=depth.parent_body,
        pos=depth.pos,
        quat=depth.quat,
        fovy=depth.vertical_fov_deg,
        width=depth.width,
        height=depth.height,
        data_types=("depth",),
        enabled_geom_groups=(0, 1, 2),
        use_shadows=False,
        use_textures=False,
    )

    noisy_proprio = _proprio_terms(noisy=True)
    clean_proprio = _proprio_terms(noisy=False)
    observations = {
        "actor": ObservationGroupCfg(
            terms=noisy_proprio,
            concatenate_terms=True,
            enable_corruption=not play,
            history_length=1,
        ),
        "proprio_history": ObservationGroupCfg(
            terms=copy.deepcopy(noisy_proprio),
            concatenate_terms=True,
            enable_corruption=not play,
            history_length=10,
            flatten_history_dim=True,
        ),
        "camera": ObservationGroupCfg(
            terms={
                depth.sensor_name: ObservationTermCfg(
                    func=mdp.DepthHistory,
                    params=depth.observation_params(),
                )
            },
            concatenate_terms=True,
            enable_corruption=False,
            history_length=None,
            flatten_history_dim=True,
        ),
        "critic": ObservationGroupCfg(
            terms={
                **copy.deepcopy(clean_proprio),
                "base_lin_vel": ObservationTermCfg(
                    func=mdp.builtin_sensor,
                    params={"sensor_name": "robot/imu_lin_vel"},
                ),
                "height_scan": ObservationTermCfg(
                    func=envs_mdp.height_scan,
                    params={"sensor_name": terrain_scan.name},
                    scale=1.0 / terrain_scan.max_distance,
                ),
            },
            concatenate_terms=True,
            enable_corruption=False,
            history_length=1,
        ),
        "velocity_target": ObservationGroupCfg(
            terms={
                "base_lin_vel": ObservationTermCfg(
                    func=mdp.builtin_sensor,
                    params={"sensor_name": "robot/imu_lin_vel"},
                )
            },
            enable_corruption=False,
            history_length=1,
        ),
        "height_target": ObservationGroupCfg(
            terms={
                "height_scan": ObservationTermCfg(
                    func=envs_mdp.height_scan,
                    params={"sensor_name": terrain_scan.name},
                    scale=1.0 / terrain_scan.max_distance,
                )
            },
            enable_corruption=False,
            history_length=1,
        ),
        "foot_clearance_target": ObservationGroupCfg(
            terms={
                "foot_clearance": ObservationTermCfg(
                    func=mdp.foot_clearance,
                    params={"sensor_names": foot_ray_names, "max_clearance": 0.6},
                    scale=1.0 / 0.6,
                )
            },
            enable_corruption=False,
            history_length=1,
        ),
        # PiePPO replaces this current clean vector with o_(t+1) before storage.
        "successor_target": ObservationGroupCfg(
            terms=copy.deepcopy(clean_proprio),
            enable_corruption=False,
            history_length=1,
        ),
    }

    actions: dict[str, ActionTermCfg] = {
        "joint_pos": JointPositionActionCfg(
            entity_name="robot",
            actuator_names=(".*",),
            scale=0.25,
            use_default_offset=True,
        )
    }
    commands: dict[str, CommandTermCfg] = {
        "twist": TerrainAwareVelocityCommandCfg(
            entity_name="robot",
            resampling_time_range=(10.0, 10.0),
            rel_standing_envs=0.0,
            heading_command=False,
            debug_vis=True,
            flat_yaw_probabilities=(0.40, 0.30, 0.30),
            obstacle_yaw_probabilities=(0.80, 0.20, 0.00),
            obstacle_lin_vel_x=(0.20, 1.50),
            gentle_ang_vel_z=(-0.30, 0.30),
            ranges=TerrainAwareVelocityCommandCfg.Ranges(
                lin_vel_x=(0.0, 1.5),
                lin_vel_y=(0.0, 0.0),
                ang_vel_z=(-1.2, 1.2),
                heading=None,
            ),
        )
    }

    events = {
        "reset_base": EventTermCfg(
            func=mdp.reset_root_state_uniform,
            mode="reset",
            params={
                "pose_range": {
                    "x": (0.0, 0.0),
                    "y": (0.0, 0.0),
                    "z": (0.0, 0.0),
                    "yaw": (0.0, 0.0),
                },
                "velocity_range": {},
            },
        ),
        "reset_robot_joints": EventTermCfg(
            func=mdp.reset_joints_by_offset,
            mode="reset",
            params={
                "position_range": (-0.15, 0.15),
                "velocity_range": (-0.1, 0.1),
                "asset_cfg": SceneEntityCfg("robot", joint_names=(".*",)),
            },
        ),
        "push_robot": EventTermCfg(
            func=mdp.push_by_setting_velocity,
            mode="interval",
            interval_range_s=(6.0, 8.0),
            params={
                "velocity_range": {
                    "x": (-0.4, 0.4),
                    "y": (-0.4, 0.4),
                    "z": (-0.25, 0.25),
                    "roll": (-0.3, 0.3),
                    "pitch": (-0.3, 0.3),
                    "yaw": (-0.4, 0.4),
                }
            },
        ),
        "foot_friction": EventTermCfg(
            mode="startup",
            func=dr.geom_friction,
            params={
                "asset_cfg": SceneEntityCfg("robot", geom_names=foot_geoms),
                "operation": "abs",
                "ranges": (0.2, 1.2),
                "shared_random": True,
            },
        ),
        "encoder_bias": EventTermCfg(
            mode="startup",
            func=dr.encoder_bias,
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "bias_range": (-0.015, 0.015),
            },
        ),
        "base_com": EventTermCfg(
            mode="startup",
            func=dr.body_com_offset,
            params={
                "asset_cfg": SceneEntityCfg("robot", body_names=(binding.root_body,)),
                "operation": "add",
                "ranges": {0: (-0.05, 0.05), 1: (-0.05, 0.05), 2: (-0.05, 0.05)},
            },
        ),
        "base_payload": EventTermCfg(
            mode="startup",
            func=dr.body_mass,
            params={
                # PIE treats this as a point payload attached at the trunk COM.
                "asset_cfg": SceneEntityCfg("robot", body_names=(binding.root_body,)),
                "operation": "add",
                "ranges": (-1.0, 2.0),
            },
        ),
        "pd_gains": EventTermCfg(
            mode="startup",
            func=dr.pd_gains,
            params={
                # Leave actuator ids as slice(None) so grouped actuators are
                # randomized as actuator objects rather than as control ids.
                "asset_cfg": SceneEntityCfg("robot"),
                "kp_range": (0.9, 1.1),
                "kd_range": (0.9, 1.1),
                "operation": "scale",
            },
        ),
        "motor_strength": EventTermCfg(
            mode="startup",
            func=dr.effort_limits,
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "effort_limit_range": (0.9, 1.1),
                "operation": "scale",
            },
        ),
        "camera_position": EventTermCfg(
            mode="startup",
            func=dr.cam_pos,
            params={
                "asset_cfg": SceneEntityCfg("robot", camera_names=(depth_camera.name,)),
                "operation": "add",
                "ranges": {
                    0: (-_CAMERA_POS_JITTER, _CAMERA_POS_JITTER),
                    1: (-_CAMERA_POS_JITTER, _CAMERA_POS_JITTER),
                    2: (-_CAMERA_POS_JITTER, _CAMERA_POS_JITTER),
                },
            },
        ),
        "camera_pitch": EventTermCfg(
            mode="startup",
            func=dr.cam_quat,
            params={
                "asset_cfg": SceneEntityCfg("robot", camera_names=(depth_camera.name,)),
                "pitch_range": (
                    -math.radians(_CAMERA_PITCH_RANGE_DEG),
                    math.radians(_CAMERA_PITCH_RANGE_DEG),
                ),
            },
        ),
        "camera_fovy": EventTermCfg(
            mode="startup",
            func=dr.cam_fovy,
            params={
                "asset_cfg": SceneEntityCfg("robot", camera_names=(depth_camera.name,)),
                "operation": "add",
                "ranges": depth.fovy_sweep(),
            },
        ),
    }

    rewards = {
        "track_linear_velocity": RewardTermCfg(
            func=mdp.track_body_planar_velocity,
            weight=1.5,
            params={"command_name": "twist", "sigma": 0.25},
        ),
        "track_angular_velocity": RewardTermCfg(
            func=mdp.track_body_yaw_velocity,
            weight=0.5,
            params={"command_name": "twist", "sigma": 0.25},
        ),
        "lin_vel_z": RewardTermCfg(func=mdp.lin_vel_z_l2, weight=-1.0),
        "ang_vel_xy": RewardTermCfg(func=mdp.ang_vel_xy_l2, weight=-0.05),
        "orientation": RewardTermCfg(
            func=mdp.body_orientation_l2,
            # The paper-aligned -1.0 coefficient is too weak once the gait and
            # stair-traversal rewards are active: a 30 degree lean only costs
            # 0.25 reward before weighting. Make upright posture a primary
            # objective instead of a nearly free velocity-tracking shortcut.
            weight=-5.0,
            params={"asset_cfg": SceneEntityCfg("robot", body_names=(binding.root_body,))},
        ),
        "joint_acc": RewardTermCfg(func=mdp.joint_acc_l2, weight=-2.5e-7),
        "power": RewardTermCfg(
            func=mdp.joint_power_l1,
            weight=-2.0e-5,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=(".*",))},
        ),
        "collision": RewardTermCfg(
            func=mdp.collision_count,
            weight=-10.0,
            params={"sensor_name": nonfoot_ground.name, "force_threshold": 0.1},
        ),
        "action_rate": RewardTermCfg(func=mdp.action_rate_l2, weight=-0.01),
        "smoothness": RewardTermCfg(func=mdp.action_acc_l2, weight=-0.01),
        "joint_pos_limits": RewardTermCfg(func=mdp.joint_pos_limits, weight=-10.0),
    }
    terminations = {
        "time_out": TerminationTermCfg(func=mdp.time_out, time_out=True),
        "fell_over": TerminationTermCfg(
            func=mdp.bad_orientation,
            # Do not let rollouts spend time learning from a severely tilted
            # posture which is already unrecoverable for stair traversal.
            params={"limit_angle": math.radians(55.0)},
        ),
        "illegal_contact": TerminationTermCfg(
            func=mdp.illegal_contact,
            params={"sensor_name": nonfoot_ground.name, "force_threshold": 10.0},
        ),
    }
    curriculum = {
        "terrain_levels": CurriculumTermCfg(
            func=mdp.terrain_levels_vel,
            params={"command_name": "twist"},
        ),
        **{
            f"terrain_{terrain_name}_level": CurriculumTermCfg(
                func=mdp.terrain_curriculum_stat,
                params={"stat_name": f"{terrain_name}_level"},
            )
            for terrain_name in PIE_TERRAINS_CFG.sub_terrains
        },
    }

    cfg = ManagerBasedRlEnvCfg(
        scene=SceneCfg(
            terrain=TerrainEntityCfg(
                terrain_type="generator",
                terrain_generator=replace(PIE_TERRAINS_CFG),
                max_init_terrain_level=2,
            ),
            entities={"robot": robot_cfg()},
            sensors=(
                terrain_scan,
                *foot_rays,
                feet_ground,
                nonfoot_ground,
                depth_camera,
            ),
            num_envs=1 if play else 4096,
            extent=2.0,
        ),
        observations=observations,
        actions=actions,
        commands=commands,
        events=events,
        rewards=rewards,
        terminations=terminations,
        curriculum=curriculum,
        viewer=ViewerConfig(
            origin_type=ViewerConfig.OriginType.ASSET_BODY,
            entity_name="robot",
            body_name=binding.root_body,
            distance=1.8,
            elevation=-10.0,
            azimuth=90.0,
        ),
        sim=SimulationCfg(
            nconmax=48,
            njmax=1800,
            contact_sensor_maxmatch=500,
            mujoco=MujocoCfg(
                timestep=0.005,
                iterations=10,
                ls_iterations=20,
                ccd_iterations=500,
            ),
        ),
        decimation=4,
        episode_length_s=20.0,
    )

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.events.pop("push_robot", None)
        cfg.events.pop("camera_position", None)
        cfg.events.pop("camera_pitch", None)
        cfg.events.pop("camera_fovy", None)
        cfg.curriculum = {}
        cfg.events["randomize_terrain"] = EventTermCfg(
            func=envs_mdp.randomize_terrain,
            mode="reset",
            params={},
        )
        assert cfg.scene.terrain is not None
        assert cfg.scene.terrain.terrain_generator is not None
        cfg.scene.terrain.terrain_generator.curriculum = False
        cfg.scene.terrain.terrain_generator.num_cols = 5
        cfg.scene.terrain.terrain_generator.num_rows = 5
        cfg.scene.terrain.terrain_generator.border_width = 10.0

    # Diagonal-trot contact timing and stance-foot slip suppression.
    cfg.rewards["foot_gait"] = RewardTermCfg(
        func=mdp.feet_gait,
        weight=0.5,
        params={
            "period": 0.6,
            "offset": [0.0, 0.5, 0.5, 0.0],
            "threshold": 0.56,
            "command_threshold": 0.1,
            "command_name": "twist",
            "sensor_name": "feet_ground_contact",
        },
    )
    cfg.rewards["foot_slip"] = RewardTermCfg(
        func=mdp.feet_slip,
        weight=-0.25,
        params={
            "sensor_name": "feet_ground_contact",
            "command_name": "twist",
            "command_threshold": 0.1,
            "asset_cfg": SceneEntityCfg("robot", site_names=foot_sites),
        },
    )

    # Targeted posture shaping.
    cfg.rewards["joint_pos_limits"] = RewardTermCfg(
        func=mdp.joint_pos_limits,
        weight=-10.0,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=(".*",))},
    )
    cfg.rewards["hip_deviation_l2"] = RewardTermCfg(
        func=mdp.joint_deviation_l2,
        weight=-0.5,
        params={
            "asset_cfg": SceneEntityCfg(
                "robot", joint_names=binding.role_joint_pattern("hip_abduction")
            )
        },
    )
    cfg.rewards["base_height"] = RewardTermCfg(
        func=mdp.base_height_reward,
        weight=0.2,
        params={
            "sensor_name": "feet_ground_contact",
            "target_height": 0.27,
            "support_force_threshold": 1.0,
            "base_cfg": SceneEntityCfg("robot", body_names=(binding.root_body,)),
            "foot_cfg": SceneEntityCfg("robot", site_names=foot_sites),
        },
    )

    return cfg


def make_runner_cfg(profile: ParkourProfile) -> RslRlOnPolicyRunnerCfg:
    """Create the policy, estimator, and PPO settings for the PIE recipe."""
    return RslRlOnPolicyRunnerCfg(
        actor=RslRlModelCfg(
            class_name=PIE_ACTOR_CLASS_NAME,
            hidden_dims=(512, 256, 128),
            activation="elu",
            obs_normalization=True,
            cnn_cfg={
                "proprio_group": "actor",
                "history_group": "proprio_history",
                "depth_group": "camera",
                "velocity_target_group": "velocity_target",
                "height_target_group": "height_target",
                "foot_target_group": "foot_clearance_target",
                "successor_target_group": "successor_target",
                "history_length": 10,
                "depth_shape": (2, 60, 86),
                "token_dim": 64,
                "attention_heads": 1,
                "transformer_layers": 2,
                "transformer_ff_dim": 256,
                "transformer_dropout": 0.0,
                "memory_hidden_dim": 128,
                "memory_num_layers": 1,
                "map_latent_dim": 16,
                "vae_latent_dim": 16,
                "history_hidden_dims": (256, 128),
                "successor_decoder_dims": (64, 128),
                "height_decoder_dims": (64, 128),
                "output_channels": (32, 64, 64),
                "kernel_size": (8, 4, 3),
                "stride": (4, 2, 1),
                "padding": 0,
                "cnn_activation": "elu",
            },
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
        algorithm=PIEPpoAlgorithmCfg(
            class_name=PIE_PPO_CLASS_NAME,
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
            auxiliary_loss_coef=1.0,
            velocity_loss_coef=1.0,
            foot_clearance_loss_coef=1.0,
            height_reconstruction_loss_coef=1.0,
            successor_loss_coef=1.0,
            kl_loss_coef=4.0,
        ),
        obs_groups={
            "actor": ("actor", "proprio_history", "camera"),
            "critic": ("critic",),
        },
        experiment_name=profile.experiment_name,
        save_interval=1000,
        num_steps_per_env=24,
        max_iterations=20000,
    )
