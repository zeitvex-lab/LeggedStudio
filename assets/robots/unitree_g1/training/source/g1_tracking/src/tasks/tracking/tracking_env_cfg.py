"""Motion-tracking (DeepMimic-style) task configuration.

Builds on mjlab's built-in G1 velocity environment and replaces the command
tracking stack with the DeepMimic tracking reward family driven by reference
motion pkls, plus reference-state-initialization resets.
"""

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.observation_manager import ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.config.g1.env_cfgs import unitree_g1_flat_env_cfg

import src.tasks.tracking.mdp as tracking_mdp

# Tracking reward sigmas (upstream g1_deepmimic config).
TRACKING_DOF_POS_SIGMA = 4.0
TRACKING_DOF_VEL_SIGMA = 100.0
TRACKING_REF_BASE_POSE_SIGMA = 0.2
TRACKING_REF_BASE_VEL_SIGMA = 1.0
TRACKING_REF_KEY_POS_SIGMA = 0.1
# Upstream reference_state_initialization_prob.
RSI_PROB = 0.7


def make_tracking_env_cfg(motion_dir: str) -> ManagerBasedRlEnvCfg:
  """Create the motion-tracking configuration from the flat G1 velocity cfg."""
  cfg = unitree_g1_flat_env_cfg(play=False)

  # DeepMimic episodes are bounded; keep the upstream 10 s cap.
  cfg.episode_length_s = 10.0

  ##
  # Observations: drop command / lin-vel proprioception, add reference frame.
  ##

  del cfg.observations["actor"].terms["command"]
  del cfg.observations["actor"].terms["base_lin_vel"]
  del cfg.observations["critic"].terms["command"]
  ref_terms = {
    "ref_dof_pos": ObservationTermCfg(
      func=tracking_mdp.ref_dof_pos, params={"motion_dir": motion_dir}
    ),
    "ref_dof_vel": ObservationTermCfg(
      func=tracking_mdp.ref_dof_vel, params={"motion_dir": motion_dir}
    ),
    "ref_base_quat": ObservationTermCfg(
      func=tracking_mdp.ref_base_quat, params={"motion_dir": motion_dir}
    ),
    "ref_base_lin_vel_b": ObservationTermCfg(
      func=tracking_mdp.ref_base_lin_vel_b, params={"motion_dir": motion_dir}
    ),
    "ref_base_ang_vel_b": ObservationTermCfg(
      func=tracking_mdp.ref_base_ang_vel_b, params={"motion_dir": motion_dir}
    ),
  }
  for name, term in ref_terms.items():
    cfg.observations["actor"].terms[name] = term
    cfg.observations["critic"].terms[name] = term

  ##
  # Commands: DeepMimic has no velocity commands.
  ##

  cfg.commands = {}

  ##
  # Events: RSI reset + gentler pushes, DeepMimic domain randomization ranges.
  ##

  cfg.events.pop("reset_base", None)
  cfg.events.pop("reset_robot_joints", None)
  cfg.events.pop("push_robot", None)
  cfg.events["push_robot"] = EventTermCfg(
    func=velocity_mdp.push_by_setting_velocity,
    mode="interval",
    interval_range_s=(5.0, 10.0),
    params={
      "velocity_range": {
        "x": (-0.5, 0.5),
        "y": (-0.5, 0.5),
        "z": (0.0, 0.0),
        "roll": (0.0, 0.0),
        "pitch": (0.0, 0.0),
        "yaw": (0.0, 0.0),
      },
    },
  )
  if "foot_friction" in cfg.events:
    cfg.events["foot_friction"].params["ranges"] = (0.2, 1.25)
  cfg.events["init_tracking_motion"] = EventTermCfg(
    func=tracking_mdp.init_tracking_motion,
    mode="startup",
    params={"motion_dir": motion_dir},
  )
  cfg.events["reset_from_reference_motion"] = EventTermCfg(
    func=tracking_mdp.reset_from_reference_motion,
    mode="reset",
    params={
      "motion_dir": motion_dir,
      "rsi_prob": RSI_PROB,
      "asset_cfg": SceneEntityCfg("robot", joint_names=(".*",)),
    },
  )

  ##
  # Rewards: DeepMimic tracking family + regularizers.
  ##

  for name in (
    "track_linear_velocity",
    "track_angular_velocity",
    "upright",
    "pose",
    "body_ang_vel",
    "angular_momentum",
    "air_time",
    "foot_clearance",
    "foot_swing_height",
    "foot_slip",
    "soft_landing",
  ):
    cfg.rewards.pop(name, None)

  robot_cfg = SceneEntityCfg("robot")
  cfg.rewards["tracking_ref_dof_pos"] = RewardTermCfg(
    func=tracking_mdp.tracking_ref_dof_pos,
    weight=1.0,  # upstream 0.5 * 2
    params={"motion_dir": motion_dir, "std": TRACKING_DOF_POS_SIGMA, "asset_cfg": robot_cfg},
  )
  cfg.rewards["tracking_ref_dof_vel"] = RewardTermCfg(
    func=tracking_mdp.tracking_ref_dof_vel,
    weight=0.2,  # upstream 0.1 * 2
    params={"motion_dir": motion_dir, "std": TRACKING_DOF_VEL_SIGMA, "asset_cfg": robot_cfg},
  )
  cfg.rewards["tracking_ref_base_pose"] = RewardTermCfg(
    func=tracking_mdp.tracking_ref_base_pose,
    weight=1.0,  # upstream 0.5 * 2
    params={"motion_dir": motion_dir, "std": TRACKING_REF_BASE_POSE_SIGMA, "asset_cfg": robot_cfg},
  )
  cfg.rewards["tracking_ref_base_vel"] = RewardTermCfg(
    func=tracking_mdp.tracking_ref_base_vel,
    weight=0.2,  # upstream 0.1 * 2
    params={"motion_dir": motion_dir, "std": TRACKING_REF_BASE_VEL_SIGMA, "asset_cfg": robot_cfg},
  )
  cfg.rewards["tracking_ref_key_pos"] = RewardTermCfg(
    func=tracking_mdp.tracking_ref_key_pos,
    weight=0.3,  # upstream 0.15 * 2
    params={"motion_dir": motion_dir, "std": TRACKING_REF_KEY_POS_SIGMA, "asset_cfg": robot_cfg},
  )
  cfg.rewards["ang_vel_xy"] = RewardTermCfg(
    func=velocity_mdp.body_angular_velocity_penalty,
    weight=-0.05,
    params={"asset_cfg": SceneEntityCfg("robot", body_names=("pelvis",))},
  )
  cfg.rewards["joint_acc"] = RewardTermCfg(
    func=envs_mdp.joint_acc_l2,
    weight=-5.0e-8,  # upstream dof_acc
    params={"asset_cfg": robot_cfg},
  )
  cfg.rewards["dof_pos_limits"].weight = -5.0  # upstream dof_pos_limits
  cfg.rewards["action_rate_l2"].weight = -0.01

  ##
  # Terminations: fall + minimum height (upstream max_projected_gravity -0.3
  # corresponds to ~72.5 deg; keep the velocity task's 70 deg fell_over check).
  ##

  cfg.terminations["bad_base_height"] = TerminationTermCfg(
    func=envs_mdp.root_height_below_minimum,
    params={"minimum_height": 0.3},
  )
  cfg.curriculum = {}

  return cfg
