"""Go2 Walk-These-Ways style periodic-gait locomotion task.

Periodic Reward Framework (OSU arXiv:2011.01387) ported from LeggedGym-Ex
``go2_wtw.py`` (BSD-3-Clause): a global gait phase advances every control
step; per-leg theta offsets select trot/pronk/pace/bound patterns; each
leg's swing/stance expectation penalizes foot speed (swing) and contact
force (stance); behavior parameters (gait period, foot clearance, base
height, pitch) are both observations and curriculum-sampled ranges.

Observation: 45-dim rl_sdk base + theta(4) + clock(8) + behavior(4) = 61.
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers import EventTermCfg
from mjlab.managers.observation_manager import ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg, ObjRef
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise

from local_tasks.mjlab_extension import register as _register_go2_assets

_register_go2_assets()

from local_tasks.robots.unitree.go2.tasks.locomotion import wtw_mdp


def go2_wtw_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Go2 periodic-gait (Walk-These-Ways) rough configuration."""
    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = 500
    cfg.sim.contact_sensor_maxmatch = 500
    cfg.scene.entities = {"robot": _registered_go2_robot_cfg()}

    # Raycast frames: base scan on the trunk, per-foot scans on the FR/FL/RR/RL sites.
    for sensor in cfg.scene.sensors or ():
        if sensor.name == "terrain_scan":
            sensor.frame.name = "base_link"
        elif sensor.name == "foot_height_scan":
            sensor.frame = tuple(
                ObjRef(type="site", name=s, entity="robot") for s in ("FR", "FL", "RR", "RL")
            )

    # The base env_cfg's air-time / contact terms reference this sensor; the
    # official go1/g1 configs add it in their own builders.
    cfg.scene.sensors = tuple(cfg.scene.sensors or ()) + (
        ContactSensorCfg(
            name="feet_ground_contact",
            primary=ContactMatch(
                mode="geom",
                pattern=tuple(f"{n}_foot_collision" for n in ("FR", "FL", "RR", "RL")),
                entity="robot",
            ),
            secondary=ContactMatch(mode="body", pattern="terrain"),
            fields=("found", "force"),
            reduce="netforce",
            num_slots=1,
            track_air_time=True,
        ),
        ContactSensorCfg(
            name="nonfoot_ground_touch",
            primary=ContactMatch(mode="body", pattern=r"^(?!.*_calf).*", entity="robot"),
            secondary=ContactMatch(mode="body", pattern="terrain"),
            fields=("force",),
            reduce="netforce",
            num_slots=1,
        ),
    )
    feet_sensor = wtw_mdp.ContactSensorRef("feet_ground_contact", (0, 1, 2, 3))
    nonfoot_sensor = wtw_mdp.ContactSensorRef("nonfoot_ground_touch", None)

    # The Go2 MJCF has no dedicated foot links; the calf tip is the foot.
    foot_cfg = SceneEntityCfg("robot", body_names=[f"{lr}_calf" for lr in ("FL", "FR", "RL", "RR")])
    trunk_cfg = SceneEntityCfg("robot", body_names=["base_link"])
    all_joint_cfg = SceneEntityCfg("robot")

    ##
    # Actions: baseline joint position (12)
    ##
    cfg.actions["joint_pos"].scale = 0.25

    ##
    # Events: reset-time behavior resampling (theta + behavior params)
    ##
    cfg.events["wtw_behavior_resample"] = EventTermCfg(
        func=wtw_mdp.resample_behavior_params, mode="reset"
    )

    ##
    # Terrain curriculum retained from the base (WTW relies on terrain levels)
    ##
    if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
        cfg.scene.terrain.terrain_generator.curriculum = True

    ##
    # Commands: baseline ranges (WTW resamples phase/theta on reset)
    ##
    twist_cmd = cfg.commands["twist"]
    assert isinstance(twist_cmd, UniformVelocityCommandCfg)
    twist_cmd.resampling_time_range = (10.0, 10.0)

    ##
    # Observations: 45-dim base + WTW clock / theta / behavior params = 61
    ##
    for group_name in ("actor", "critic"):
        terms = cfg.observations[group_name].terms
        terms["wtw_clock"] = ObservationTermCfg(
            func=wtw_mdp.clock_observation, params={"dt": 0.02}
        )
        terms["wtw_theta"] = ObservationTermCfg(func=wtw_mdp.theta_observation)
        terms["wtw_behavior"] = ObservationTermCfg(func=wtw_mdp.behavior_params_observation)

    ##
    # Rewards: official WTW weight table
    ##
    cfg.rewards = {
        "tracking_lin_vel": RewardTermCfg(
            func=velocity_mdp.track_linear_velocity, weight=1.0, params={"command_name": "twist", "std": 0.425}
        ),
        "tracking_ang_vel": RewardTermCfg(
            func=velocity_mdp.track_angular_velocity, weight=0.5, params={"command_name": "twist", "std": 0.7854}
        ),
        "tracking_base_height": RewardTermCfg(
            func=wtw_mdp.tracking_base_height, weight=0.6, params={"asset_cfg": SceneEntityCfg("robot")}
        ),
        "tracking_orientation": RewardTermCfg(
            func=wtw_mdp.tracking_orientation, weight=0.6, params={"asset_cfg": SceneEntityCfg("robot")}
        ),
        "tracking_foot_clearance": RewardTermCfg(
            func=wtw_mdp.tracking_foot_clearance,
            weight=0.9,
            params={"sensor_cfg": feet_sensor, "asset_cfg": foot_cfg},
        ),
        "quad_periodic_gait": RewardTermCfg(
            func=wtw_mdp.quad_periodic_gait,
            weight=1.5,
            params={"sensor_cfg": feet_sensor, "asset_cfg": foot_cfg, "a_swing": 0.0, "b_swing": 0.5},
        ),
        "lin_vel_z": RewardTermCfg(func=wtw_mdp.lin_vel_z_l2, weight=-0.5),
        "ang_vel_xy": RewardTermCfg(func=wtw_mdp.ang_vel_xy_l2, weight=-0.05),
        "dof_vel": RewardTermCfg(func=envs_mdp.joint_vel_l2, weight=-5e-4),
        "dof_acc": RewardTermCfg(func=envs_mdp.joint_acc_l2, weight=-2e-7),
        "action_rate": RewardTermCfg(func=envs_mdp.action_rate_l2, weight=-0.01),
        "action_smoothness": RewardTermCfg(func=wtw_mdp.action_smoothness, weight=-0.01),
        "torques": RewardTermCfg(func=envs_mdp.joint_torques_l2, weight=-2e-4),
        "foot_landing_vel": RewardTermCfg(
            func=wtw_mdp.foot_landing_vel, weight=-0.1, params={"sensor_cfg": feet_sensor, "asset_cfg": foot_cfg}
        ),
        "hip_pos": RewardTermCfg(func=wtw_mdp.hip_pos, weight=-1.0),
        "dof_pos_limits": RewardTermCfg(
            func=envs_mdp.joint_pos_limits, weight=-10.0, params={"asset_cfg": all_joint_cfg}
        ),
        "collision": RewardTermCfg(
            func=wtw_mdp.undesired_contacts,
            weight=-1.0,
            params={"sensor_cfg": nonfoot_sensor, "threshold": 1.0},
        ),
    }

    cfg.viewer.body_name = "base_link"
    cfg.viewer.distance = 1.5
    cfg.viewer.elevation = -10.0

    if play:
        cfg.episode_length_s = int(1e9)
        cfg.observations["policy"].enable_corruption = False
        cfg.curriculum = {}
        if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
            terrain = cfg.scene.terrain.terrain_generator
            terrain.curriculum = False
            terrain.num_cols = 5
            terrain.num_rows = 5
            terrain.border_width = 10.0
    return cfg


def _registered_go2_robot_cfg():
    """Resolve the extension-registered Go2 asset config."""
    import mjlab.asset_zoo.robots.unitree_go2 as go2

    return go2.get_go2_robot_cfg()


def go2_wtw_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Go2 WTW flat-ground variant."""
    cfg = go2_wtw_rough_env_cfg(play=play)
    cfg.sim.njmax = 300
    cfg.sim.mujoco.ccd_iterations = 50
    cfg.sim.contact_sensor_maxmatch = 64
    assert cfg.scene.terrain is not None
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.curriculum.pop("terrain_levels", None)
    return cfg


def go2_wtw_runner_cfg():
    """Official WTW PPO runner config (MLP 512/256/128, 10k iters)."""
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
        experiment_name="go2_wtw",
        save_interval=100,
        num_steps_per_env=24,
        max_iterations=10_000,
    )
