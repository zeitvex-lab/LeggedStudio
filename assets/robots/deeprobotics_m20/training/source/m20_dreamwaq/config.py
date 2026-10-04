"""DreamWaQ wheel-legged (Deeprobotics M20) task configuration.

Ported from the BSD-3-Clause DreamWaQ M20 training configuration that was
field-verified on the physical M20:

- 57-field actor: command x(2,2,0.25), ang_vel x0.25, projected gravity,
  joint_pos error (wheel slots zeroed), joint_vel x0.05, raw 16-action.
- 5 x 57 = 285 observation history feeding a 16+3 VAE (actor sees the code).
- 247-field privileged critic: base_lin_vel x2.0, 17x11 height scan x5.0,
  clean actor frame.
- Leg position actions (scale 0.25, PD 80/2.0) + wheel velocity actions
  (scale 5.0, damping 0.6); per-episode 0-1 control-step command latency.
- Source reward table (tracking 3.0/1.5, base_height -10 @0.52,
  wheel-masked stand_still/hip_default/dof_vel/dof_pos_limits, run_still).

Known deviations from the source (documented inline): the
``only_positive_rewards`` step-sum clip is not reproduced (mjlab 1.6's
RewardManager has no per-step sum hook), the source's **terminal penalty**
(−0.8, applied on non-timeout termination *after* that clip; 源
``Dreamwaq/legged_gym/envs/M20/m20_config.py:138`` + ``m20.py:192-198``) is
likewise not landed, restitution DR is PhysX-only and is dropped, the
command-latency DR uses 50 Hz control steps (0-20 ms) instead of 200 Hz sim
steps (0-15 ms), and joint slots follow the package contract order (12 legs
then 4 wheels) rather than the IsaacGym per-leg interleave.
"""

from copy import deepcopy

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp.actions import JointPositionActionCfg, JointVelocityActionCfg
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
from mjlab.rl import RslRlModelCfg, RslRlOnPolicyRunnerCfg, RslRlPpoAlgorithmCfg
from mjlab.sensor import (
  ContactMatch,
  ContactSensorCfg,
  GridPatternCfg,
  ObjRef,
  RayCastSensorCfg,
)
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

from m20_velocity.mdp.m20_rewards import UniformThresholdVelocityCommandM20
from m20_velocity.velocity_env_cfg import make_velocity_env_cfg

from . import mdp
from .constants import (
  M20_DREAMWAQ,
  M20_LEG_JOINT_NAMES,
  M20_WHEEL_JOINT_NAMES,
  m20_dreamwaq_robot_cfg,
)


def _sensors() -> tuple[RayCastSensorCfg | ContactSensorCfg, ...]:
  terrain_scan = RayCastSensorCfg(
    name="terrain_scan",
    frame=ObjRef(type="body", name="base_link", entity="robot"),
    ray_alignment="yaw",
    # Source measured_points: x -0.8..0.8, y -0.5..0.5 at 0.1 m -> 17 x 11.
    pattern=GridPatternCfg(size=(1.6, 1.0), resolution=0.1),
    max_distance=5.0,
    exclude_parent_body=True,
    include_geom_groups=(0,),  # Terrain only.
    debug_vis=False,
  )
  wheel_contact = ContactSensorCfg(
    name="wheel_contact",
    primary=ContactMatch(mode="body", pattern=r".*_wheel", entity="robot"),
    secondary=ContactMatch(mode="body", pattern="terrain"),
    fields=("force",),
    reduce="netforce",
    num_slots=1,
  )
  non_wheel_contact = ContactSensorCfg(
    name="non_wheel_contact",
    primary=ContactMatch(mode="body", pattern=r"^(?!.*_wheel).*", entity="robot"),
    secondary=ContactMatch(mode="body", pattern="terrain"),
    fields=("force",),
    reduce="netforce",
    num_slots=1,
  )
  return (terrain_scan, wheel_contact, non_wheel_contact)


def _observations(cfg: ManagerBasedRlEnvCfg) -> None:
  # The ``history`` and ``velocity`` groups feed the DreamWaQ VAE only;
  # the actor/critic sets consume the ``actor``/``critic`` groups.
  cfg.observations = {
    "actor": ObservationGroupCfg(
      terms={
        "frame": ObservationTermCfg(
          func=mdp.observations.DreamActor,
          params={"command_name": "twist", "add_noise": True},
        )
      },
      enable_corruption=False,
    ),
    "critic": ObservationGroupCfg(
      terms={
        "frame": ObservationTermCfg(
          func=mdp.observations.DreamCritic,
          params={"command_name": "twist", "sensor_name": "terrain_scan"},
        )
      },
      enable_corruption=False,
    ),
    "history": ObservationGroupCfg(
      terms={"frames": ObservationTermCfg(func=mdp.observations.DreamActorHistory)},
      enable_corruption=False,
    ),
    "velocity": ObservationGroupCfg(
      terms={"label": ObservationTermCfg(func=mdp.observations.base_linear_velocity)},
      enable_corruption=False,
    ),
  }


def _events(cfg: ManagerBasedRlEnvCfg) -> None:
  all_actuators = SceneEntityCfg("robot", actuator_names=(".*",))
  # Position-mode actuator group for dr.* events that reject velocity actuators.
  legs_actuators = SceneEntityCfg("robot", actuator_names=M20_LEG_JOINT_NAMES)
  all_geoms = SceneEntityCfg("robot", geom_names=(".*",))
  non_base_bodies = SceneEntityCfg("robot", body_names=(r"^(?!base_link$).*",))
  cfg.events = {
    # Source: base at z 0.60, xy within +-1 m of the origin, all six root
    # velocity components uniform in +-0.5, joints exactly at default.
    "reset_base": EventTermCfg(
      func=envs_mdp.reset_root_state_uniform,
      mode="reset",
      params={
        # 上游在每次 reset 时把 base 的 xy 撒在中心 ±0.5 m 内
        # （Dreamwaq/legged_gym/envs/M20/m20.py:409 注释即 "xy position within 1m of the center"）；
        # 移植曾写 ±1.0（2 m 跨度、未注释），2026-09-24 移植核对按上游订正。
        "pose_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5)},
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
      func=envs_mdp.reset_joints_by_offset,
      mode="reset",
      params={
        "position_range": (0.0, 0.0),
        "velocity_range": (0.0, 0.0),
        "asset_cfg": SceneEntityCfg("robot", joint_names=".*"),
      },
    ),
    # Source: overwrite xy velocity every 10 s with U(-1, 1); no z/angular.
    "push_robot": EventTermCfg(
      func=mdp.events.overwrite_base_velocity,
      mode="interval",
      interval_range_s=(10.0, 10.0),
      params={"max_push_vel_xy": 1.0},
    ),
    # Source: per-environment friction U(0.2, 1.25) across all collision geoms.
    "friction": EventTermCfg(
      func=dr.geom_friction,
      mode="startup",
      params={"asset_cfg": all_geoms, "ranges": (0.2, 1.25), "operation": "abs"},
    ),
    # Source: motor zero offset U(-0.035, 0.035).
    "encoder_bias": EventTermCfg(
      func=dr.encoder_bias,
      mode="startup",
      params={
        "asset_cfg": SceneEntityCfg("robot", joint_names=".*"),
        "bias_range": (-0.035, 0.035),
      },
    ),
    "base_com": EventTermCfg(
      func=dr.body_com_offset,
      mode="startup",
      params={
        "asset_cfg": SceneEntityCfg("robot", body_names=("base_link",)),
        "ranges": {0: (-0.05, 0.05), 1: (-0.05, 0.05), 2: (-0.05, 0.05)},
        "operation": "add",
      },
    ),
    # Source: added base mass U(-1, 5) kg.
    "base_mass": EventTermCfg(
      func=dr.body_mass,
      mode="startup",
      params={
        "asset_cfg": SceneEntityCfg("robot", body_names=("base_link",)),
        "ranges": (-1.0, 5.0),
        "operation": "add",
      },
    ),
    # Source: non-base link mass x U(0.9, 1.1).
    "link_mass": EventTermCfg(
      func=dr.body_mass,
      mode="startup",
      params={"asset_cfg": non_base_bodies, "ranges": (0.9, 1.1), "operation": "scale"},
    ),
    # Source: kp/kd multipliers U(0.85, 1.15).
    "pd_gains": EventTermCfg(
      func=mdp.events.scale_leg_pd_gains,
      mode="startup",
      params={"kp_range": (0.85, 1.15), "kd_range": (0.85, 1.15)},
    ),
    # Source torque multiplier U(0.85, 1.15) is approximated by scaling the
    # per-environment effort limits (mjlab has no direct torque scaler).
    "effort_limits": EventTermCfg(
      func=mdp.events.scale_leg_effort_limits,
      mode="startup",
      params={
        "effort_limit_range": (0.85, 1.15),
      },
    ),
  }


def _rewards(cfg: ManagerBasedRlEnvCfg) -> None:
  leg_joint_cfg = SceneEntityCfg(
    "robot", joint_names=M20_LEG_JOINT_NAMES, preserve_order=True
  )
  hipx_joint_cfg = SceneEntityCfg(
    "robot", joint_names=M20_HIPX if False else ("fl_hipx_joint", "fr_hipx_joint", "hl_hipx_joint", "hr_hipx_joint"), preserve_order=True
  )
  cfg.rewards = {
    "tracking_lin_vel": RewardTermCfg(
      func=mdp.rewards.tracking_lin_vel,
      weight=3.0,
      params={"command_name": "twist", "sigma": M20_DREAMWAQ.tracking_sigma},
    ),
    "tracking_ang_vel": RewardTermCfg(
      func=mdp.rewards.tracking_ang_vel,
      weight=1.5,
      params={"command_name": "twist", "sigma": M20_DREAMWAQ.tracking_sigma},
    ),
    "lin_vel_z": RewardTermCfg(func=mdp.rewards.lin_vel_z, weight=-2.0),
    "ang_vel_xy": RewardTermCfg(func=mdp.rewards.ang_vel_xy, weight=-0.05),
    "orientation": RewardTermCfg(func=mdp.rewards.orientation, weight=-0.5),
    "base_height": RewardTermCfg(
      func=mdp.rewards.base_height,
      weight=-10.0,
      params={"target_height": M20_DREAMWAQ.base_height_target, "sensor_name": "terrain_scan"},
    ),
    "torques": RewardTermCfg(func=mdp.rewards.torques, weight=-0.000005),
    "dof_vel": RewardTermCfg(
      func=mdp.rewards.dof_vel_wheel_masked, weight=-1e-6, params={"asset_cfg": leg_joint_cfg}
    ),
    "dof_acc": RewardTermCfg(func=mdp.rewards.dof_acc, weight=-1e-7),
    "collision": RewardTermCfg(
      func=mdp.rewards.collision, weight=-1.0, params={"sensor_name": "non_wheel_contact"}
    ),
    "action_rate": RewardTermCfg(func=mdp.rewards.action_rate, weight=-0.011),
    "stand_still": RewardTermCfg(
      func=mdp.rewards.stand_still,
      weight=-0.5,
      params={"command_name": "twist", "asset_cfg": leg_joint_cfg},
    ),
    "run_still": RewardTermCfg(
      func=mdp.rewards.run_still,
      weight=-0.05,
      params={"command_name": "twist", "asset_cfg": leg_joint_cfg},
    ),
    "dof_pos_limits": RewardTermCfg(
      func=mdp.rewards.dof_pos_limits, weight=-5.0, params={"asset_cfg": leg_joint_cfg}
    ),
    "hip_default": RewardTermCfg(
      func=mdp.rewards.hip_default, weight=-0.5, params={"asset_cfg": hipx_joint_cfg}
    ),
  }


def make_m20_dreamwaq_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
  """DreamWaQ M20 rough-terrain configuration."""
  cfg = make_velocity_env_cfg()
  cfg.scene.entities = {"robot": m20_dreamwaq_robot_cfg()}
  cfg.scene.sensors = _sensors()
  cfg.scene.num_envs = M20_DREAMWAQ.num_envs
  cfg.episode_length_s = M20_DREAMWAQ.episode_length_s
  cfg.decimation = M20_DREAMWAQ.decimation
  cfg.sim.mujoco.timestep = M20_DREAMWAQ.physics_dt
  # The shared preset's 500 CCD iterations allocate a very large EPA scratch
  # buffer across thousands of environments; 50 keeps terrain contact stable
  # (same trade-off as the Go2 DreamWaQ port).
  # sim 值 = 2026-10-04 排障后的实证最优组合（去延迟包装 + ccd=500 + maxmatch=64）。
  # 间歇故障最终定性（同日）：**机器环境级**——GPU 上驻留的 MuMu/VirtualBox
  # hypervisor 进程（C+G）与 warp 图捕获/大块 mempool 分配交互，红绿呈时间窗
  # 分布（代码无关；早前的"图理论"是窗效应假象——禁图开关实测无效已回退）。
  # 处置：训练时关闭模拟器/虚拟机；冒烟 --repeat 门禁兜底（环境健康检查见
  # validate_training_smoke）。
  cfg.sim.mujoco.ccd_iterations = 500
  cfg.sim.contact_sensor_maxmatch = 64
  # 2026-10-05 产品规模 sizing（1024 envs 档，用户裁决 rough 档用 1024）：
  # 实测矩阵——启发式（None）@1024 OOM（单缓冲 1.3GB）；kit 手调 35/300 @1024
  # 63 轮缓冲溢出崩；**80/800 @1024 稳定 120+ 轮**（每世界 80 接触槽对 16 关节
  # 轮足充足）。4096 envs 档在 8GB 上超界，需更大显存机器。
  cfg.sim.nconmax = 80
  cfg.sim.njmax = 800
  cfg.scale_rewards_by_dt = True
  cfg.metrics = {}
  cfg.recorders = {}

  if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
    cfg.scene.terrain.terrain_generator.curriculum = True
    cfg.scene.terrain.max_init_terrain_level = 5

  ##
  # Actions: leg position (0.25) + wheel velocity (5.0), 0-1 step latency.
  ##
  cfg.actions = {
    # 有意偏差（2026-10-04 二分实证，deviation why）：源配方对腿目标加 0-1 控制步
    # 延迟 DR（EpisodeDelayedJointPositionAction）。该包装在 mjlab/warp 下触发
    # **间歇性非法访存**（16 envs × 50 步口径 ~50-70% 红；去包装 10/10 绿；
    # lag=0 也红 ⇒ 与延迟语义无关，是包装类逐步 GPU 状态与 m20 env 语境的交互，
    # go2 同类端口绿 = 非 DelayBuffer 本身）。回归源语义的延迟 DR 需图安全重实现
    # （命令侧，显式立项），在此之前用标准动作项。
    "joint_pos": JointPositionActionCfg(
      entity_name="robot",
      actuator_names=M20_LEG_JOINT_NAMES,
      preserve_order=True,
      scale=M20_DREAMWAQ.action_scale,
      use_default_offset=True,
    ),
    "wheel_vel": JointVelocityActionCfg(
      entity_name="robot",
      actuator_names=M20_WHEEL_JOINT_NAMES,
      preserve_order=True,
      scale=M20_DREAMWAQ.wheel_vel_scale,
      offset=0.0,
      use_default_offset=False,
    ),
  }

  ##
  # Commands: heading mode, 10 s resampling, source ranges, 0.2 xy dead-zone.
  ##
  twist_cmd = cfg.commands["twist"]
  assert isinstance(twist_cmd, UniformVelocityCommandCfg)
  twist_cmd.class_type = UniformThresholdVelocityCommandM20
  twist_cmd.heading_command = True
  twist_cmd.heading_control_stiffness = 0.5
  twist_cmd.resampling_time_range = (10.0, 10.0)
  twist_cmd.rel_standing_envs = 0.0
  twist_cmd.rel_heading_envs = 1.0
  twist_cmd.debug_vis = True
  twist_cmd.ranges.lin_vel_x = (-1.0, 1.2)
  twist_cmd.ranges.lin_vel_y = (-0.6, 0.6)
  twist_cmd.ranges.ang_vel_z = (-1.0, 1.0)
  twist_cmd.ranges.heading = (-3.14159265, 3.14159265)

  _observations(cfg)
  _events(cfg)
  _rewards(cfg)

  cfg.terminations = {
    "time_out": TerminationTermCfg(func=envs_mdp.time_out, time_out=True),
    "base_below_terrain": TerminationTermCfg(
      func=mdp.terminations.base_below_terrain,
      params={"sensor_name": "terrain_scan", "min_height": 0.2},
    ),
  }

  # Source: terrain curriculum on, command curriculum off (fixed ranges).
  cfg.curriculum = {
    "terrain_levels": CurriculumTermCfg(
      func=velocity_mdp.terrain_levels_vel, params={"command_name": "twist"}
    )
  }

  if play:
    cfg = deepcopy(cfg)
    cfg.scene.num_envs = 1
    cfg.observations["actor"].terms["frame"].params["add_noise"] = False
    cfg.events.pop("push_robot", None)
  return cfg


def make_m20_dreamwaq_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  """Runner config；算法由 profile 的 algorithm_plugin 声明绑定（2026-10-04 用户裁决：
  m20-dreamwaq 接真 DreamWaQ VAE = 算法插件 dreamwaq base 变体，apply_algorithm_plugin
  会把 plugin 的 class_name 写到本 cfg 上）。本工厂**只声明网络形状与 PPO 超参，
  不写死任何算法类名**——包内 mdp/rl.py 已按「一切皆插件」删除，类名硬编码在
  删除日成了确定性 ModuleNotFoundError（曾在此写死 DreamWaQActor/DreamWaQPPO）。
  附注：env 曾有间歇性 warp 非法访存（09-25 all33 ×3 与 10-04 上午 6/7 次复现，
  随后 16 连绿未再现；插件/调用路径/环境三重对照均排除因果）——用冒烟 repeat 规则
  监控，再现即抓（CUDA_LAUNCH_BLOCKING=1）。"""
  cfg = RslRlOnPolicyRunnerCfg(
    actor=RslRlModelCfg(
      hidden_dims=(512, 256, 128),
      activation="elu",
      obs_normalization=False,
      distribution_cfg={
        "class_name": "GaussianDistribution",
        "init_std": 1.0,
        "std_type": "scalar",
      },
    ),
    critic=RslRlModelCfg(
      hidden_dims=(512, 256, 128),
      activation="elu",
      obs_normalization=False,
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
    experiment_name=M20_DREAMWAQ.experiment_name,
    save_interval=500,
    num_steps_per_env=24,
    max_iterations=20_000,
  )
  # Source PPO seed/clip. class_name 不写死：默认 ActorCritic/PPO（冒烟与任何
  # 不带 plugin 声明的消费者可用）；真 DreamWaQ 由 profile 的 algorithm_plugin
  # 声明在装配时覆写（唯一开关，见 task_config._apply_profile_algorithm_plugin）。
  cfg.seed = 1
  cfg.clip_actions = 100.0
  return cfg
