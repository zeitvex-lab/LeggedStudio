"""LimX TRON1 sole-foot velocity environment configuration.

Flat-ground velocity task built from the package-local robot constants and
mjlab's shared velocity base, adapted from LeggedGym-Ex
``legged_gym/envs/tron1sf/tron1sf_config.py`` (BSD-3):

- Policy observation: 33 dims = cmd(3) + projected_gravity(3) + ang_vel(3)
  + joint_pos(8) + joint_vel(8) + last_action(8), stacked with
  ``history_length=10`` (source ``frame_stack=10`` -> 330-dim policy input).
- Command ranges: lin_vel_x +-0.5, lin_vel_y +-1.0, ang_vel_z +-1 (heading mode).
- Rewards mapped to the source table: tracking 1.0/1.0, keep_balance 1.0,
  dof_pos_limits -2.0, feet_air_time 1.0, foot_clearance (target 0.1 m,
  source offset 0.055 m is the ankle origin height), ang_vel_xy -0.05,
  action_rate -0.01, plus shared biped terms ``feet_distance_ours`` (-100),
  ``no_fly`` (0.4), ``foot_landing_vel`` (-0.15) and ``foot_flat`` (0.3) from
  ``adapters/mjlab/shared_rewards``; ``hip_pos_zero_command`` (-10) maps onto
  the ``pose`` posture term with tightened hip stds.
- Terminations: non-foot body contact, bad orientation (70 deg), timeout.
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers import TerminationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import (
    ContactMatch,
    ContactSensorCfg,
    ObjRef,
    RingPatternCfg,
    TerrainHeightSensorCfg,
)
from mjlab.tasks.velocity import mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg

from shared_rewards import feet_distance_ours, foot_flat, foot_landing_vel, no_fly

from .robot_constants import TRON1_SF_ACTION_SCALE, get_tron1_sf_robot_cfg

# 包内 MJCF 为独足(sole-foot):足端即踝,帧/接触/终止判定全部锚定 ankle_L/R_Link
# (据 robot.xml:69/96)。MJCF 无 ankle site(唯一 site 为 imu),高度扫描改用足端
# body 帧(lite3 B31 同款修法),一律不用 site 引用。
_FOOT_GEOMS = ("ankle_L_collision", "ankle_R_collision")
_FOOT_BODIES = ("ankle_L_Link", "ankle_R_Link")
_ROOT_BODY = "base_Link"

_HISTORY_LEN = 10  # source env.frame_stack / c_frame_stack


def _configure_foot_height_sensor(cfg: ManagerBasedRlEnvCfg) -> None:
    for sensor in cfg.scene.sensors or ():
        if sensor.name == "foot_height_scan":
            assert isinstance(sensor, TerrainHeightSensorCfg)
            # MJCF 无 ankle site,改用足端 body 帧(lite3 B31 同款修法)。
            sensor.frame = tuple(
                ObjRef(type="body", name=name, entity="robot") for name in _FOOT_BODIES
            )
            sensor.pattern = RingPatternCfg.single_ring(radius=0.05, num_samples=6)


def _contact_sensors() -> tuple[ContactSensorCfg, ContactSensorCfg]:
    feet = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(mode="geom", pattern=_FOOT_GEOMS, entity="robot"),
            fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    other = ContactSensorCfg(
        name="nonfoot_ground_touch",
        primary=ContactMatch(
            mode="geom", pattern=".*_collision", entity="robot", exclude=_FOOT_GEOMS
        ),
            fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    return feet, other


def _restructure_actor_obs(cfg: ManagerBasedRlEnvCfg) -> None:
    """Rebuild the actor group to the source 33-dim layout and stack history.

    Source order: cmd, projected_gravity, ang_vel, dof_pos, dof_vel, action.
    ``base_lin_vel`` stays available to the critic only (privileged).
    """
    actor = cfg.observations["actor"]
    terms = dict(actor.terms)

    command = terms.pop("command")
    gravity = terms.pop("projected_gravity")
    ang_vel = terms.pop("base_ang_vel")
    # 包内 MJCF 未声明 imu_ang_vel/imu_lin_vel 传感器(mjlab 自动生成的内置传感器
    # 名为 robot/gyro、robot/acc),base cfg 的 builtin_sensor 项在构建期即 KeyError;
    # 改用状态量计算的 base_ang_vel/base_lin_vel(lite3 B31 同款修法),语义不变。
    # critic 组与 actor 组共享同一 term 对象,此处改写即同时生效。
    ang_vel.func = envs_mdp.base_ang_vel
    ang_vel.params = {}
    ang_vel.scale = 0.25  # source obs_scales.ang_vel
    joint_pos = terms.pop("joint_pos")  # biased: dof_pos - default (scale 1.0)
    joint_vel = terms.pop("joint_vel")
    joint_vel.scale = 0.05  # source obs_scales.dof_vel
    actions = terms.pop("actions")
    lin_vel = terms.pop("base_lin_vel", None)
    if lin_vel is not None:  # critic 专属特权观测,同样去传感器化
        lin_vel.func = envs_mdp.base_lin_vel
        lin_vel.params = {}
    terms.pop("height_scan", None)

    actor.terms = {
        "command": command,
        "projected_gravity": gravity,
        "base_ang_vel": ang_vel,
        "joint_pos": joint_pos,
        "joint_vel": joint_vel,
        "actions": actions,
    }
    actor.history_length = _HISTORY_LEN
    critic = cfg.observations["critic"]
    critic.history_length = _HISTORY_LEN  # source c_frame_stack


def _configure_rewards(cfg: ManagerBasedRlEnvCfg) -> None:
    cfg.rewards["track_linear_velocity"].weight = 1.0  # tracking_lin_vel
    cfg.rewards["track_angular_velocity"].weight = 1.0  # tracking_ang_vel
    cfg.rewards["upright"].weight = 1.0  # keep_balance
    cfg.rewards["body_ang_vel"].weight = -0.05  # ang_vel_xy
    cfg.rewards["dof_pos_limits"].weight = -2.0
    cfg.rewards["action_rate_l2"].weight = -0.01  # action_rate
    cfg.rewards["air_time"].weight = 1.0  # feet_air_time
    # MJCF 无 site:foot_clearance/foot_slip(mdp.feet_clearance/feet_slip)依赖
    # site 线速度(site_ids 为空则与高度扫描帧数不匹配,step 期即形状错误),
    # 无法锚定,直接移除这两项(其余足端项均走接触/高度传感器,不受影响)。
    cfg.rewards.pop("foot_clearance", None)
    cfg.rewards.pop("foot_slip", None)
    cfg.rewards["foot_swing_height"].weight = 0.0
    cfg.rewards["soft_landing"].weight = 0.0

    cfg.rewards["feet_distance"] = RewardTermCfg(
        func=feet_distance_ours,
        weight=-1.0,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=_FOOT_BODIES),
            "min_dist": 0.115,  # source rewards.foot_distance_threshold
            "weight": 100.0,  # source rewards.scales.feet_distance
        },
    )
    cfg.rewards["no_fly"] = RewardTermCfg(
        func=no_fly,
        weight=0.4,
        params={
            "sensor_cfg": SceneEntityCfg("feet_ground_contact"),
            "asset_cfg": SceneEntityCfg("robot", body_names=_FOOT_BODIES),
            "air_time_threshold": 0.3,
        },
    )
    cfg.rewards["foot_landing_vel"] = RewardTermCfg(
        func=foot_landing_vel,
        weight=-0.15,
        params={
            "sensor_cfg": SceneEntityCfg("feet_ground_contact"),
            "asset_cfg": SceneEntityCfg("robot", body_names=_FOOT_BODIES),
            "height_threshold": 0.05,  # source rewards.about_landing_threshold
        },
    )
    cfg.rewards["foot_flat"] = RewardTermCfg(
        func=foot_flat,
        weight=0.3,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=_FOOT_BODIES),
            "sigma": 0.1,
        },
    )

    # Posture regularisation; the tightened hip stds stand in for the source
    # hip_pos_zero_command (-10) term (keep hips near zero while walking).
    cfg.rewards["pose"].params["std_standing"] = {r".*_Joint": 0.05}
    moving = {
        r".*(?:abad|hip)_.*_Joint": 0.15,
        r".*knee_.*_Joint": 0.35,
        r".*ankle_.*_Joint": 0.25,
    }
    cfg.rewards["pose"].params["std_walking"] = moving
    cfg.rewards["pose"].params["std_running"] = moving


def make_tron1_sf_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground TRON1-SF velocity configuration (source trains on plane)."""
    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = 50
    cfg.sim.contact_sensor_maxmatch = 64
    cfg.sim.nconmax = None
    cfg.scene.entities = {"robot": get_tron1_sf_robot_cfg()}

    _configure_foot_height_sensor(cfg)
    feet_sensor, other_sensor = _contact_sensors()
    cfg.scene.sensors = (cfg.scene.sensors or ()) + (feet_sensor, other_sensor)

    assert cfg.scene.terrain is not None
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.scene.sensors = tuple(
        sensor for sensor in (cfg.scene.sensors or ()) if sensor.name != "terrain_scan"
    )

    action = cfg.actions["joint_pos"]
    assert isinstance(action, JointPositionActionCfg)
    action.scale = TRON1_SF_ACTION_SCALE

    cfg.viewer.body_name = _ROOT_BODY
    cfg.viewer.distance = 2.0
    cfg.viewer.elevation = -10.0

    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.resampling_time_range = (10.0, 10.0)  # source commands.resampling_time
    command.ranges.lin_vel_x = (-0.5, 0.5)
    command.ranges.lin_vel_y = (-1.0, 1.0)
    command.ranges.ang_vel_z = (-1.0, 1.0)
    command.ranges.heading = (-3.14, 3.14)
    command.viz.z_offset = 0.85

    # Domain randomisation (source domain_rand; PD-gain/armature/friction
    # randomisation stays with the mjlab event set -- encoder_bias here).
    cfg.events["foot_friction"].params["asset_cfg"].geom_names = _FOOT_GEOMS
    cfg.events["foot_friction"].params["ranges"] = (0.0, 2.0)
    cfg.events["base_com"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    cfg.events["base_com"].params["ranges"] = {
        0: (-0.03, 0.03),
        1: (-0.03, 0.03),
        2: (-0.03, 0.03),
    }
    cfg.events["push_robot"].params["interval_range_s"] = (10.0, 10.0)
    cfg.events["push_robot"].params["velocity_range"] = {
        "x": (-1.0, 1.0),
        "y": (-1.0, 1.0),
        "z": (-0.4, 0.4),
    }

    _configure_rewards(cfg)
    cfg.rewards["upright"].params["asset_cfg"].body_names = (_ROOT_BODY,)
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = (_ROOT_BODY,)

    _restructure_actor_obs(cfg)
    cfg.observations["critic"].terms.pop("height_scan", None)

    # Terminations: keep bad_orientation + time_out, add non-foot contact
    # (source penalize/terminate contacts on knee/hip/base/abad, never ankle).
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.terminations["illegal_contact"] = TerminationTermCfg(
        func=mdp.illegal_contact,
        params={"sensor_name": other_sensor.name, "force_threshold": 10.0},
    )

    # Fixed command ranges: drop the mjlab velocity-stage curriculum (its later
    # stages go far beyond the TRON1 source command envelope).
    cfg.curriculum.pop("terrain_levels", None)
    cfg.curriculum.pop("command_vel", None)

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["actor"].enable_corruption = False
        cfg.events.pop("push_robot", None)
        cfg.events.pop("foot_friction", None)
        cfg.curriculum = {}

    return cfg


def sf_flat_env_cfg(*, play: bool = False):
    return make_tron1_sf_flat_env_cfg(play=play)


def sf_runner_cfg():
    from mjlab.rl import (
        RslRlModelCfg,
        RslRlOnPolicyRunnerCfg,
        RslRlPpoAlgorithmCfg,
    )

    return RslRlOnPolicyRunnerCfg(
        actor=RslRlModelCfg(
            hidden_dims=(512, 256, 128),
            activation="elu",
            obs_normalization=True,
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
        experiment_name="tron1_sf_velocity",
        save_interval=100,
        num_steps_per_env=24,
        max_iterations=15_000,  # source max_iterations 4000 @4096 envs
    )
