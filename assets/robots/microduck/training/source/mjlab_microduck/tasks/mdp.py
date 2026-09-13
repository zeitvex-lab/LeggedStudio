"""MDP functions for microduck tasks"""

import math
from dataclasses import dataclass as _dataclass

import numpy as np
import torch
from typing import TYPE_CHECKING, Optional
import mujoco

from mjlab.envs.manager_based_rl_env import ManagerBasedRlEnv
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.reward_manager import RewardManager as _RewardManager
from mjlab.entity import Entity
from mjlab.tasks.velocity.mdp.velocity_command import UniformVelocityCommand, UniformVelocityCommandCfg
from mjlab.tasks.velocity.mdp import observations as _velocity_obs
from mjlab.managers.command_manager import CommandTerm
from mjlab.managers import CommandTermCfg
from mjlab.managers.event_manager import requires_model_fields
from mjlab.utils.lab_api.math import matrix_from_quat, wrap_to_pi, quat_apply, quat_from_angle_axis
from rsl_rl.algorithms.ppo import PPO as _PPO

# ---------------------------------------------------------------------------
# Patch 1: RewardManager.compute — sanitize NaN rewards before they enter the
# PPO buffer.  mjlab computes rewards BEFORE resetting environments, so any
# reward term operating on a NaN physics state returns NaN.  That NaN
# propagates: NaN reward → NaN advantage → NaN loss → NaN gradient →
# NaN/negative std → crash in torch.normal on the next mini-batch.
# ---------------------------------------------------------------------------
_orig_reward_compute = _RewardManager.compute

def _nan_safe_reward_compute(self, dt: float) -> torch.Tensor:
    result = _orig_reward_compute(self, dt)
    # _episode_sums is updated inside compute() before nan_to_num can act.
    # Sanitize in-place so per-term metrics don't show NaN.
    for key in self._episode_sums:
        torch.nan_to_num_(self._episode_sums[key], nan=0.0)
    return torch.nan_to_num(result, nan=0.0)

_RewardManager.compute = _nan_safe_reward_compute

# ---------------------------------------------------------------------------
# Patch 2: PPO.compute_returns — sanitize advantages before normalization.
# At a sudden curriculum step (e.g. reward weight ×2.5) the value function is
# badly wrong: all TD errors shift by the same amount, std(advantages) → tiny,
# and (A − mean) / (std + 1e-8) → huge.  That blows up the gradient for std,
# which the optimizer then pushes below zero.  Zeroing NaN/Inf advantages
# before normalization keeps them in a safe range.
# ---------------------------------------------------------------------------
_orig_compute_returns = _PPO.compute_returns

def _safe_compute_returns(self, obs) -> None:
    _orig_compute_returns(self, obs)
    st = self.storage
    torch.nan_to_num_(st.advantages, nan=0.0, posinf=0.0, neginf=0.0)
    torch.nan_to_num_(st.returns,    nan=0.0, posinf=0.0, neginf=0.0)

_PPO.compute_returns = _safe_compute_returns

# Patch 3 (ActorCritic._update_distribution std-clamp) was REMOVED in the mjlab
# 1.3.0 migration: rsl_rl 5.0.1 refactored the policy (no ActorCritic class; the
# distribution now lives in rsl_rl.modules.distribution). It was a defensive
# band-aid against std going negative/NaN (microban runs fine without it). If
# std-blowup recurs under 1.3.0, reinstate it against the new GaussianDistribution.

print("[mdp] Patches 1-2 active: NaN-safe reward/advantage")

# ---------------------------------------------------------------------------
# Patch 4: exporter_utils.get_base_metadata — the new microduck model has
# passive joints (jaw linkage closed via equality constraints) that are part
# of the articulation but have no XML actuator.  The upstream exporter
# iterates robot.joint_names (16) and indexes joint_name_to_ctrl_id (14),
# crashing with KeyError on passive_*.  Filter passive joints out of the
# exported metadata so policies stay consistent with the 14-dim action space.
# ---------------------------------------------------------------------------
from mjlab.rl import exporter_utils as _exporter_utils  # noqa: E402
from mjlab.envs.mdp.actions import JointPositionAction as _JointAction  # noqa: E402

def _get_base_metadata_no_passive(env, run_path):
    robot = env.scene["robot"]
    joint_action = env.action_manager.get_term("joint_pos")
    assert isinstance(joint_action, _JointAction)
    full_names = list(robot.joint_names)
    keep_idx = [i for i, n in enumerate(full_names) if not n.startswith("passive_")]
    joint_names = [full_names[i] for i in keep_idx]
    joint_name_to_ctrl_id = {a.target.split("/")[-1]: a.id for a in robot.spec.actuators}
    ctrl_ids = [joint_name_to_ctrl_id[n] for n in joint_names]
    stiffness = env.sim.mj_model.actuator_gainprm[ctrl_ids, 0]
    damping = -env.sim.mj_model.actuator_biasprm[ctrl_ids, 2]
    default_jp = robot.data.default_joint_pos[0].cpu().tolist()
    return {
        "run_path": run_path,
        "joint_names": joint_names,
        "joint_stiffness": stiffness.tolist(),
        "joint_damping": damping.tolist(),
        "default_joint_pos": [default_jp[i] for i in keep_idx],
        "command_names": list(env.command_manager.active_terms),
        "observation_names": env.observation_manager.active_terms["actor"],
        "action_scale": joint_action._scale[0].cpu().tolist()
        if isinstance(joint_action._scale, torch.Tensor)
        else joint_action._scale,
    }

_exporter_utils.get_base_metadata = _get_base_metadata_no_passive
# Also patch the already-imported reference in the velocity task exporter.
try:
    from mjlab.tasks.velocity.rl import exporter as _vel_exporter  # noqa: E402
    if hasattr(_vel_exporter, "get_base_metadata"):
        _vel_exporter.get_base_metadata = _get_base_metadata_no_passive
except Exception:
    pass

print("[mdp] Patch 4 active: ONNX export filters passive_* joints")

if TYPE_CHECKING:
    from mjlab.viewer.debug_visualizer import DebugVisualizer


_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")

# Name patterns matching the 4 neck/head actuated joints. Used by head_pose
# tracking reward and by UniformPoseCommand asset hookups.
_NECK_JOINT_PATTERNS = [r".*neck_pitch.*", r".*head_pitch.*", r".*head_yaw.*", r".*head_roll.*"]


def _servo_joint_ids(env: "ManagerBasedRlEnv", asset: Entity) -> list:
    """Entity-local indices of the servo (non-``passive_``) joints, cached.

    All joint-index-based reward/event params in this module (``joint_indices``,
    ``target_overrides``, qpos-column math) are written against the canonical
    14-servo layout. On models with extra unactuated joints — backlash hinges,
    roller wheels, the jaw linkage, all named ``passive_*`` — the entity joint
    array is wider and interleaved, so raw indices would select the wrong
    joints. Index through this list to recover the servo-only view; on plain
    models it is the identity.
    """
    cache = env.__dict__.setdefault("_servo_joint_ids_cache", {})
    key = id(asset)
    ids = cache.get(key)
    if ids is None:
        ids, _ = asset.find_joints(r"^(?!passive_).*")
        cache[key] = ids
    return ids


def _servo_joint_pos(env: "ManagerBasedRlEnv", asset: Entity) -> torch.Tensor:
    return asset.data.joint_pos[:, _servo_joint_ids(env, asset)]


def _servo_joint_vel(env: "ManagerBasedRlEnv", asset: Entity) -> torch.Tensor:
    return asset.data.joint_vel[:, _servo_joint_ids(env, asset)]


def _servo_default_joint_pos(env: "ManagerBasedRlEnv", asset: Entity) -> torch.Tensor:
    return asset.data.default_joint_pos[:, _servo_joint_ids(env, asset)]


def _fallen_mask(
    env: ManagerBasedRlEnv,
    asset,
    gate_z_below: float,
    gate_tilt_above_deg: float,
) -> torch.Tensor:
    """Per-env float mask: 1.0 where the robot counts as FALLEN — trunk height
    below `gate_z_below` OR tilt beyond `gate_tilt_above_deg`. Used to gate the
    recovery rewards so they only steer while actually fallen and contribute
    exactly zero during clean walking (no walk tax / bounce farming)."""
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2], nan=0.0
    )
    quat = asset.data.root_link_quat_w
    # cos(tilt) = R22 = 1 - 2(qx² + qy²)
    cos_tilt = 1.0 - 2.0 * (quat[:, 1] ** 2 + quat[:, 2] ** 2)
    fallen = (z < gate_z_below) | (cos_tilt < math.cos(math.radians(gate_tilt_above_deg)))
    return fallen.float()


def upright_progress(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Potential-based upright shaping: Δcos(tilt) per step.

    Pays for PROGRESS toward upright, charges for progress toward fallen, and
    pays exactly ZERO for holding any pose — so no state can farm it (the gated
    state-reward it replaces was farmed from sitting, lying flat, and a
    head-tripod lean across three velstand runs). Potential-based shaping is
    policy-invariant (Ng et al.): it accelerates learning of recovery without
    creating new optima. A full prone→stand recovery collects Δ≈+1 total
    (× weight); a fall costs the same on the way down.
    """
    asset: Entity = env.scene[asset_cfg.name]
    quat = asset.data.root_link_quat_w
    cos_tilt = torch.nan_to_num(
        1.0 - 2.0 * (quat[:, 1] ** 2 + quat[:, 2] ** 2), nan=1.0
    )
    if not hasattr(env, "_upright_potential_prev"):
        env._upright_potential_prev = cos_tilt.clone()
    # Freshly reset envs: no spurious delta from the previous episode's pose.
    fresh = env.episode_length_buf <= 1
    env._upright_potential_prev[fresh] = cos_tilt[fresh]
    delta = cos_tilt - env._upright_potential_prev
    env._upright_potential_prev = cos_tilt.clone()
    return delta


def body_upright_linear(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    gate_z_below: float | None = None,
    gate_tilt_above_deg: float = 40.0,
) -> torch.Tensor:
    """Linear reward for body uprightness — provides gradient at every tilt angle.

    Returns +1 when fully upright, 0 when horizontal (prone/supine), -1 when inverted.
    Unlike flat_orientation (Gaussian), this has non-zero gradient everywhere, so the
    robot always has a signal to rotate toward upright even when starting from prone.

    Computed as the z-component of the body's local Z-axis expressed in world frame,
    which equals R[2,2] = 1 - 2*(qx² + qy²) for quaternion [w, x, y, z].
    """
    asset: Entity = env.scene[asset_cfg.name]
    quat = asset.data.root_link_quat_w  # (N, 4): [w, x, y, z]
    qx = quat[:, 1]
    qy = quat[:, 2]
    reward = 1.0 - 2.0 * (qx * qx + qy * qy)
    if gate_z_below is not None:
        # Recovery-gated variant (velstand): active only while fallen, exactly
        # zero during clean walking so it can't dilute the tracking rewards.
        reward = reward * _fallen_mask(env, asset, gate_z_below, gate_tilt_above_deg)
    return reward


def body_upright_gaussian(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    std: float = 0.1,
) -> torch.Tensor:
    """Gaussian reward on tilt magnitude — sharp pull toward fully vertical.

    Complements ``body_upright_linear`` (which is ``cos(tilt)`` and whose
    gradient ``sin(tilt)`` *vanishes* at the target). This Gaussian's
    gradient is non-zero near vertical and tapers as you move away, so it
    creates a strong differential pull in the regime where the linear
    version is weakest.

    Uses ``2*(qx² + qy²) = 1 - cos(tilt) ≈ tilt²/2`` as a tilt-squared
    proxy and applies ``exp(-tilt²/std²)``. Default std=0.1 rad ≈ 5.7°.
    """
    asset: Entity = env.scene[asset_cfg.name]
    quat = asset.data.root_link_quat_w
    qx = quat[:, 1]
    qy = quat[:, 2]
    tilt_sq = 2.0 * (qx * qx + qy * qy)  # ≈ 1 − cos(tilt); small-angle: tilt²/2
    return torch.exp(-tilt_sq / (std * std))


def body_ang_vel_at_height(
    env: ManagerBasedRlEnv,
    height_low: float,
    height_high: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    tilt_full_deg: float | None = None,
    tilt_zero_deg: float = 45.0,
) -> torch.Tensor:
    """Trunk ``sum(ω_xy²)`` penalty gated by trunk z (and optionally tilt).

    Height-gated arrival damper: zero below ``height_low`` (ground recovery —
    flips/rolls need large trunk rotation and must stay free), full above
    ``height_high``. Same formula as mjlab's body_angular_velocity_penalty
    (world-frame ω_xy, z-rotation free) but returns the gated POSITIVE cost;
    use a negative weight.

    ``tilt_full_deg`` (optional but STRONGLY recommended): additionally gate
    by tilt — full cost only when tilt ≤ tilt_full_deg, zero when
    ≥ tilt_zero_deg, smoothstep between. LESSON (2026-07 run that broke
    front-recovery): with a height gate alone, the final straighten of a
    bent-over rise (tilt 60°→0 happening INSIDE the z gate) is itself a
    large trunk rotation — taxing it builds a reward wall right before the
    finish, and the policy parks bent-over below the gate instead. With the
    tilt gate, the approach TO vertical is free; only residual wobble
    AROUND vertical (the overshoot→tip→retry oscillation) is damped.
    """
    asset = env.scene[asset_cfg.name]
    ang_vel = asset.data.body_link_ang_vel_w[:, asset_cfg.body_ids, :].squeeze(1)
    cost = torch.sum(torch.square(ang_vel[:, :2]), dim=1)
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2], nan=0.0
    )
    t = torch.clamp((z - height_low) / max(height_high - height_low, 1e-6), 0.0, 1.0)
    gate = t * t * (3.0 - 2.0 * t)
    if tilt_full_deg is not None:
        quat = asset.data.root_link_quat_w
        cos_tilt = 1.0 - 2.0 * (quat[:, 1] ** 2 + quat[:, 2] ** 2)
        tilt_deg = torch.rad2deg(torch.acos(cos_tilt.clamp(-1.0, 1.0)))
        s = torch.clamp(
            (tilt_zero_deg - tilt_deg) / max(tilt_zero_deg - tilt_full_deg, 1e-6),
            0.0,
            1.0,
        )
        gate = gate * (s * s * (3.0 - 2.0 * s))
    return cost * gate


def standing_composite_score(
    env: ManagerBasedRlEnv,
    target_height: float,
    height_std: float,
    upright_std: float,
    pose_std: float,
    joint_indices: list,
    target_overrides: Optional[dict] = None,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Smooth multiplicative goal-state score (product of three Gaussians).

    Returns ``height_score * upright_score * pose_score``, each ∈ [0, 1].
    Because the factors *multiply*, a deficiency in any one term collapses
    the whole reward — the policy can't claim 80% of this by being perfect
    on 2-of-3. Gradient is non-zero everywhere, so the score works during
    the rise (not just at the goal like a binary bonus would).

    Use to break Nash-equilibrium compromises (e.g., a "lean trunk at the
    right height" basin that satisfies the additive rewards' partial sums).
    """
    asset = env.scene[asset_cfg.name]

    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2], nan=0.0
    )
    height_score = torch.exp(-((z - target_height) / height_std) ** 2)

    quat = asset.data.root_link_quat_w
    qx = quat[:, 1]
    qy = quat[:, 2]
    tilt_sq = 2.0 * (qx * qx + qy * qy)
    upright_score = torch.exp(-tilt_sq / (upright_std * upright_std))

    target = _servo_default_joint_pos(env, asset).clone()
    if target_overrides:
        for idx, val in target_overrides.items():
            target[:, idx] = val
    joint_pos = _servo_joint_pos(env, asset)[:, joint_indices]
    target = target[:, joint_indices]
    pose_err_sq = ((joint_pos - target) ** 2).mean(dim=-1)
    pose_score = torch.exp(-pose_err_sq / (pose_std * pose_std))

    return height_score * upright_score * pose_score


def com_upward_velocity(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    max_height: float = 0.08,
    gate_z_below: float | None = None,
    gate_tilt_above_deg: float = 40.0,
    max_vz: float | None = None,
) -> torch.Tensor:
    """Reward upward CoM velocity to incentivize dynamic standup motion.

    Gated by height: only active while the CoM is below `max_height` (the
    standing target). Once standing, the reward is zero so the robot has no
    incentive to keep squatting to farm upward-velocity reward.

    ``max_vz`` (optional): cap the rewarded velocity. Uncapped, the reward is
    proportional to vz, which pays MORE per step for an explosive launch —
    a violent-rise incentive. With a cap, any rise ≥ max_vz earns the same,
    so the gentlest rise that reaches the cap is optimal (the |a_z| penalty
    then picks the smooth one). The bootstrap property is preserved: any
    upward motion still pays immediately.
    """
    asset: Entity = env.scene[asset_cfg.name]
    # nan_to_num: MuJoCo can produce NaN on contact instability; treat as z=0
    com_z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2], nan=0.0
    )
    vz = torch.nan_to_num(asset.data.root_link_lin_vel_w[:, 2], nan=0.0)
    below_target = (com_z < max_height).float()
    reward = torch.clamp(vz, min=0.0, max=max_vz) * below_target
    if gate_z_below is not None:
        # Recovery-gated (velstand): without the gate this pays for dip-and-rise
        # during gait whenever the trunk crosses max_height → bounce incentive.
        reward = reward * _fallen_mask(env, asset, gate_z_below, gate_tilt_above_deg)
    return reward


def fallen_too_long(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    gate_z_below: float = 0.10,
    gate_tilt_above_deg: float = 40.0,
    max_duration_s: float = 5.0,
) -> torch.Tensor:
    """Terminate envs that have been continuously FALLEN for `max_duration_s`.

    For envs that mix walking with fall recovery (velstand): the fell_over
    termination gets disabled by curriculum so the policy can attempt recovery,
    but without a backstop a failed recovery farms recovery-reward for the whole
    20 s episode, starving the walk of data (audit: ~25% walking share). This
    gives every fall a fair recovery window, then recycles the env.
    """
    asset: Entity = env.scene[asset_cfg.name]
    fallen = _fallen_mask(env, asset, gate_z_below, gate_tilt_above_deg).bool()
    if not hasattr(env, "_fallen_timer_s"):
        env._fallen_timer_s = torch.zeros(env.num_envs, device=env.device)
    # Freshly reset envs start with a clean timer.
    env._fallen_timer_s[env.episode_length_buf <= 1] = 0.0
    env._fallen_timer_s = torch.where(
        fallen, env._fallen_timer_s + env.step_dt, torch.zeros_like(env._fallen_timer_s)
    )
    return env._fallen_timer_s >= max_duration_s


def robot_state_is_nan(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    sensor_names: tuple[str, ...] = (),
) -> torch.Tensor:
    """Terminate environments where MuJoCo produced NaN joint positions.

    MuJoCo's contact solver can overflow to NaN under extreme penetration or
    impulse (e.g. robot landing at high velocity). A NaN simulation state
    propagates into observations, corrupting the policy network weights.

    Terminating immediately resets the environment before the cascade spreads:
    - The observation returned to the runner is from the valid reset state.
    - NaN rewards are avoided on subsequent steps.

    Note: the reward at THIS terminal step may still be NaN from the simulation;
    mjlab computes rewards before resetting (see manager_based_rl_env.py step()).
    Our custom reward functions guard against NaN internally with nan_to_num,
    but standard mjlab rewards can still be NaN here. One NaN reward is
    tolerable because done=True prevents it propagating backward through GAE.

    Couvre TOUT l'état physique, pas seulement joint_pos : la divergence du
    contact fait souvent exploser le FREE-JOINT de base (position/orientation/
    vitesse) ou les ROUES passives, pas les joints actionnés. Ces quantités
    alimentent des termes d'obs critic (base_lin_vel, base_ang_vel,
    projected_gravity, wheel_vel) ; si on ne les surveille pas, l'env ne se
    reset pas et le NaN atteint l'obs → le check_nan de rsl_rl tue tout
    l'entraînement. On teste la non-finitude (NaN ET inf, l'inf devenant NaN en
    aval lors de la normalisation de projected_gravity).
    """
    asset: Entity = env.scene[asset_cfg.name]
    d = asset.data
    bad = ~torch.isfinite(d.joint_pos).all(dim=1)
    bad |= ~torch.isfinite(d.joint_vel).all(dim=1)
    bad |= ~torch.isfinite(d.root_link_pos_w).all(dim=1)
    bad |= ~torch.isfinite(d.root_link_quat_w).all(dim=1)
    bad |= ~torch.isfinite(d.root_link_lin_vel_w).all(dim=1)
    bad |= ~torch.isfinite(d.root_link_ang_vel_w).all(dim=1)

    # Contact FORCES can blow up a step before qpos/qvel do: MuJoCo resolves a
    # degenerate contact into an inf/NaN impulse while the integrated state is
    # still finite. That force feeds the critic-only `foot_contact_forces` obs
    # (sign(F)*log1p(|F|)), which the state checks above do NOT cover — so the
    # env was not reset and the NaN reached the runner's check_nan, killing the
    # whole run (crash 2026-08-21, Velocity2-Rough-Backlash with hfield slopes).
    for name in sensor_names:
        if name not in env.scene.sensors:
            continue
        force = getattr(env.scene.sensors[name].data, "force", None)
        if force is not None:
            bad |= ~torch.isfinite(force).flatten(start_dim=1).all(dim=1)
    return bad


def is_alive(env: ManagerBasedRlEnv) -> torch.Tensor:
    """
    Reward for staying alive (not terminated)

    Args:
        env: The environment

    Returns:
        Reward tensor of shape (num_envs,) - ones for all envs
    """
    return torch.ones(env.num_envs, device=env.device)


def com_height_target(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    target_height_min: float = 0.1,
    target_height_max: float = 0.15,
) -> torch.Tensor:
    """
    Reward for keeping the center of mass within a target height range.
    Returns positive reward when in range, negative penalty when outside.

    Args:
        env: The environment
        asset_cfg: Asset configuration
        target_height_min: Minimum target height for CoM (meters)
        target_height_max: Maximum target height for CoM (meters)

    Returns:
        Reward tensor of shape (num_envs,)
    """
    asset: Entity = env.scene[asset_cfg.name]

    # Height above terrain spawn origin (world z minus terrain z).
    # env_origins[:, 2] is 0 for flat ground, so this is safe unconditionally.
    # nan_to_num: MuJoCo can produce NaN on contact instability; treat as z=0
    # so the penalty is finite (small, since 0 is near the target range).
    com_height = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2], nan=0.0
    )

    # Reward when in range, penalty when outside
    # Use smooth penalty that increases quadratically with distance from range
    below_min = com_height < target_height_min
    above_max = com_height > target_height_max
    in_range = ~(below_min | above_max)

    # Compute penalties for being outside range
    penalty_below = torch.square(com_height - target_height_min) * below_min.float()
    penalty_above = torch.square(com_height - target_height_max) * above_max.float()

    # Reward: +1 when in range, -squared_distance when outside
    reward = in_range.float() - (penalty_below + penalty_above)

    return reward


def crouch_height_target(
    phase: torch.Tensor,
    height_low: float,
    height_high: float,
    hold_lo: float = 0.375,
    hold_hi: float = 0.625,
) -> torch.Tensor:
    """Cible de hauteur du tronc « en trapèze » le long de la phase [0,1).

    phase ∈ [0, hold_lo)      : descente   height_high -> height_low
    phase ∈ [hold_lo, hold_hi): palier      height_low   (la glisse accroupie)
    phase ∈ [hold_hi, 1.0)    : remontée    height_low  -> height_high

    Args:
        phase: (B,) phase par env, dans [0, 1).
        height_low: hauteur du tronc accroupi (m).
        height_high: hauteur du tronc debout (m).
        hold_lo, hold_hi: bornes du palier bas en fraction de phase.
    Returns:
        (B,) hauteur-cible en mètres.
    """
    descend = phase < hold_lo
    hold = (phase >= hold_lo) & (phase < hold_hi)

    frac_d = phase / hold_lo
    t_descend = height_high + (height_low - height_high) * frac_d

    t_hold = torch.full_like(phase, height_low)

    frac_r = (phase - hold_hi) / (1.0 - hold_hi)
    t_rise = height_low + (height_high - height_low) * frac_r

    return torch.where(descend, t_descend, torch.where(hold, t_hold, t_rise))


def crouch_glide_reward_from_values(
    com_height: torch.Tensor,
    cmd_cos: torch.Tensor,
    cmd_sin: torch.Tensor,
    height_low: float,
    height_high: float,
    hold_lo: float = 0.375,
    hold_hi: float = 0.625,
    std: float = 0.02,
) -> torch.Tensor:
    """Récompense gaussienne du suivi de la cible de hauteur (fonction pure).

    Décode la phase depuis [cos, sin] puis compare la hauteur mesurée à la
    cible-trapèze. Retourne exp(-((h - cible)/std)^2) ∈ (0, 1].
    """
    phase = (torch.atan2(cmd_sin, cmd_cos) / (2 * torch.pi)) % 1.0
    target = crouch_height_target(phase, height_low, height_high, hold_lo, hold_hi)
    return torch.exp(-((com_height - target) / std) ** 2)


def crouch_pose_blend(
    phase: torch.Tensor,
    descent_end: float,
    hold_end: float,
    rise_end: float,
) -> torch.Tensor:
    """Blend 0..1 le long de la phase [0,1) — 0 = pose debout, 1 = pose accroupie.

    [0, descent_end)      : 0 -> 1  (se baisser)
    [descent_end, hold_end): 1      (bas / accroupi)
    [hold_end, rise_end)  : 1 -> 0  (se lever)
    [rise_end, 1.0)       : 0       (haut / debout, repos)
    """
    b = torch.zeros_like(phase)
    descend = phase < descent_end
    b = torch.where(descend, phase / descent_end, b)
    low = (phase >= descent_end) & (phase < hold_end)
    b = torch.where(low, torch.ones_like(phase), b)
    rise = (phase >= hold_end) & (phase < rise_end)
    b = torch.where(rise, 1.0 - (phase - hold_end) / (rise_end - hold_end), b)
    return b


def _crouch_pose_error(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg,
    command_name: str,
    crouch_pose: dict,
    descent_end: float,
    hold_end: float,
    rise_end: float,
    stand_pose: Optional[dict] = None,
):
    """(cur, target) joint tensors for the phase-interpolated crouch pose.

    Target interpolates per joint STAND <-> crouch_pose by the 4-segment blend
    b(phase) in [0,1] (0 = standing, 1 = crouch). STAND is `stand_pose` where
    given, else the model DEFAULT (HOME). Joints are resolved BY NAME so the
    passive-wheel interspersing on the roller robot never shifts an index.
    """
    asset: Entity = env.scene[asset_cfg.name]
    cmd = env.command_manager.get_command(command_name)
    phase = (torch.atan2(cmd[:, 1], cmd[:, 0]) / (2 * torch.pi)) % 1.0  # (B,)
    blend = crouch_pose_blend(phase, descent_end, hold_end, rise_end)   # (B,) 0..1

    names = list(crouch_pose.keys())
    ids = [int(asset.find_joints([n])[0][0]) for n in names]
    default = asset.data.default_joint_pos[:, ids]                     # (B,k)

    stand = default.clone()                                            # source pose
    if stand_pose:
        for j, n in enumerate(names):
            if n in stand_pose:
                stand[:, j] = stand_pose[n]
    crouch = torch.tensor(
        [crouch_pose[n] for n in names], device=env.device, dtype=default.dtype
    ).unsqueeze(0)                                                     # (1,k)

    target = stand + blend.unsqueeze(-1) * (crouch - stand)           # (B,k)
    cur = asset.data.joint_pos[:, ids]                                # (B,k)
    return cur, target


_NECK_JOINT_CFG = SceneEntityCfg("robot", joint_names=(r"^(?!passive_).*(neck|head).*",))
_HIP_PITCH_KNEE_CFG = SceneEntityCfg("robot", joint_names=(r"^(?!passive_).*(hip_pitch|knee).*",))
_ROLLER_FEET_SITE_CFG = SceneEntityCfg("robot", site_names=("left_foot", "right_foot"))


def feet_flat_penalty(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _ROLLER_FEET_SITE_CFG,
    sensor_name: str | None = None,
) -> torch.Tensor:
    """Penalize foot sites not being parallel to the ground.

    The foot site frame has Z+ pointing up when flat. We project a unit gravity
    vector (pointing down) into each foot site's local frame. When flat, gravity
    maps to [0,0,-1] in site frame (xy=0, penalty=0). Any tilt rotates Z away
    from world-up, giving nonzero xy components.

    Max value ≈ 2.0 per foot (foot fully sideways), total ≈ 4.0.

    When ``sensor_name`` is given, each foot's penalty is GATED by that foot's own
    ground contact: the airborne (swing) foot is free to tilt, only the stance
    blade is asked to stay flat (so its wheels keep gripping). Without this gate
    the penalty punishes the recovery-foot lift a stride needs — it is minimised
    by keeping BOTH blades flat on the ground, i.e. the swizzle. Assumes the site
    order (left, right) matches the sensor slot order (ankle_l_v1,
    ankle_r_v1) — both left-first in this model.

    Bug note: must normalize gravity PER ENV with dim=-1. Using torch.norm()
    without dim computes a scalar over all envs × 3 dims, making the vector
    ~1/sqrt(num_envs) in magnitude → penalty ~num_envs times too small.
    """
    from mjlab.utils.lab_api.math import quat_apply_inverse
    import torch.nn.functional as F

    asset: Entity = env.scene[asset_cfg.name]
    gravity_w_n = F.normalize(asset.data.gravity_vec_w, dim=-1)  # (B, 3), unit vector per env

    foot_quats = asset.data.site_quat_w[:, asset_cfg.site_ids, :]  # (B, N_feet, 4)
    per_foot = torch.zeros(env.num_envs, foot_quats.shape[1], device=env.device)
    for i in range(foot_quats.shape[1]):
        proj = quat_apply_inverse(foot_quats[:, i, :], gravity_w_n)  # (B, 3)
        per_foot[:, i] = torch.sum(torch.square(proj[:, :2]), dim=1)  # xy² only

    if sensor_name is not None:
        from mjlab.sensor import ContactSensor
        sensor: ContactSensor = env.scene[sensor_name]
        contact_time = sensor.data.current_contact_time  # (B, N_feet)
        assert contact_time is not None
        per_foot = per_foot * (contact_time > 0.0).float()

    return per_foot.sum(dim=1)


def joint_torques_l2(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG
) -> torch.Tensor:
    """
    Penalize actuator forces (torques) to encourage energy-efficient motion.

    Args:
        env: The environment
        asset_cfg: Asset configuration

    Returns:
        Penalty tensor of shape (num_envs,) - sum of squared actuator forces
    """
    asset: Entity = env.scene[asset_cfg.name]

    # Get actuator forces (scalar actuation in actuation space)
    actuator_forces = asset.data.actuator_force

    # Return L2 squared norm
    return torch.sum(torch.square(actuator_forces), dim=1)


def feet_grounded_reward(
    env: ManagerBasedRlEnv,
    sensor_name: str,
) -> torch.Tensor:
    """Positive reward for feet contacting the ground (0, +0.5, or +1.0).

    Uses the contact sensor's `found` field. For the feet_ground_contact sensor
    which has 2 primary foot geoms, `found` has shape (num_envs, 2) with per-foot
    binary contact. We sum and normalize to [0, 1].
    """
    if sensor_name not in env.scene.sensors:
        return torch.zeros(env.num_envs, device=env.device)
    sensor = env.scene.sensors[sensor_name]
    found = sensor.data.found  # (num_envs, num_feet) or (num_envs, 1)
    if found.dim() > 1:
        found = found.sum(dim=-1)  # collapse foot dimension
    return torch.clamp(found, 0.0, 2.0) / 2.0


def wheel_speed_reward(
    env: ManagerBasedRlEnv,
    command_name: str,
    wheel_radius: float = 0.0175,
    vel_scale: float = 0.5,
    bidirectional: bool = False,
) -> torch.Tensor:
    """Reward wheel spin proportional to commanded push.

    All 4 wheels spin positive for forward motion (verified visually).
    tanh saturation at vel_scale m/s equivalent prevents runaway.

    - ``bidirectional=False`` (default): forward only — reward forward spin for
      cmd_x > 0, silent otherwise (cmd_x < 0 handled by the braking reward).
    - ``bidirectional=True``: reward wheel spin in the COMMANDED direction —
      forward for cmd_x > 0, backward for cmd_x < 0 — with magnitude |cmd_x|.
      Lets cmd_x < 0 mean "go backward" instead of "brake".
    """
    cmd_x = env.command_manager.get_command(command_name)[:, 0]  # (B,)

    asset: Entity = env.scene["robot"]
    lf_ids, _ = asset.find_joints("passive_LF_?wheel")
    lr_ids, _ = asset.find_joints("passive_LR_?wheel")
    rf_ids, _ = asset.find_joints("passive_RF_?wheel")
    rr_ids, _ = asset.find_joints("passive_RR_?wheel")

    vel = asset.data.joint_vel
    # All 4 wheels spin positive for forward motion (verified by test_wheel_direction.py)
    forward_omega = (vel[:, lf_ids[0]] + vel[:, lr_ids[0]] + vel[:, rf_ids[0]] + vel[:, rr_ids[0]]) / 4.0

    omega_scale = vel_scale / wheel_radius
    if bidirectional:
        # spin aligned with the command sign (fwd for +, back for -)
        aligned = torch.sign(cmd_x) * forward_omega
        return torch.abs(cmd_x) * torch.tanh(torch.clamp(aligned, min=0.0) / omega_scale)
    return torch.clamp(cmd_x, min=0.0) * torch.tanh(torch.clamp(forward_omega, min=0.0) / omega_scale)


# ==============================================================================
# Ground Pick Rewards
# ==============================================================================

def mouth_ground_proximity(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot", site_names=["mouth_tip"]),
    std: float = 0.03,
    target_height: float = 0.0,
    command_name: str = "twist",
) -> torch.Tensor:
    """Reward for mouth tip approaching the ground, weighted by the approach phase.

    The command for the ground pick task is [cos(2π*phase), sin(2π*phase), 0].
    The approach phase is the first half-cycle (sin > 0, phase ∈ [0, 0.5]),
    smoothly weighted by max(0, sin(2π*phase)).

    Args:
        std: Gaussian std on mouth_tip height (m). 0.03 m gives strong gradient.
        target_height: Target z-height for the mouth tip (m). 0 = ground level.
    """
    asset = env.scene[asset_cfg.name]
    mouth_z = asset.data.site_pos_w[:, asset_cfg.site_ids[0], 2]  # (num_envs,)
    proximity = torch.exp(-((mouth_z - target_height) / std) ** 2)

    # Approach weight: max(0, sin(2π*phase)) — peaks at 1 at phase=0.25, zero at 0 and 0.5
    cmd = env.command_manager.get_command(command_name)
    approach_weight = torch.clamp(cmd[:, 1], min=0.0)

    return approach_weight * proximity


def mouth_perpendicular_to_ground(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot", site_names=["mouth_tip"]),
    command_name: str = "twist",
) -> torch.Tensor:
    """Reward the mouth tip x-axis being vertical (pointing down) during the approach phase.

    A perfectly perpendicular contact gives alignment=1; horizontal gives 0; pointing up gives -1.
    Weighted by max(0, sin(2π*phase)) so it only applies during the descent.
    """
    asset = env.scene[asset_cfg.name]
    # site_quat_w: (num_envs, num_sites, 4) as [w, x, y, z]
    q = asset.data.site_quat_w[:, asset_cfg.site_ids[0], :]  # (num_envs, 4)
    w, qx, qy, qz = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    # z-component of the site x-axis in world frame (first column of rotation matrix)
    x_axis_z = 2.0 * (qx * qz - w * qy)
    # dot with [0, 0, -1]: 1 = perfectly downward, -1 = upward
    alignment = -x_axis_z

    cmd = env.command_manager.get_command(command_name)
    approach_weight = torch.clamp(cmd[:, 1], min=0.0)

    return approach_weight * alignment


def sit_grounded(
    env: ManagerBasedRlEnv,
    sensor_name: str,
    command_name: Optional[str] = None,
    sin_threshold: float = 0.7,
    min_progress_frac: float = 0.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    upright_cos_threshold: float = 0.5,
) -> torch.Tensor:
    """Positive reward for trunk-ground contact WHILE upright.

    Gated additionally on the trunk's body-frame +Z axis pointing in roughly the
    world-up direction (cosine >= ``upright_cos_threshold``, default 0.5 → up to
    60° tilt accepted). Without this gate, the policy can earn the contact
    bonus by tipping sideways or face-forward — the trunk hits the ground in
    those weird poses, sit_grounded fires, and the policy converges to a
    "fallen" mode that competes with the actual sit pose.

    When ``command_name`` is provided, the reward is gated to the sit window of
    a phase command. Otherwise it's always-on, optionally gated to the late
    part of the episode via ``min_progress_frac``.
    """
    if sensor_name not in env.scene.sensors:
        return torch.zeros(env.num_envs, device=env.device)
    sensor = env.scene.sensors[sensor_name]
    found = sensor.data.found
    if found.dim() > 1:
        found = found.sum(dim=-1)
    has_contact = (found > 0).float()

    # Upright check: trunk body's +Z (world frame, third column of rotation matrix
    # derived from the trunk quaternion) dot world-up = trunk's body-up · world-up.
    # Equivalently: 1 - 2*(qx² + qy²) for a unit quaternion (w, x, y, z).
    asset: Entity = env.scene[asset_cfg.name]
    quat = asset.data.root_link_quat_w  # (N, 4) = (w, x, y, z)
    qx, qy = quat[:, 1], quat[:, 2]
    upright_cos = 1.0 - 2.0 * (qx * qx + qy * qy)
    is_upright = (upright_cos >= upright_cos_threshold).float()

    contact_upright = has_contact * is_upright

    if command_name is None:
        if min_progress_frac > 0.0:
            progress = env.episode_length_buf.float() / float(env.max_episode_length)
            late_enough = (progress >= min_progress_frac).float()
            return late_enough * contact_upright
        return contact_upright
    cmd = env.command_manager.get_command(command_name)
    in_sit_window = (cmd[:, 1] > sin_threshold).float()
    return in_sit_window * contact_upright


def pose_target_match(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    std: float = 0.3,
    joint_indices: Optional[list] = None,
    target_overrides: Optional[dict] = None,
) -> torch.Tensor:
    """Always-on Gaussian on joint positions vs a target pose.

    Non-phase analog of ``phase_pose_match``: useful for episodic tasks (e.g.
    the sit env) where there's no cyclic command to weight the reward by, and
    the target pose is constant for the whole episode.

    Args:
        std: Gaussian std per joint (rad).
        joint_indices: Optional subset of joints to evaluate.
        target_overrides: ``{joint_index: angle_rad}``. Joints not listed default
            to ``asset.data.default_joint_pos`` (the home/standing pose).
    """
    asset = env.scene[asset_cfg.name]
    joint_pos = _servo_joint_pos(env, asset)
    target = _servo_default_joint_pos(env, asset).clone()
    if target_overrides:
        for idx, val in target_overrides.items():
            target[:, idx] = val
    if joint_indices is not None:
        joint_pos = joint_pos[:, joint_indices]
        target = target[:, joint_indices]
    return torch.exp(-((joint_pos - target) / std) ** 2).mean(dim=-1)


def interpolated_pose_target_match(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    std: float = 0.3,
    joint_indices: Optional[list] = None,
    source_overrides: Optional[dict] = None,
    target_overrides: Optional[dict] = None,
    ramp_start_frac: float = 0.0,
    ramp_end_frac: float = 1.0,
) -> torch.Tensor:
    """Gaussian on joint positions vs a time-interpolated target pose.

    Tracks a target that linearly interpolates from a source pose to a target
    pose over the episode, between progress fractions ``ramp_start_frac`` and
    ``ramp_end_frac``. Before/after the ramp the target is clamped to source /
    final target respectively.

    The point is to enforce smooth descent: snapping to the final target early
    leaves the robot *off-target* relative to where the interpolated target
    currently is, costing pose reward for the duration of the mismatch.

    Args:
        std: Gaussian std per joint (rad).
        joint_indices: Optional subset of joints to evaluate.
        source_overrides: ``{joint_index: angle_rad}`` defining the source pose
            (start of the ramp). ``None`` = default/HOME pose.
        target_overrides: same, for the target pose (end of the ramp).
        ramp_start_frac, ramp_end_frac: episode-progress window in [0, 1] over
            which the target moves from source to target.
    """
    asset = env.scene[asset_cfg.name]
    joint_pos = _servo_joint_pos(env, asset)
    source = _servo_default_joint_pos(env, asset).clone()
    target = _servo_default_joint_pos(env, asset).clone()
    if source_overrides:
        for idx, val in source_overrides.items():
            source[:, idx] = val
    if target_overrides:
        for idx, val in target_overrides.items():
            target[:, idx] = val

    progress = env.episode_length_buf.float() / float(env.max_episode_length)
    span = max(ramp_end_frac - ramp_start_frac, 1e-6)
    tau = ((progress - ramp_start_frac) / span).clamp(0.0, 1.0).unsqueeze(-1)
    interp = source * (1.0 - tau) + target * tau

    if joint_indices is not None:
        joint_pos = joint_pos[:, joint_indices]
        interp = interp[:, joint_indices]
    return torch.exp(-((joint_pos - interp) / std) ** 2).mean(dim=-1)


def interpolated_pose_l1_penalty(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    joint_indices: Optional[list] = None,
    source_overrides: Optional[dict] = None,
    target_overrides: Optional[dict] = None,
    ramp_start_frac: float = 0.0,
    ramp_end_frac: float = 1.0,
) -> torch.Tensor:
    """L1 distance from a time-interpolated target pose (negative — used as penalty).

    Same interpolation schedule as ``interpolated_pose_target_match`` but
    returns ``-mean(|joint_pos - interp|)`` instead of a Gaussian. The L1
    gradient is constant everywhere — useful as a bootstrap signal when the
    Gaussian variant saturates to zero far from target and leaves the policy
    no gradient to discover the target direction.
    """
    asset = env.scene[asset_cfg.name]
    joint_pos = _servo_joint_pos(env, asset)
    source = _servo_default_joint_pos(env, asset).clone()
    target = _servo_default_joint_pos(env, asset).clone()
    if source_overrides:
        for idx, val in source_overrides.items():
            source[:, idx] = val
    if target_overrides:
        for idx, val in target_overrides.items():
            target[:, idx] = val

    progress = env.episode_length_buf.float() / float(env.max_episode_length)
    span = max(ramp_end_frac - ramp_start_frac, 1e-6)
    tau = ((progress - ramp_start_frac) / span).clamp(0.0, 1.0).unsqueeze(-1)
    interp = source * (1.0 - tau) + target * tau

    if joint_indices is not None:
        joint_pos = joint_pos[:, joint_indices]
        interp = interp[:, joint_indices]
    return -torch.abs(joint_pos - interp).mean(dim=-1)


def interpolated_height_target(
    env: ManagerBasedRlEnv,
    start_height: float,
    end_height: float,
    std: float = 0.02,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    ramp_start_frac: float = 0.0,
    ramp_end_frac: float = 1.0,
) -> torch.Tensor:
    """Gaussian on trunk z vs a time-interpolated target height.

    Companion to ``interpolated_pose_target_match`` — same time-interpolation
    logic applied to the trunk height.
    """
    progress = env.episode_length_buf.float() / float(env.max_episode_length)
    span = max(ramp_end_frac - ramp_start_frac, 1e-6)
    tau = ((progress - ramp_start_frac) / span).clamp(0.0, 1.0)
    target_z = start_height * (1.0 - tau) + end_height * tau

    asset = env.scene[asset_cfg.name]
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2], nan=0.0
    )
    return torch.exp(-((z - target_z) / std) ** 2)


def _multistage_target_pose(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg,
    waypoints,
) -> torch.Tensor:
    """Compute the time-interpolated joint target across N waypoints.

    waypoints: ordered list of dicts {"frac": float in [0,1],
                                       "overrides": dict[int,float] | None}.
    First waypoint should have frac=0.0 (typically HOME, overrides=None).
    Subsequent waypoints define milestones. Between two waypoints the target
    linearly interpolates. Before the first / after the last it clamps.

    Returns a (num_envs, num_joints) tensor of target joint angles.
    """
    asset = env.scene[asset_cfg.name]
    default = _servo_default_joint_pos(env, asset)

    def build_pose(overrides):
        pose = default.clone()
        if overrides:
            for idx, val in overrides.items():
                pose[:, idx] = val
        return pose

    progress = env.episode_length_buf.float() / float(env.max_episode_length)
    # Find which segment we're in (broadcast over envs).
    out = build_pose(waypoints[0]["overrides"])
    for i in range(1, len(waypoints)):
        f0 = waypoints[i - 1]["frac"]
        f1 = waypoints[i]["frac"]
        span = max(f1 - f0, 1e-6)
        tau = ((progress - f0) / span).clamp(0.0, 1.0).unsqueeze(-1)
        prev_pose = build_pose(waypoints[i - 1]["overrides"])
        next_pose = build_pose(waypoints[i]["overrides"])
        seg = prev_pose * (1.0 - tau) + next_pose * tau
        # Take this segment's value when progress is in [f0, f1] or past it.
        mask = (progress >= f0).float().unsqueeze(-1)
        out = torch.where(mask > 0, seg, out)
    return out


def _multistage_target_height(
    env: ManagerBasedRlEnv,
    waypoints,
) -> torch.Tensor:
    """Same logic as _multistage_target_pose but for trunk z height.

    waypoints: [{"frac": float, "height": float}, ...].
    """
    progress = env.episode_length_buf.float() / float(env.max_episode_length)
    out = torch.full_like(progress, waypoints[0]["height"])
    for i in range(1, len(waypoints)):
        f0 = waypoints[i - 1]["frac"]
        f1 = waypoints[i]["frac"]
        span = max(f1 - f0, 1e-6)
        tau = ((progress - f0) / span).clamp(0.0, 1.0)
        seg = waypoints[i - 1]["height"] * (1.0 - tau) + waypoints[i]["height"] * tau
        mask = (progress >= f0).float()
        out = torch.where(mask > 0, seg, out)
    return out


def multistage_pose_target_match(
    env: ManagerBasedRlEnv,
    waypoints: list,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    std: float = 0.3,
    joint_indices: Optional[list] = None,
) -> torch.Tensor:
    """Multi-waypoint variant of interpolated_pose_target_match.

    waypoints: [{"frac": 0.0, "overrides": None},
                {"frac": 0.4, "overrides": FOLD_OVERRIDES},
                {"frac": 0.7, "overrides": SIT_OVERRIDES}]

    Use this to enforce a curriculum-style trajectory through one or more
    intermediate poses (e.g. stand → fold → sit). Same per-joint Gaussian
    semantics as the single-stage version.
    """
    asset = env.scene[asset_cfg.name]
    target = _multistage_target_pose(env, asset_cfg, waypoints)
    joint_pos = _servo_joint_pos(env, asset)
    if joint_indices is not None:
        joint_pos = joint_pos[:, joint_indices]
        target = target[:, joint_indices]
    return torch.exp(-((joint_pos - target) / std) ** 2).mean(dim=-1)


def multistage_height_target(
    env: ManagerBasedRlEnv,
    waypoints: list,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    std: float = 0.03,
) -> torch.Tensor:
    """Multi-waypoint Gaussian on trunk z."""
    target_z = _multistage_target_height(env, waypoints)
    asset = env.scene[asset_cfg.name]
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2], nan=0.0
    )
    return torch.exp(-((z - target_z) / std) ** 2)


def pose_target_match(
    env: ManagerBasedRlEnv,
    target_overrides: Optional[dict] = None,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    std: float = 0.3,
    joint_indices: Optional[list] = None,
) -> torch.Tensor:
    """Gaussian pose-match against a single fixed target.

    target = ``default_joint_pos`` with the per-index overrides applied. No
    waypoints, no episode-progress interpolation — the same target is rewarded
    from t=0 to the end of the episode.
    """
    asset = env.scene[asset_cfg.name]
    target = _servo_default_joint_pos(env, asset).clone()
    if target_overrides:
        for idx, val in target_overrides.items():
            target[:, idx] = val
    joint_pos = _servo_joint_pos(env, asset)
    if joint_indices is not None:
        joint_pos = joint_pos[:, joint_indices]
        target = target[:, joint_indices]
    return torch.exp(-((joint_pos - target) / std) ** 2).mean(dim=-1)


def height_target_gaussian(
    env: ManagerBasedRlEnv,
    target_height: float,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    std: float = 0.02,
) -> torch.Tensor:
    """Gaussian on trunk z against a single fixed target."""
    asset = env.scene[asset_cfg.name]
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2], nan=0.0
    )
    return torch.exp(-((z - target_height) / std) ** 2)


def trunk_vertical_accel_penalty(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Penalty proportional to ``|a_z|`` of the trunk (finite-diff of v_z).

    Captures hard impacts (large deceleration spike on landing) AND incentivises
    a smooth quasi-static descent (constant velocity → a_z ≈ 0). At rest a_z is
    zero so the seated robot pays no cost.

    State is kept on the env in ``_prev_trunk_vz``; at episode reset the
    accel is zeroed to avoid a transient from the previous episode's final
    state leaking into the new one.
    """
    asset = env.scene[asset_cfg.name]
    vz = torch.nan_to_num(asset.data.root_link_lin_vel_w[:, 2], nan=0.0)
    prev = getattr(env, "_prev_trunk_vz", None)
    if prev is None or prev.shape[0] != vz.shape[0]:
        prev = vz.detach().clone()
    a_z = (vz - prev) / env.step_dt
    # Zero out a_z at reset steps to suppress the cross-episode transient.
    if hasattr(env, "episode_length_buf"):
        reset_mask = env.episode_length_buf <= 1
        a_z = torch.where(reset_mask, torch.zeros_like(a_z), a_z)
    env._prev_trunk_vz = vz.detach().clone()
    return -torch.abs(a_z)


def trunk_downward_velocity_penalty(
    env: ManagerBasedRlEnv,
    max_down_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Penalty on downward trunk velocity beyond ``max_down_vel``.

    Caps descent SPEED, which ``trunk_vertical_accel_penalty`` alone cannot:
    a fast constant-velocity drop has a_z ≈ 0 the whole way down and pays only
    one impact spike at the bottom — cheap relative to arriving at the target
    pose sooner. This term makes every step of a too-fast descent cost reward,
    so the gentlest descent that stays under the cap is optimal. Zero at rest
    and for any motion slower than the cap (including all upward motion).
    """
    asset = env.scene[asset_cfg.name]
    vz = torch.nan_to_num(asset.data.root_link_lin_vel_w[:, 2], nan=0.0)
    return -torch.clamp(-vz - max_down_vel, min=0.0)


def seated_stillness(
    env: ManagerBasedRlEnv,
    height_full: float = 0.06,
    height_zero: float = 0.08,
    vel_std: float = 0.05,
    tilt_full_deg: float = 25.0,
    tilt_zero_deg: float = 60.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Reward trunk stillness while seated UPRIGHT: |v| Gaussian, z- and tilt-gated.

    exp(-(|v|/vel_std)²) · smoothstep(z) · smoothstep(tilt). The z gate is full
    below ``height_full`` and zero above ``height_zero`` (inactive during the
    descent). The tilt gate is full below ``tilt_full_deg`` and zero above
    ``tilt_zero_deg`` — WITHOUT it, "lie still on your back" scores as well as
    "sit still upright" (the trunk on its back is inside the seated z band and
    perfectly motionless), which is exactly the exploit run 2 converged to.
    Makes "rest quietly, upright, at the seated height" the only rewarded rest.
    """
    asset = env.scene[asset_cfg.name]
    v = torch.nan_to_num(asset.data.root_link_lin_vel_w, nan=0.0).norm(dim=-1)
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2], nan=0.0
    )
    t = torch.clamp((height_zero - z) / max(height_zero - height_full, 1e-6), 0.0, 1.0)
    z_gate = t * t * (3.0 - 2.0 * t)
    quat = asset.data.root_link_quat_w
    cos_tilt = 1.0 - 2.0 * (quat[:, 1] ** 2 + quat[:, 2] ** 2)
    cos_full = math.cos(math.radians(tilt_full_deg))
    cos_zero = math.cos(math.radians(tilt_zero_deg))
    u = torch.clamp((cos_tilt - cos_zero) / max(cos_full - cos_zero, 1e-6), 0.0, 1.0)
    tilt_gate = u * u * (3.0 - 2.0 * u)
    return torch.exp(-((v / vel_std) ** 2)) * z_gate * tilt_gate


def phase_pose_blend(
    phase: torch.Tensor,
    descent_end: float,
    hold_end: float,
    rise_end: float,
) -> torch.Tensor:
    """Blend 0..1 le long de la phase [0,1) — 0 = pose STAND, 1 = pose DOWN.

    [0, descent_end)       : 0 -> 1  (se baisser)
    [descent_end, hold_end): 1       (bas)
    [hold_end, rise_end)   : 1 -> 0  (se lever)
    [rise_end, 1.0)        : 0       (haut / repos)
    """
    b = torch.zeros_like(phase)
    descend = phase < descent_end
    b = torch.where(descend, phase / descent_end, b)
    low = (phase >= descent_end) & (phase < hold_end)
    b = torch.where(low, torch.ones_like(phase), b)
    rise = (phase >= hold_end) & (phase < rise_end)
    b = torch.where(rise, 1.0 - (phase - hold_end) / (rise_end - hold_end), b)
    return b


def kick_pose_target(
    phase: torch.Tensor,
    stand: torch.Tensor,
    back: torch.Tensor,
    forward: torch.Tensor,
    windup_end: float,
    kick_end: float,
    return_end: float,
) -> torch.Tensor:
    """Cible articulaire interpolée d'un geste de shoot à 4 keyframes.

    phase (B,) ∈ [0,1). stand/back/forward (k,) ou (1,k). Retour (B,k).

    [0, windup_end)        STAND   -> BACK     (armement)
    [windup_end, kick_end) BACK    -> FORWARD  (frappe sèche)
    [kick_end, return_end) FORWARD -> STAND    (retour)
    [return_end, 1.0)      STAND             (repos)
    """
    p = phase.unsqueeze(-1)  # (B,1)

    def interp(a, b, s):
        return a + s * (b - a)

    s1 = (p / windup_end).clamp(0.0, 1.0)
    s2 = ((p - windup_end) / (kick_end - windup_end)).clamp(0.0, 1.0)
    s3 = ((p - kick_end) / (return_end - kick_end)).clamp(0.0, 1.0)

    seg1 = interp(stand, back, s1)
    seg2 = interp(back, forward, s2)
    seg3 = interp(forward, stand, s3)  # à s3=1 (phase>=return_end) => STAND

    out = seg1
    out = torch.where(p >= windup_end, seg2, out)
    out = torch.where(p >= kick_end, seg3, out)
    return out


def _kick_pose_error(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg,
    command_name: str,
    stand_pose: dict,
    back_pose: dict,
    forward_pose: dict,
    windup_end: float,
    kick_end: float,
    return_end: float,
    joint_names: Optional[list] = None,
):
    """(cur, target) pour le geste de shoot, joints résolus PAR NOM.

    Les 3 poses partagent les mêmes clés (14 joints). L'ordre des noms est
    donné par `stand_pose` (ou par `joint_names` si fourni — un sous-ensemble
    des clés, ex. jambe droite + cou d'un côté, jambe gauche de l'autre, pour
    appliquer des std différents au geste vs à la jambe d'appui).
    """
    if not stand_pose:
        raise ValueError("_kick_pose_error requires a non-empty stand_pose dict")
    asset: Entity = env.scene[asset_cfg.name]
    names = list(joint_names) if joint_names is not None else list(stand_pose.keys())
    ids = [int(asset.find_joints([n])[0][0]) for n in names]

    def vec(d):
        return torch.tensor([d[n] for n in names], device=env.device,
                            dtype=asset.data.joint_pos.dtype)

    stand_v, back_v, fwd_v = vec(stand_pose), vec(back_pose), vec(forward_pose)

    cmd = env.command_manager.get_command(command_name)
    phase = (torch.atan2(cmd[:, 1], cmd[:, 0]) / (2 * torch.pi)) % 1.0  # (B,)
    target = kick_pose_target(phase, stand_v, back_v, fwd_v,
                              windup_end, kick_end, return_end)          # (B,k)
    cur = asset.data.joint_pos[:, ids]                                   # (B,k)
    return cur, target


def kick_engagement(
    phase: torch.Tensor,
    windup_end: float,
    return_end: float,
) -> torch.Tensor:
    """Gate d'engagement du geste ∈ [0,1] (pur) — pour pondérer les rewards
    d'équilibre unipède qui ne doivent s'appliquer que hors du repos STAND.

    [0, windup_end)        : 0 -> 1  (montée pendant l'armement)
    [windup_end, return_end): 1       (phase de frappe = appui unipède attendu)
    [return_end, 1.0)      : 0        (repos STAND, appui bipède, CoM centré OK)
    """
    g = torch.zeros_like(phase)
    ramp = phase < windup_end
    g = torch.where(ramp, phase / windup_end, g)
    hold = (phase >= windup_end) & (phase < return_end)
    g = torch.where(hold, torch.ones_like(phase), g)
    return g


def _phase_pose_error(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg,
    command_name: str,
    target_pose: dict,
    descent_end: float,
    hold_end: float,
    rise_end: float,
    source_pose: Optional[dict] = None,
):
    """(cur, target) pour la pose interpolée par la phase, résolue PAR NOM.

    Cible = source + blend(phase)·(target_pose - source), source = STAND
    (`source_pose` si fourni, sinon le DEFAULT/HOME du modèle). blend ∈ [0,1]
    (0 = STAND, 1 = target_pose) via `phase_pose_blend`.
    """
    if not target_pose:
        raise ValueError("_phase_pose_error requires a non-empty target_pose dict")

    asset: Entity = env.scene[asset_cfg.name]
    cmd = env.command_manager.get_command(command_name)
    phase = (torch.atan2(cmd[:, 1], cmd[:, 0]) / (2 * torch.pi)) % 1.0  # (B,)
    blend = phase_pose_blend(phase, descent_end, hold_end, rise_end)     # (B,)

    names = list(target_pose.keys())
    ids = [int(asset.find_joints([n])[0][0]) for n in names]
    default = asset.data.default_joint_pos[:, ids]                       # (B,k)

    source = default.clone()
    if source_pose:
        for j, n in enumerate(names):
            if n in source_pose:
                source[:, j] = source_pose[n]
    target_vec = torch.tensor(
        [target_pose[n] for n in names], device=env.device, dtype=default.dtype
    ).unsqueeze(0)                                                       # (1,k)

    target = source + blend.unsqueeze(-1) * (target_vec - source)        # (B,k)
    cur = asset.data.joint_pos[:, ids]                                   # (B,k)
    return cur, target


def phase_pose_match(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    std: float = 0.3,
    command_name: str = "twist",
    joint_indices: Optional[list] = None,
    target_overrides: Optional[dict] = None,
    phase: str = "approach",
) -> torch.Tensor:
    """Reward matching a target pose, weighted by phase-cycle command.

    Generic helper for phase-conditioned tasks (e.g. sit/stand). The command
    encodes phase as [cos(2π·phase), sin(2π·phase), 0]:
      - "approach" weight = max(0, sin(2π·phase)) — peaks at phase 0.25.
      - "return"   weight = max(0,-sin(2π·phase)) — peaks at phase 0.75.

    Args:
        std: Gaussian std per joint (rad).
        joint_indices: Optional subset of joints to evaluate (rest ignored).
        target_overrides: {joint_index: angle_rad}. Joints not listed default
            to asset.data.default_joint_pos (the home/standing pose).
        phase: "approach" or "return".
    """
    asset = env.scene[asset_cfg.name]
    joint_pos = _servo_joint_pos(env, asset)
    target = _servo_default_joint_pos(env, asset).clone()
    if target_overrides:
        for idx, val in target_overrides.items():
            target[:, idx] = val
    if joint_indices is not None:
        joint_pos = joint_pos[:, joint_indices]
        target = target[:, joint_indices]
    pose_reward = torch.exp(-((joint_pos - target) / std) ** 2).mean(dim=-1)

    cmd = env.command_manager.get_command(command_name)
    if phase == "approach":
        weight = torch.clamp(cmd[:, 1], min=0.0)
    else:
        weight = torch.clamp(-cmd[:, 1], min=0.0)
    return weight * pose_reward


def ground_pick_return_pose(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    std: float = 0.3,
    command_name: str = "twist",
    joint_indices: Optional[list] = None,
) -> torch.Tensor:
    """Reward for returning to the standing pose after ground pick, weighted by the return phase.

    The return phase is the second half-cycle (sin < 0, phase ∈ [0.5, 1.0]),
    smoothly weighted by max(0, -sin(2π*phase)).

    Args:
        std: Gaussian std per joint (rad).
        joint_indices: Subset of joints to evaluate. Use to apply different stds
            to leg joints vs neck/head joints (call this reward twice).
    """
    asset = env.scene[asset_cfg.name]
    joint_pos  = _servo_joint_pos(env, asset)        # (num_envs, n_servo_joints)
    default_pos = _servo_default_joint_pos(env, asset)

    if joint_indices is not None:
        joint_pos   = joint_pos[:, joint_indices]
        default_pos = default_pos[:, joint_indices]

    pose_reward = torch.exp(-((joint_pos - default_pos) / std) ** 2).mean(dim=-1)

    # Return weight: max(0, -sin(2π*phase)) — peaks at 1 at phase=0.75, zero at 0.5 and 1
    cmd = env.command_manager.get_command(command_name)
    return_weight = torch.clamp(-cmd[:, 1], min=0.0)

    return return_weight * pose_reward


def ground_pick_return_upright(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    std: float = 0.4,
    command_name: str = "twist",
) -> torch.Tensor:
    """Reward trunk verticality, weighted by the RETURN phase (stand-up aid).

    Same return weighting as ``ground_pick_return_pose`` (``max(0, -sin(2π·phase))``)
    so it only rewards being upright during the stand-up, never fighting the
    forward lean of the approach. Verticality = ``exp(-tilt²/std²)`` with the same
    tilt proxy as ``body_upright_gaussian`` (``2*(qx²+qy²) ≈ 1-cos(tilt)``). A broad
    std (0.4 rad ≈ 23°) gives gradient even from a fairly tilted crouch.
    """
    asset: Entity = env.scene[asset_cfg.name]
    quat = asset.data.root_link_quat_w
    tilt_sq = 2.0 * (quat[:, 1] ** 2 + quat[:, 2] ** 2)  # qx² + qy²
    upright = torch.exp(-tilt_sq / (std * std))
    cmd = env.command_manager.get_command(command_name)
    return_weight = torch.clamp(-cmd[:, 1], min=0.0)
    return return_weight * upright


# --------------------------------------------------------------------------- #
# Ground-pick : gating de phase SEGMENTÉ (durées descente/palier/remontée/repos #
# indépendantes, au lieu de la pondération sinusoïdale max(0,±sin)).            #
#   down-gate  = phase_pose_blend(phase, descent_end, hold_end, rise_end)       #
#               0 (haut) -> 1 (descente) -> 1 (palier bas) -> 0 (remontée/repos) #
#   up-gate    = phase_rise_gate(phase, hold_end, rise_end)                      #
#               0 avant la remontée -> 0..1 (remontée) -> 1 (repos debout)       #
# --------------------------------------------------------------------------- #
def phase_rise_gate(
    phase: torch.Tensor, hold_end: float, rise_end: float
) -> torch.Tensor:
    """Gate montante pour le RETOUR : 0 avant hold_end, 0->1 sur [hold_end,
    rise_end), 1 après (repos debout)."""
    g = torch.zeros_like(phase)
    rising = (phase >= hold_end) & (phase < rise_end)
    g = torch.where(rising, (phase - hold_end) / (rise_end - hold_end), g)
    g = torch.where(phase >= rise_end, torch.ones_like(phase), g)
    return g


def _gp_phase(env: ManagerBasedRlEnv, command_name: str) -> torch.Tensor:
    cmd = env.command_manager.get_command(command_name)
    return (torch.atan2(cmd[:, 1], cmd[:, 0]) / (2 * torch.pi)) % 1.0


def apply_mouth_payload_force(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg(
        "robot", body_names=["jaw_soft"], site_names=["mouth_tip"]
    ),
    command_name: str = "twist",
    hold_end: float = 0.35,
    ramp: float = 0.05,
    gravity: float = 9.81,
) -> torch.Tensor:
    """Hook par-step (utilisé comme reward de poids 0) : applique le POIDS de
    l'objet tenu dans la bouche comme force externe verticale au mouth_tip, gaté
    sur la remontée (phase >= hold_end, rampe rapide au moment du 'grab').

    Émule une masse ponctuelle au bout de la bouche pendant le relever : la force
    m·g est appliquée au CoM du corps + le couple (p_mouth - p_com) × F, ce qui
    équivaut à l'appliquer au mouth_tip (bon bras de levier pour le cou). Retourne
    0 (ce n'est pas une vraie récompense — juste le hook d'application)."""
    asset: Entity = env.scene[asset_cfg.name]
    payload = getattr(env, "_mouth_payload_kg", None)
    if payload is None:
        return torch.zeros(env.num_envs, device=env.device)
    phase = _gp_phase(env, command_name)
    gate = ((phase - hold_end) / ramp).clamp(0.0, 1.0)  # 0 avant grab -> 1 après
    fz = -(gate * payload) * gravity                     # (N,) force verticale (bas)

    bid = int(asset_cfg.body_ids[0])
    sid = int(asset_cfg.site_ids[0])
    p_mouth = asset.data.site_pos_w[:, sid, :]           # (N,3)
    p_com = asset.data.body_com_pos_w[:, bid, :]         # (N,3)
    F = torch.zeros((env.num_envs, 3), device=env.device, dtype=p_mouth.dtype)
    F[:, 2] = fz
    tau = torch.cross(p_mouth - p_com, F, dim=-1)        # applique F au mouth_tip
    asset.write_external_wrench_to_sim(
        forces=F.unsqueeze(1), torques=tau.unsqueeze(1), body_ids=[bid],
    )
    return torch.zeros(env.num_envs, device=env.device)


# ==============================================================================
# Domain Randomization Events
# ==============================================================================


def randomize_mass_and_inertia(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    scale_range: tuple[float, float],
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
):
    """Randomize body mass and inertia together with the same scaling factor.

    This maintains physical consistency - mass and inertia must scale together
    to avoid creating invalid inertia tensors that cause simulation instability.

    Args:
        env: The environment
        env_ids: Environment IDs to randomize
        scale_range: (min, max) scaling factor applied to both mass and inertia
        asset_cfg: Asset configuration specifying which bodies to randomize
    """
    if env_ids is None:
        env_ids = torch.arange(env.num_envs, device=env.device, dtype=torch.int)
    else:
        env_ids = env_ids.to(env.device, dtype=torch.int)

    asset: Entity = env.scene[asset_cfg.name]

    # Get body indices
    body_ids = asset_cfg.body_ids
    if isinstance(body_ids, slice):
        body_ids = list(range(asset.num_bodies))[body_ids]
    body_indices = asset.indexing.body_ids[body_ids]

    # Sample ONE random scale per environment (applied to both mass and inertia)
    num_envs = len(env_ids)
    num_bodies = len(body_indices)
    scales = torch.rand(num_envs, num_bodies, device=env.device) * (scale_range[1] - scale_range[0]) + scale_range[0]

    # Store original values on first call
    if not hasattr(env, '_original_mass_inertia'):
        env._original_mass_inertia = {
            'mass': env.sim.model.body_mass[0, body_indices].clone(),
            'inertia': env.sim.model.body_inertia[0, body_indices].clone(),
        }

    # Reset to original first (to prevent accumulation)
    original = env._original_mass_inertia
    env.sim.model.body_mass[env_ids[:, None], body_indices] = original['mass'].unsqueeze(0).expand(num_envs, -1)
    env.sim.model.body_inertia[env_ids[:, None], body_indices] = original['inertia'].unsqueeze(0).expand(num_envs, -1, -1)

    # Apply same scale to both mass and inertia
    env.sim.model.body_mass[env_ids[:, None], body_indices] *= scales
    env.sim.model.body_inertia[env_ids[:, None], body_indices] *= scales.unsqueeze(-1)  # Scale all 3 inertia components


def reward_weight(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    reward_name: str,
    weight_stages: list[dict],
) -> torch.Tensor:
    """Step-staged reward weight curriculum.

    mjlab 1.3.0 dropped the built-in ``mdp.reward_weight`` helper, so microduck
    provides its own. ``weight_stages`` is a list of ``{"step": int, "weight":
    float}`` dicts; the weight of the latest stage whose step has elapsed is
    applied. Mutates the live RewardManager term cfg (not env.cfg, which is a
    deepcopy at manager init).
    """
    del env_ids
    term_cfg = env.reward_manager.get_term_cfg(reward_name)
    for stage in weight_stages:
        if env.common_step_counter > stage["step"]:
            term_cfg.weight = stage["weight"]
    return torch.tensor([term_cfg.weight])


def slope_move_masks(distance: "torch.Tensor", size_x: float):
    """Masques de promotion/rétrogradation du curriculum de pente.

    move_up   : a parcouru plus de 40% de la tuile → il a dévalé la rampe,
                on la rend plus raide. Aligné sur la termination
                terrain_edge_reached (~3.8 m, threshold_fraction=0.95 par
                défaut sur size_x=8.0), qui termine l'épisode avant le seuil
                de moitié (4.0 m) — sans cet alignement un traverseur réussi
                n'est jamais promu.
    move_down : a à peine avancé (< 20% de la tuile) → chute/blocage précoce,
                on adoucit la rampe.
    """
    move_up = distance > size_x * 0.4
    move_down = (distance < size_x * 0.2) & (~move_up)
    return move_up, move_down


def projected_gravity(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Projected gravity vector in body frame.

    Returns the gravity vector projected into the robot's body frame,
    representing pure orientation without linear acceleration.
    This is simpler than raw accelerometer and only depends on orientation.

    Returns:
        torch.Tensor: Projected gravity in body frame (num_envs, 3)
    """
    asset: Entity = env.scene[asset_cfg.name]
    return asset.data.projected_gravity_b


def _imu_misalignment_quat(env: ManagerBasedRlEnv, max_angle_rad: float) -> torch.Tensor:
    """Per-env constant IMU mounting-misalignment rotation (sampled once).

    Models a fixed small mounting/calibration error of the IMU on each robot.
    Sampled lazily on first use and cached — constant per env for the whole run
    (like a startup randomization), so it's a *systematic per-robot bias*, not
    per-step noise. Replaces the old randomize_imu_orientation event, which wrote
    site_quat (not per-env expanded under mjlab 1.3.0, and not read by the
    projected_gravity / base_ang_vel observations anyway).

    Returns a (num_envs, 4) unit quaternion (w, x, y, z).
    """
    q = getattr(env, "_imu_misalign_quat", None)
    if q is None:
        n = env.num_envs
        axis = torch.randn(n, 3, device=env.device)
        axis = axis / (torch.norm(axis, dim=-1, keepdim=True) + 1e-8)
        angle = torch.rand(n, device=env.device) * max_angle_rad  # [0, max]
        q = quat_from_angle_axis(angle, axis)
        env._imu_misalign_quat = q
    return q


def randomize_imu_orientation(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    max_angle_deg: float = 2.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
):
    """Randomize IMU sensor mounting orientation by small angles.
    
    Simulates slight mounting errors or calibration offsets in the real robot.
    The IMU orientation is randomized by rotating around random axes by up to max_angle_deg.
    
    Args:
        env: The environment
        env_ids: Environment IDs to randomize
        max_angle_deg: Maximum rotation angle in degrees (default 2.0°)
        asset_cfg: Asset configuration
    """
    if env_ids is None:
        env_ids = torch.arange(env.num_envs, device=env.device, dtype=torch.int)
    else:
        env_ids = env_ids.to(env.device, dtype=torch.int)
    
    asset: Entity = env.scene[asset_cfg.name]

    # IMU site is the first site (index 0) in robot.xml
    # Sites: imu (0), left_foot (1), right_foot (2)
    site_id = 0
    
    # Store original orientation on first call
    if not hasattr(env, '_original_imu_quat'):
        env._original_imu_quat = env.sim.model.site_quat[0, site_id].clone()
    
    # Generate random rotations for each environment
    num_envs = len(env_ids)
    max_angle_rad = max_angle_deg * torch.pi / 180.0
    
    # Random rotation angles [-max_angle, +max_angle] for each axis
    angles = (torch.rand(num_envs, 3, device=env.device) * 2 - 1) * max_angle_rad
    
    # Convert Euler angles to quaternions (small angle approximation for efficiency)
    # For small angles: quat ≈ [1, θx/2, θy/2, θz/2]
    half_angles = angles / 2.0
    quats_delta = torch.zeros(num_envs, 4, device=env.device)
    quats_delta[:, 0] = 1.0  # w component
    quats_delta[:, 1:] = half_angles  # x, y, z components
    
    # Normalize the quaternion
    quats_delta = quats_delta / torch.norm(quats_delta, dim=1, keepdim=True)
    
    # Get original quaternion and apply delta rotation
    original_quat = env._original_imu_quat.unsqueeze(0).expand(num_envs, -1)
    
    # Quaternion multiplication: q_new = q_delta * q_original
    # q1 * q2 = [w1*w2 - dot(v1,v2), w1*v2 + w2*v1 + cross(v1,v2)]
    w1, x1, y1, z1 = quats_delta[:, 0], quats_delta[:, 1], quats_delta[:, 2], quats_delta[:, 3]
    w2, x2, y2, z2 = original_quat[:, 0], original_quat[:, 1], original_quat[:, 2], original_quat[:, 3]
    
    new_quat = torch.stack([
        w1*w2 - x1*x2 - y1*y2 - z1*z2,  # w
        w1*x2 + x1*w2 + y1*z2 - z1*y2,  # x
        w1*y2 - x1*z2 + y1*w2 + z1*x2,  # y
        w1*z2 + x1*y2 - y1*x2 + z1*w2,  # z
    ], dim=1)
    
    # Apply to the selected environments
    env.sim.model.site_quat[env_ids, site_id] = new_quat


def set_random_prone_orientation(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    face_down_prob: float = 0.5,
):
    """Randomly initialize each env as face-down (belly) or face-up (back), with random yaw.

    Face-down:  +90° pitch → quat = [s*cy, -s*sy,  s*cy,  s*sy]
    Face-up:    -90° pitch → quat = [s*cy,  s*sy, -s*cy,  s*sy]

    Args:
        face_down_prob: probability of sampling face-down (vs face-up). A curriculum
            can ramp this from a high initial value (easier task) toward 0.5.
    """
    if env_ids is None or len(env_ids) == 0:
        return
    env_ids = env_ids.to(env.device, dtype=torch.int)
    num = len(env_ids)

    yaw = torch.rand(num, device=env.device) * 2 * np.pi - np.pi
    cy = torch.cos(yaw * 0.5)
    sy = torch.sin(yaw * 0.5)
    s = 2.0 ** -0.5  # sqrt(2)/2

    face_down = torch.stack([ s * cy, -s * sy,  s * cy,  s * sy], dim=1)
    face_up   = torch.stack([ s * cy,  s * sy, -s * cy,  s * sy], dim=1)

    mask = torch.rand(num, device=env.device) < face_down_prob  # True → face-down
    new_quat = torch.where(mask.unsqueeze(1), face_down, face_up)

    env.sim.data.qpos[env_ids, 3:7] = new_quat
    env.sim.data.qvel[env_ids, :6] = 0.0


def set_random_ground_state(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    face_down_prob: float = 0.4,
    face_up_prob: float = 0.4,
    sitting_prob: float = 0.2,
    standing_prob: float = 0.0,
    prone_z_min: float = 0.20,
    prone_z_max: float = 0.25,
    sitting_z_min: float = 0.07,
    sitting_z_max: float = 0.09,
    standing_z_min: float = 0.11,
    standing_z_max: float = 0.12,
    sitting_joint_overrides: Optional[dict] = None,
    sitting_joint_noise_std: float = 0.0,
    sitting_tilt_max: float = 0.0,
    face_up_roll_max: float = 0.0,
):
    """Reset to a random ground state: face-down, face-up, sitting, or standing.

    Broader than ``set_random_prone_orientation`` — used by the stand-up env so
    the policy learns to recover from any plausible pose, including the sitting
    keyframe (rest state of the sit policy) and an already-standing pose (so it
    also learns to *hold* a stand, not only to rise).

    Modes (probabilities are normalized; they need not sum to 1.0):
      - face-down (belly to floor): +90° pitch, random yaw, z in [prone_z_min, prone_z_max].
      - face-up   (back to floor):  -90° pitch, random yaw, z in [prone_z_min, prone_z_max].
      - sitting:                    upright (±sitting_tilt_max), random yaw, z low,
                                    joints set to ``sitting_joint_overrides``.
      - standing:                   upright (±sitting_tilt_max), random yaw, z in
                                    [standing_z_min, standing_z_max], joints left at
                                    HOME (whatever ``reset_robot_joints`` set).

    Args:
        sitting_joint_overrides: ``{qpos_joint_index: angle_rad}`` to write into
            ``qpos[7+idx]`` for envs sampled into the sitting bucket. ``None``
            keeps joints at whatever ``reset_robot_joints`` already set.
    """
    if env_ids is None or len(env_ids) == 0:
        return
    env_ids = env_ids.to(env.device, dtype=torch.int)
    num = len(env_ids)

    total = face_down_prob + face_up_prob + sitting_prob + standing_prob
    p_fd  = face_down_prob / total
    p_fu  = (face_down_prob + face_up_prob) / total
    p_sit = (face_down_prob + face_up_prob + sitting_prob) / total

    yaw = torch.rand(num, device=env.device) * 2 * np.pi - np.pi
    cy = torch.cos(yaw * 0.5)
    sy = torch.sin(yaw * 0.5)
    s = 2.0 ** -0.5  # sqrt(2)/2

    face_down = torch.stack([ s * cy, -s * sy,  s * cy,  s * sy], dim=1)
    face_up   = torch.stack([ s * cy,  s * sy, -s * cy,  s * sy], dim=1)
    # Upright sitting: yaw-only by default, with optional ±sitting_tilt_max
    # pitch/roll noise so the policy doesn't overfit to perfectly-upright starts.
    if sitting_tilt_max > 0.0:
        pitch = (torch.rand(num, device=env.device) * 2 - 1) * sitting_tilt_max
        roll  = (torch.rand(num, device=env.device) * 2 - 1) * sitting_tilt_max
        cp = torch.cos(pitch * 0.5); sp = torch.sin(pitch * 0.5)
        cr = torch.cos(roll  * 0.5); sr = torch.sin(roll  * 0.5)
        # ZYX intrinsic Euler → quaternion (yaw * pitch * roll).
        sit_w = cr * cp * cy + sr * sp * sy
        sit_x = sr * cp * cy - cr * sp * sy
        sit_y = cr * sp * cy + sr * cp * sy
        sit_z = cr * cp * sy - sr * sp * cy
        sitting = torch.stack([sit_w, sit_x, sit_y, sit_z], dim=1)
    else:
        sitting = torch.stack([cy, torch.zeros_like(cy), torch.zeros_like(cy), sy], dim=1)

    u = torch.rand(num, device=env.device)
    is_fd    = u < p_fd
    is_fu    = (u >= p_fd) & (u < p_fu)
    is_sit   = (u >= p_fu) & (u < p_sit)
    is_stand = u >= p_sit

    # Face-up partial-roll noise: rotate the supine pose about the body's long
    # axis by uniform ±face_up_roll_max. WHY (2026-07, back-recovery was
    # seed-lucky): the reward landscape between supine and prone is FLAT —
    # upright_linear (cos tilt) is ≈0 through the whole roll, height doesn't
    # change — so rolling off the back only pays via the front-rise path that
    # follows, a long-horizon dependency that noisy exploration rarely finds
    # from a perfectly flat supine start. With roll noise, a fraction of
    # face-up spawns start near-on-side (partway along the roll): the policy
    # learns roll-completion from easy starts and generalizes back to flat
    # supine — a built-in reverse curriculum. Uniform sampling keeps every
    # difficulty represented (flat back |roll|<15° ≈ 17% at ±90°), so no
    # annealing schedule is needed, and varied post-fall poses are realistic
    # DR for deployment anyway.
    if face_up_roll_max > 0.0:
        theta = (torch.rand(num, device=env.device) * 2 - 1) * face_up_roll_max
        ct = torch.cos(theta * 0.5)
        st = torch.sin(theta * 0.5)
        # Log-roll = rotation about the body's LONG axis, which is body z (the
        # spine: trunk z is up when standing → horizontal when lying). NOT body
        # x — supine leaves body x pointing skyward, so an x-roll would only
        # spin the robot in place like the yaw noise already does.
        # Body-frame rotation → right-multiply: q_fu ⊗ [ct, 0, 0, st].
        w, x, y, z = face_up[:, 0], face_up[:, 1], face_up[:, 2], face_up[:, 3]
        face_up = torch.stack(
            [
                w * ct - z * st,
                x * ct + y * st,
                y * ct - x * st,
                w * st + z * ct,
            ],
            dim=1,
        )

    # Sitting and standing share the same upright orientation (identity + optional
    # ±sitting_tilt_max); they differ only in trunk height and joint pose.
    new_quat = face_down.clone()
    new_quat[is_fu]    = face_up[is_fu]
    new_quat[is_sit]   = sitting[is_sit]
    new_quat[is_stand] = sitting[is_stand]

    # Random z per env: prone heights for face-down/up, low for sit, ~standing for stand.
    z_prone = torch.rand(num, device=env.device) * (prone_z_max - prone_z_min) + prone_z_min
    z_sit   = torch.rand(num, device=env.device) * (sitting_z_max - sitting_z_min) + sitting_z_min
    z_stand = torch.rand(num, device=env.device) * (standing_z_max - standing_z_min) + standing_z_min
    new_z = z_prone.clone()
    new_z = torch.where(is_sit, z_sit, new_z)
    new_z = torch.where(is_stand, z_stand, new_z)

    env.sim.data.qpos[env_ids, 2]   = new_z
    env.sim.data.qpos[env_ids, 3:7] = new_quat
    env.sim.data.qvel[env_ids, :6]  = 0.0

    # Sitting-bucket joint overrides (e.g. knee/ankle bent to keyframe).
    # Override keys are SERVO indices (14-joint layout); translate to entity
    # joint indices so models with interleaved passive_* joints (backlash)
    # write the intended joints. qpos column = 7 + entity joint index
    # (robot free joint first, all hinges 1-dof).
    asset: Entity = env.scene[asset_cfg.name]
    servo_ids = _servo_joint_ids(env, asset)
    if sitting_joint_overrides:
        sit_env_ids = env_ids[is_sit]
        if len(sit_env_ids) > 0:
            for jnt_idx, angle in sitting_joint_overrides.items():
                env.sim.data.qpos[sit_env_ids, 7 + servo_ids[jnt_idx]] = angle

    # Joint noise for sitting envs: Gaussian noise on every actuated joint
    # so the policy sees a distribution of plausible "sit" starts rather than
    # a single canonical pose. Captures real-world transfer where the robot's
    # joint angles won't match the SIT keyframe exactly when the standup
    # policy takes over from the sit policy.
    if sitting_joint_noise_std > 0.0:
        sit_env_ids = env_ids[is_sit]
        if len(sit_env_ids) > 0:
            # Servo joints only: passive_* joints (backlash hinges) have tiny
            # ranges and must stay at 0 on reset.
            n_sit = len(sit_env_ids)
            cols = torch.tensor([7 + j for j in servo_ids], device=env.device, dtype=torch.long)
            noise = torch.randn(n_sit, len(cols), device=env.device) * sitting_joint_noise_std
            env.sim.data.qpos[sit_env_ids.unsqueeze(1).long(), cols.unsqueeze(0)] += noise


# Deep-crouch anchor pose (velstand run-5): the "stuck" mid-recovery basin —
# knees folded under the body, trunk pitched forward, feet flat. Values chosen
# by extending the HOME zig-zag (hip fwd / knee back / ankle fwd, sign
# conventions per the SIT keyframe fold directions) to deep flexion, inside
# the ±1.57 joint limits. hip_yaw/hip_roll/neck stay at HOME.
_CROUCH_ANCHOR_BY_NAME = {
    "left_hip_pitch": -1.15,
    "left_knee": 1.25,
    "left_ankle": 1.05,
    "right_hip_pitch": 1.15,
    "right_knee": -1.25,
    "right_ankle": -1.05,
}


def set_random_crouch_state(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    depth_min: float = 0.35,
    depth_max: float = 1.0,
    pitch_max_deg: float = 55.0,
    joint_noise: float = 0.12,
    z_stand: float = 0.115,
    z_deep: float = 0.06,
):
    """Reset selected envs into a random mid-recovery crouch.

    Reverse curriculum for the recovery last mile (velstand run-5 lesson):
    prone-init episodes spend most of their fallen budget getting TO the deep
    crouch and are recycled shortly after reaching it, so the crouch→stand
    mile gets almost no on-policy data — the policy converged to parking
    there. Seeding resets ACROSS that mile (depth λ ∈ [depth_min, depth_max]
    between standing and the deep-crouch anchor, trunk pitch and z scaled
    with λ) makes the frontier dense from step 0 of the episode.
    """
    if env_ids is None or len(env_ids) == 0:
        return
    env_ids = env_ids.to(env.device, dtype=torch.long)
    num = len(env_ids)
    asset: Entity = env.scene[asset_cfg.name]

    lam = torch.rand(num, device=env.device) * (depth_max - depth_min) + depth_min

    # Joints: lerp HOME → anchor on the leg pitch chain, uniform noise on the
    # servo joints only (passive_* backlash hinges have ±1° ranges — noise
    # there would spawn them pinned outside their limits).
    joints = asset.data.default_joint_pos[env_ids].clone()
    for name, anchor in _CROUCH_ANCHOR_BY_NAME.items():
        ids, _ = asset.find_joints(f"^{name}$")
        j = ids[0]
        joints[:, j] = joints[:, j] + lam * (anchor - joints[:, j])
    noise_mask = torch.zeros(joints.shape[1], device=joints.device)
    noise_mask[_servo_joint_ids(env, asset)] = 1.0
    joints += (torch.rand_like(joints) * 2 - 1) * joint_noise * noise_mask

    # Base orientation: forward pitch scaled with depth (the stuck basin is a
    # forward crouch from both fall directions), random yaw, small roll noise.
    pitch = lam * math.radians(pitch_max_deg) \
        + (torch.rand(num, device=env.device) * 2 - 1) * math.radians(10.0)
    pitch = torch.clamp(pitch, min=math.radians(5.0))
    roll = (torch.rand(num, device=env.device) * 2 - 1) * math.radians(8.0)
    yaw = torch.rand(num, device=env.device) * 2 * np.pi - np.pi
    cy = torch.cos(yaw * 0.5); sy = torch.sin(yaw * 0.5)
    cp = torch.cos(pitch * 0.5); sp = torch.sin(pitch * 0.5)
    cr = torch.cos(roll * 0.5); sr = torch.sin(roll * 0.5)
    # ZYX intrinsic Euler → quaternion (yaw * pitch * roll), as in
    # set_random_ground_state's sitting branch.
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    quat = torch.stack([qw, qx, qy, qz], dim=1)

    # Trunk height scaled with depth, small upward margin to settle cleanly.
    z = z_stand + lam * (z_deep - z_stand) \
        + torch.rand(num, device=env.device) * 0.01

    env.sim.data.qpos[env_ids, 2] = z
    env.sim.data.qpos[env_ids, 3:7] = quat
    env.sim.data.qpos[env_ids, 7:] = joints
    env.sim.data.qvel[env_ids, :] = 0.0


class VelocityCommandCommandOnly(UniformVelocityCommand):
    """Like UniformVelocityCommand but only draws the command arrows (no actual velocity arrows)."""

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        super()._resample_command(env_ids)
        # Turn-in-place practice: for a fraction of envs, zero the linear velocity
        # and force a meaningful (away-from-zero) yaw command. Independent uniform
        # sampling almost never produces "lin≈0, |ang| large" (~2% of samples), so
        # spinning on the spot was effectively untrained → slow/unstable real-robot
        # turning. Mirrors the base rel_forward_envs mechanism.
        p = getattr(self.cfg, "rel_turn_in_place_envs", 0.0)
        if p <= 0.0:
            return
        r = torch.empty(len(env_ids), device=self.device)
        turn_ids = env_ids[r.uniform_(0.0, 1.0) < p]
        if len(turn_ids) == 0:
            return
        self.vel_command_b[turn_ids, 0] = 0.0
        self.vel_command_b[turn_ids, 1] = 0.0
        lo, hi = self.cfg.ranges.ang_vel_z
        maxr = max(abs(lo), abs(hi))
        rr = torch.empty(len(turn_ids), device=self.device)
        sign = torch.where(rr.uniform_(0.0, 1.0) < 0.5, -1.0, 1.0)
        mag = torch.empty(len(turn_ids), device=self.device).uniform_(0.4 * maxr, maxr)
        self.vel_command_b[turn_ids, 2] = sign * mag
        # These envs must actually turn — un-mark them as standing (which would
        # zero the command) and refresh the world-frame reference copy.
        self.is_standing_env[turn_ids] = False
        self.vel_command_w[turn_ids] = self.vel_command_b[turn_ids]

    def _debug_vis_impl(self, visualizer: "DebugVisualizer") -> None:
        batch = visualizer.env_idx
        if batch >= self.num_envs:
            return

        cmds = self.command.cpu().numpy()
        base_pos_ws = self.robot.data.root_link_pos_w.cpu().numpy()
        base_quat_w = self.robot.data.root_link_quat_w
        base_mat_ws = matrix_from_quat(base_quat_w).cpu().numpy()

        base_pos_w = base_pos_ws[batch]
        base_mat_w = base_mat_ws[batch]
        cmd = cmds[batch]

        if np.linalg.norm(base_pos_w) < 1e-6:
            return

        def local_to_world(vec: np.ndarray) -> np.ndarray:
            return base_pos_w + base_mat_w @ vec

        scale = self.cfg.viz.scale * 2.0
        z_offset = self.cfg.viz.z_offset

        # Command linear velocity arrow (blue).
        cmd_lin_from = local_to_world(np.array([0, 0, z_offset]) * scale)
        cmd_lin_to = local_to_world(
            (np.array([0, 0, z_offset]) + np.array([cmd[0], cmd[1], 0])) * scale
        )
        visualizer.add_arrow(cmd_lin_from, cmd_lin_to, color=(0.2, 0.2, 0.6, 0.6), width=0.015)


class RelativeHeadingVelocityCommand(VelocityCommandCommandOnly):
    """Velocity command where cmd[2] is the heading error in the robot's body frame.

    cmd[0] = lin_vel_x  (throttle: 0=coast, +push, -brake)
    cmd[1] = lin_vel_y  (unused, 0)
    cmd[2] = heading_error  (+ = target is to the right/CW, - = to the left/CCW)
             0 → go straight, ±max = target is max_angle rad to the right/left

    During training: a random world-frame heading is sampled at each episode reset.
    At every step, cmd[2] = clamp(wrap(current_yaw - target_yaw), ±max_angle).
    Positive when the robot is pointing CCW (left) of the target → needs to turn right.

    At inference: the user feeds cmd[2] directly.  Holding cmd[2] = constant gives
    a proportional heading correction = approximately constant turn rate.

    Set heading_command=False and rel_heading_envs=0.0 in the cfg (we handle
    heading internally).  ang_vel_z range in cfg is used as the clip limit for cmd[2].
    """

    def __init__(self, cfg, env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        # Sampled target heading per env, world frame (rad)
        self._target_heading_w = torch.zeros(self.num_envs, device=self.device)
        # Clip limit for cmd[2]: use ang_vel_z[1] from cfg (the positive bound)
        ang_rng = cfg.ranges.ang_vel_z
        self._heading_max = float(ang_rng[1]) if ang_rng else 1.0

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        super()._resample_command(env_ids)
        n = len(env_ids)
        # Sample random world-frame target heading uniformly in [-π, π]
        self._target_heading_w[env_ids] = (
            torch.rand(n, device=self.device) * 2.0 * math.pi - math.pi
        )
        # Zero ang_vel slot; _update_command will fill it each step
        self.vel_command_b[env_ids, 2] = 0.0

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        # Do NOT call super()._update_command() — it would run the heading
        # proportional controller and overwrite cmd[2] with a yaw rate.
        # Instead recompute heading error from scratch each step.
        quat = self.robot.data.root_link_quat_w  # (N, 4) [w, x, y, z]
        w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
        current_yaw = torch.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
        # Positive = target is CCW (left) of robot → turn left. Standard convention.
        delta = self._target_heading_w - current_yaw
        heading_error = torch.atan2(torch.sin(delta), torch.cos(delta))
        self.vel_command_b[:, 2] = heading_error.clamp(-self._heading_max, self._heading_max)

    def _update_metrics(self) -> None:
        pass  # No velocity tracking metrics for heading command


def _forward_progress_gate(env: ManagerBasedRlEnv, v_ref: float) -> torch.Tensor | None:
    """0→1 ramp in body forward speed: 0 when standing still, 1 at/above v_ref.

    Used to gate stride-shaping rewards so that stepping which does NOT propel
    the body (e.g. tap-dancing on the spot) earns nothing — the reward for the
    FORM of a stride is only paid when the stride actually does its JOB (moving
    forward). Returns None when disabled (v_ref <= 0)."""
    if v_ref <= 0.0:
        return None
    v_fwd = env.scene["robot"].data.root_link_lin_vel_b[:, 0]
    return (v_fwd.clamp(min=0.0) / v_ref).clamp(max=1.0)


def single_support_reward(
    env: ManagerBasedRlEnv,
    sensor_name: str,
    command_name: str,
    vel_gate_ref: float = 0.0,
    double_penalty: float = 0.25,
) -> torch.Tensor:
    """Reward single-support (a skating stride), mildly discourage the swizzle.

    Real skating is a STRIDE: push off one blade while the other swings, i.e.
    single support that alternates left/right. A symmetric swizzle keeps BOTH
    blades grounded the whole time and still spins the wheels, so wheel_speed
    alone converges to it.

    Per step, counting blades in contact:
      - exactly 1 blade down (stride)  → + clamp(cmd_x,0) · gate
      - 2 blades down    (double supp) → − double_penalty · clamp(cmd_x,0)
      - 0 blades down    (flight/hop)  →  0

    The POSITIVE single-support reward is gated by forward speed (``vel_gate_ref``)
    so stepping in place (no propulsion) earns nothing — kills the tap-dance hack.
    The double-support penalty is small and UNGATED: brief double support during
    weight transfer / push-off is NORMAL skating, so we only lightly discourage
    PERMANENT double support (the swizzle) rather than forbid it. The real
    anti-swizzle signal is skating_air_time — the swizzle never lifts a foot.
    """
    from mjlab.sensor import ContactSensor
    sensor: ContactSensor = env.scene[sensor_name]
    contact_time = sensor.data.current_contact_time  # (num_envs, num_feet)
    assert contact_time is not None

    n_contact = torch.sum((contact_time > 0.0).float(), dim=1)  # (num_envs,)
    single = (n_contact == 1).float()
    double = (n_contact >= 2).float()

    cmd_x = torch.clamp(env.command_manager.get_command(command_name)[:, 0], min=0.0)
    single_r = single * cmd_x
    gate = _forward_progress_gate(env, vel_gate_ref)
    if gate is not None:
        single_r = single_r * gate
    return single_r - double_penalty * double * cmd_x


def leg_symmetry_reward(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    joint_bases: tuple = ("hip_yaw", "hip_roll", "hip_pitch", "knee", "ankle"),
) -> torch.Tensor:
    """Reward left/right legs mirroring — the swizzle's defining symmetry.

    The robot uses mirrored L/R sign conventions, so a bilaterally-symmetric config
    satisfies q_left + q_right ≈ 0 per matched joint pair. Returns
    ``-mean_pairs |q_left + q_right|`` (L1, constant gradient); use with a POSITIVE
    weight so asymmetry is penalised and the symmetric swizzle is favoured. L/R index
    pairs are resolved once by name and cached on env.
    """
    asset: Entity = env.scene[asset_cfg.name]
    if not hasattr(env, "_leg_sym_ids"):
        left, right = [], []
        for base in joint_bases:
            li, _ = asset.find_joints([f"left_{base}"])
            ri, _ = asset.find_joints([f"right_{base}"])
            left.append(li[0])
            right.append(ri[0])
        env._leg_sym_ids = (
            torch.tensor(left, device=env.device),
            torch.tensor(right, device=env.device),
        )
    lids, rids = env._leg_sym_ids
    q = asset.data.joint_pos
    return -torch.abs(q[:, lids] + q[:, rids]).mean(dim=-1)


def grounded_reward(
    env: ManagerBasedRlEnv,
    sensor_name: str,
    command_name: str,
) -> torch.Tensor:
    """Reward BOTH blades in contact — a classic swizzle stays grounded (no lifting).

    Mirror of single_support_reward but rewarding double support (n_contact >= 2),
    scaled by |cmd_x| so it shapes the push phase in EITHER direction (forward or
    backward — the swizzle env drives cmd_x < 0 as "go backward").
    """
    from mjlab.sensor import ContactSensor
    sensor: ContactSensor = env.scene[sensor_name]
    contact_time = sensor.data.current_contact_time  # (num_envs, num_feet)
    assert contact_time is not None
    n_contact = torch.sum((contact_time > 0.0).float(), dim=1)
    grounded = (n_contact >= 2).float()
    cmd_x = torch.abs(env.command_manager.get_command(command_name)[:, 0])
    return grounded * cmd_x


class GroundPickPhaseCommand(UniformVelocityCommand):
    """Phase-encoding command for the ground pick / sit-stand tasks.

    Replaces the velocity command with a cyclic phase signal:
        command = [cos(2π*phase), sin(2π*phase), 0]

    Phase ∈ [0, 0.5]: approach (go down).
    Phase ∈ [0.5, 1.0]: return (come back up).

    Phase is randomized per environment on episode reset to decorrelate envs.
    Period defaults to 4s; override via the cfg.period field (sitstand uses 8s
    for a slower, gentler sit-down).
    """

    PERIOD: float = 4.0  # default; cfg.period overrides

    def __init__(self, cfg, env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self._gp_phase = torch.zeros(self.num_envs, device=self.device)
        self._period = float(getattr(cfg, "period", self.PERIOD))
        # When False, each episode starts at phase 0 (standing) instead of a
        # random phase. Matches the runtime, where the button starts the cycle
        # at phase 0 from standing. Default True keeps the historical ground_pick
        # behavior (random phase to decorrelate envs).
        self._randomize_phase = bool(getattr(cfg, "randomize_phase", True))

    @property
    def command(self) -> torch.Tensor:
        return self.vel_command_b

    def compute(self, dt: float, env_ids=None) -> None:
        self._gp_phase = (self._gp_phase + dt / self._period) % 1.0
        self.vel_command_b[:, 0] = torch.cos(2 * torch.pi * self._gp_phase)
        self.vel_command_b[:, 1] = torch.sin(2 * torch.pi * self._gp_phase)
        self.vel_command_b[:, 2] = 0.0

    def reset(self, env_ids: torch.Tensor | None) -> dict:
        if env_ids is not None and len(env_ids) > 0:
            if self._randomize_phase:
                self._gp_phase[env_ids] = torch.rand(len(env_ids), device=self.device)
            else:
                self._gp_phase[env_ids] = 0.0
        return {}

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        pass  # Phase is continuous; no resampling needed

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        pass  # Updated in compute()

    def _update_metrics(self) -> None:
        pass  # No velocity tracking metrics for ground pick


from dataclasses import dataclass as _dataclass



# --------------------------------------------------------------------------- #
# Unified pose command machinery                                               #
# --------------------------------------------------------------------------- #
#
# Background: we deprecated the old NeckOffsetJointPositionAction +
# disturbance-randomization approach (where head/body movement was an external
# perturbation the policy was supposed to be robust to). That trained a weak,
# indirect signal — see `project_neck_offset_decoupling.md` for the
# post-mortem.
#
# Replacement: head and body pose are now *commands* — direct, dense policy
# inputs with tracking rewards. At deployment, the runtime feeds those slots
# with whatever pose the user requests; at training, they're sampled uniformly
# from per-dim ranges (kept non-zero from step 0 so input neurons stay alive)
# and ramped via curriculum.
#
# Layout, unified across all microduck policies for runtime obs compatibility:
#   command vector (13D) = [vx, vy, vtheta,           ← "twist" (velocity)
#                           neck_pitch, head_pitch,   ← "head_pose" (deltas)
#                           head_yaw, head_roll,
#                           body_x, body_y, body_z,   ← "body_pose" (deltas)
#                           body_roll, body_pitch, body_yaw]
# Total policy obs becomes 61D (51 - 3 + 13).
# --------------------------------------------------------------------------- #


from dataclasses import dataclass, field


class UniformPoseCommand(CommandTerm):
    """Generic N-dim uniform pose command.

    Samples each dim independently uniform in cfg.ranges[i] = (lo, hi) and holds
    the value between resamples. No metrics, no debug viz — keep it lightweight
    since we have many of these.
    """

    cfg: "UniformPoseCommandCfg"

    def __init__(self, cfg: "UniformPoseCommandCfg", env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self.dim = len(cfg.ranges)
        self._command = torch.zeros(self.num_envs, self.dim, device=self.device)

    @property
    def command(self) -> torch.Tensor:
        return self._command

    def _update_metrics(self) -> None:
        pass

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        pass

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        n = len(env_ids)
        if n == 0:
            return
        r = torch.empty(n, device=self.device)
        for i, (lo, hi) in enumerate(self.cfg.ranges):
            self._command[env_ids, i] = r.uniform_(lo, hi)
        # Explicit zero-command bucket. Uniform sampling essentially never
        # produces the all-zero command, so the deployment idle case ("hold the
        # nominal pose") would otherwise be absent from training (velocity
        # body-control run-1 lesson: the policy only stood still when a command
        # was present).
        if self.cfg.zero_command_prob > 0.0:
            zero_mask = torch.rand(n, device=self.device) < self.cfg.zero_command_prob
            self._command[env_ids[zero_mask]] = 0.0


@dataclass(kw_only=True)
class UniformPoseCommandCfg(CommandTermCfg):
    """Per-dim uniform ranges; builds a UniformPoseCommand."""
    # Tuple of (lo, hi) per dim. Length defines the command dim.
    ranges: tuple[tuple[float, float], ...] = ()
    # Probability that a resample yields the exact all-zero command.
    zero_command_prob: float = 0.0

    def build(self, env: ManagerBasedRlEnv) -> "UniformPoseCommand":
        return UniformPoseCommand(self, env)


def head_pose_tracking(
    env: ManagerBasedRlEnv,
    command_name: str = "head_pose",
    std: float = 0.5,
    fine_std: float | None = None,
    fine_weight: float = 0.5,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Per-joint Gaussian reward for matching commanded neck/head deltas.

    Mean over the 4 neck/head joints of exp(-(err/std)^2). Result is (N,) in
    [0, 1]. Mean form (vs sum-of-squares) keeps gradient alive when only one
    joint is off — vs SOS where a single big error kills the whole reward.

    `std` is the per-joint tolerance: at err=std the per-joint reward is 1/e
    (~0.37). Pick std on the order of the command range so the gradient
    doesn't die as the curriculum widens.

    `fine_std` (optional) blends in a second, narrow Gaussian:
    (1-fine_weight)·exp(-(err/std)²) + fine_weight·exp(-(err/fine_std)²).
    Rationale: a single wide std (0.5 rad ≈ 29°) makes small errors nearly
    free — a 10° gravity sag on the heavy head costs ~0.03 reward, so the
    policy lets it droop. The narrow component (~0.1 rad) prices those small
    errors while the wide one keeps gradient alive at far commands during
    curriculum widening.

    cmd has shape (N, 4) = deltas from default joint positions in the order
    [neck_pitch, head_pitch, head_yaw, head_roll].

    On backlash models the measured angle is qpos[servo] + qpos[backlash] —
    the OUTPUT link, which is also what the encoder obs
    (joint_pos_rel_backlash) reports. Measuring the servo alone would let the
    head droop the backlash play reward-free AND penalize the policy for
    compensating it (servo biased up = servo-side "error"). On models without
    passive_*_backlash joints the mask is 0 and this reduces to the servo.
    """
    asset: Entity = env.scene[asset_cfg.name]
    cmd = env.command_manager.get_command(command_name)  # (N, 4)

    if not hasattr(env, "_head_pose_neck_ids"):
        ids, names = asset.find_joints_by_actuator_names(_NECK_JOINT_PATTERNS)
        env._head_pose_neck_ids = torch.tensor(ids, device=env.device, dtype=torch.long)
        name_to_id = {n: i for i, n in enumerate(asset.joint_names)}
        bl = [name_to_id.get(f"passive_{n}_backlash") for n in names]
        env._head_pose_bl_ids = torch.tensor(
            [0 if b is None else b for b in bl], device=env.device, dtype=torch.long
        )
        env._head_pose_bl_mask = torch.tensor(
            [0.0 if b is None else 1.0 for b in bl], device=env.device
        )

    neck_ids = env._head_pose_neck_ids
    joint_pos = asset.data.joint_pos
    measured = (
        joint_pos[:, neck_ids]
        + joint_pos[:, env._head_pose_bl_ids] * env._head_pose_bl_mask
    )
    actual = measured - asset.data.default_joint_pos[:, neck_ids]
    err = actual - cmd
    per_joint = torch.exp(-(err / std) ** 2)
    if fine_std is not None:
        per_joint = (1.0 - fine_weight) * per_joint + fine_weight * torch.exp(
            -(err / fine_std) ** 2
        )
    return per_joint.mean(dim=-1)


# ─────────────────────────────────────────────────────────────────────────────
# NaN-safe wrappers for the sensor-derived critic observations.
#
# `robot_state_is_nan` covers joint + root state, so every obs derived from
# those is protected by the reset it triggers. The three terms below are NOT:
# they read sensor data (raycast heights, contact air-time, contact forces),
# which MuJoCo can return non-finite for while the integrated robot state is
# still clean. They are critic-only, so a single sanitized step costs the
# policy nothing, whereas letting the value through kills the entire run via
# rsl_rl's check_nan. Sanitizing here does not hide real physics blowups —
# those still terminate through nan_state and show up as
# Episode_Termination/nan_state in wandb.
# ─────────────────────────────────────────────────────────────────────────────


def _finite(x: torch.Tensor) -> torch.Tensor:
    return torch.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)


def body_pose_tracking_6d(
    env: ManagerBasedRlEnv,
    command_name: str = "body_pose",
    nominal_height: float = 0.095,
    xy_std: float = 0.02,
    z_std: float = 0.01,
    angle_std: float = math.radians(8),
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Mean of 6 per-axis Gaussian rewards for tracking commanded body pose.

    cmd has shape (N, 6) = [x, y, z, roll, pitch, yaw] all as deltas from the
    nominal standing pose (xy delta from spawn origin, z delta from
    nominal_height, angles delta from upright = 0).
    """
    asset: Entity = env.scene[asset_cfg.name]
    cmd = env.command_manager.get_command(command_name)  # (N, 6)
    dx, dy, dz = cmd[:, 0], cmd[:, 1], cmd[:, 2]
    droll, dpitch, dyaw = cmd[:, 3], cmd[:, 4], cmd[:, 5]

    # Position relative to env spawn origin. nan_to_num because MuJoCo can
    # produce NaN on contact instability and we don't want to taint the reward.
    pos_w = asset.data.root_link_pos_w
    origin = env.scene.terrain.env_origins
    rel = torch.nan_to_num(pos_w - origin, nan=0.0)
    x_err = rel[:, 0] - dx
    y_err = rel[:, 1] - dy
    z_err = rel[:, 2] - (nominal_height + dz)

    # ZYX Euler from quat.
    quat = asset.data.root_link_quat_w
    qw, qx, qy, qz = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    roll  = torch.atan2(2.0 * (qw * qx + qy * qz), 1.0 - 2.0 * (qx * qx + qy * qy))
    pitch = torch.asin(torch.clamp(2.0 * (qw * qy - qz * qx), -1.0, 1.0))
    yaw   = torch.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))

    roll_err  = roll  - droll
    pitch_err = pitch - dpitch
    yaw_err   = wrap_to_pi(yaw - dyaw)

    r_x = torch.exp(-(x_err / xy_std) ** 2)
    r_y = torch.exp(-(y_err / xy_std) ** 2)
    r_z = torch.exp(-(z_err / z_std) ** 2)
    r_r = torch.exp(-(roll_err  / angle_std) ** 2)
    r_p = torch.exp(-(pitch_err / angle_std) ** 2)
    r_w = torch.exp(-(yaw_err   / angle_std) ** 2)

    return (r_x + r_y + r_z + r_r + r_p + r_w) / 6.0


def termination_param_curriculum(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    term_name: str,
    param_stages: list[dict],
) -> torch.Tensor:
    """Mutate a termination term's params at scheduled steps.

    TerminationManager keeps its own deepcopy of the cfg dict, so the live
    term_cfgs list must be edited directly — env.cfg.terminations is a no-op.
    Useful for disabling a termination later in training (e.g. set
    bad_orientation's limit_angle to pi at iter N so the robot can fall over
    without ending the episode and learn to recover).

    param_stages: list of {step: int, params: dict}. The dict is shallow-merged
    into the live term_cfg.params at the latest matching stage.
    """
    del env_ids
    tm = env.termination_manager
    if term_name not in tm._term_names:
        # Term was removed (e.g. play mode disables fell_over entirely).
        return torch.tensor(0.0)
    idx = tm._term_names.index(term_name)
    term_cfg = tm._term_cfgs[idx]

    current = param_stages[0]["params"]
    for stage in param_stages:
        if env.common_step_counter >= stage["step"]:
            current = stage["params"]
    term_cfg.params.update(current)

    first_val = next(iter(current.values()))
    return torch.tensor(float(first_val) if isinstance(first_val, (int, float)) else 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Gait-shaping penalties ported from mjlab_microban (microban velocity recipe).
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Non-accumulating domain randomization (restore-nominal-then-apply).
#
# The stock mdp.randomize_field with operation="add"/"scale" + mode="reset"
# reads the CURRENT model value and applies the op to it, with no restore to
# nominal — so on every episode reset the perturbation STACKS on the previous
# one and the parameter random-walks away from nominal over training. For
# body_ipos (CoM) this was the long-standing microduck instability: the CoM
# drifted centimeters off-center over hundreds of resets → progressively
# unbalanced robot → falls more → reward/episode-length collapse after the early
# peak. These functions mirror randomize_mass_and_inertia: cache the nominal
# once, restore it before each draw, then apply a freshly-sampled perturbation —
# so it is re-sampled per episode but never accumulates.
# ─────────────────────────────────────────────────────────────────────────────
def randomize_com(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    ranges: tuple[float, float],
    field: str = "body_ipos",
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Randomize body CoM (body_ipos) per episode WITHOUT accumulating.

    Drop-in replacement for the buggy mdp.randomize_field(add, body_ipos, reset).
    ``ranges`` is (lo, hi) applied to all 3 CoM axes; the com_range curriculum
    updates this same ``ranges`` param. ``field`` is declared so the event can run
    with ``domain_randomization=True`` (mjlab reads params["field"] to expand that
    model field per-env).
    """
    if env_ids is None:
        env_ids = torch.arange(env.num_envs, device=env.device, dtype=torch.int)
    else:
        env_ids = env_ids.to(env.device, dtype=torch.int)

    asset: Entity = env.scene[asset_cfg.name]
    body_ids = asset_cfg.body_ids
    if isinstance(body_ids, slice):
        body_ids = list(range(asset.num_bodies))[body_ids]
    body_indices = asset.indexing.body_ids[body_ids]

    mf = getattr(env.sim.model, field)
    # Key the cache by (field, body set): multiple randomize_com events can share
    # the same field (e.g. trunk + head both randomize body_ipos) and must NOT
    # collide on a single _original_body_ipos attr — their body counts differ.
    _bidx = body_indices.tolist() if hasattr(body_indices, "tolist") else list(body_indices)
    cache_attr = f"_original_{field}_" + "_".join(str(int(i)) for i in _bidx)
    # Cache nominal on first call (model[0] is still nominal at that point).
    if not hasattr(env, cache_attr):
        setattr(env, cache_attr, mf[0, body_indices].clone())
    nominal = getattr(env, cache_attr)

    num_envs = len(env_ids)
    num_bodies = len(body_indices)

    # Restore nominal first (prevents accumulation), then add a fresh offset.
    mf[env_ids[:, None], body_indices] = nominal.unsqueeze(0).expand(num_envs, -1, -1)
    lo, hi = ranges
    offsets = torch.rand(num_envs, num_bodies, 3, device=env.device) * (hi - lo) + lo
    mf[env_ids[:, None], body_indices] += offsets
    return torch.tensor(float(hi))


# =============================================================================
# BallKick task — ball reset event, kick rewards, critic-only ball observations
# =============================================================================


def _ball_kick_dir(env: ManagerBasedRlEnv) -> torch.Tensor:
    """Per-env world-frame kick direction (XY unit vector), lazily allocated.

    Set by ``reset_ball_in_front_of_foot`` to the robot's forward direction at
    episode reset. Frozen for the episode so the policy can't redefine "forward"
    by turning after the kick.
    """
    if not hasattr(env, "_ball_kick_dir_w"):
        env._ball_kick_dir_w = torch.zeros(env.num_envs, 2, device=env.device)
        env._ball_kick_dir_w[:, 0] = 1.0
    return env._ball_kick_dir_w


def reset_ball_in_front_of_foot(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    offset: tuple = (0.09, -0.042),
    noise_xy: float = 0.015,
    ball_radius: float = 0.035,
    asset_name: str = "ball",
):
    """Place the ball in front of the (right) foot; store the kick direction.

    ``offset`` is the nominal ball-center position in the robot's yaw frame:
    at HOME the right foot is centered at (0, -0.042) with the toe tip at
    x≈0.034, so (0.08, -0.042) puts a 35mm-radius ball ~1cm in front of the
    toe. ``noise_xy`` (uniform ± per axis) is the placement DR: the policy is
    BLIND to the ball, so this is what forces a swing that works across the
    real-world placement error.

    Reads the robot root from qpos directly (root_link_pos_w lags until the
    next forward()); must be registered AFTER reset_base / set_ground_state
    (events run in dict insertion order) so the robot pose is final.
    """
    if env_ids is None or len(env_ids) == 0:
        return
    env_ids = env_ids.to(env.device)
    robot: Entity = env.scene["robot"]
    ball: Entity = env.scene[asset_name]

    root = env.sim.data.qpos[env_ids][:, robot.indexing.free_joint_q_adr]
    qw, qx, qy, qz = root[:, 3], root[:, 4], root[:, 5], root[:, 6]
    yaw = torch.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
    cos_y, sin_y = torch.cos(yaw), torch.sin(yaw)

    n = len(env_ids)
    off = torch.tensor(offset, device=env.device, dtype=torch.float).repeat(n, 1)
    off += (torch.rand(n, 2, device=env.device) * 2.0 - 1.0) * noise_xy

    pose = torch.zeros(n, 7, device=env.device)
    pose[:, 0] = root[:, 0] + cos_y * off[:, 0] - sin_y * off[:, 1]
    pose[:, 1] = root[:, 1] + sin_y * off[:, 0] + cos_y * off[:, 1]
    pose[:, 2] = env.scene.terrain.env_origins[env_ids, 2] + ball_radius
    pose[:, 3] = 1.0  # identity quat
    ball.write_root_link_pose_to_sim(pose, env_ids)
    ball.write_root_link_velocity_to_sim(
        torch.zeros(n, 6, device=env.device), env_ids
    )

    kick_dir = _ball_kick_dir(env)
    kick_dir[env_ids, 0] = cos_y
    kick_dir[env_ids, 1] = sin_y


def ball_forward_velocity(
    env: ManagerBasedRlEnv,
    asset_name: str = "ball",
    max_speed: float = 5.0,
) -> torch.Tensor:
    """Ball XY velocity along the per-env kick direction, clamped to [0, max].

    Dense and linear-in-speed up to ``max_speed``: every extra bit of forward
    ball speed pays more every step the ball keeps rolling, so exploration
    nudges bootstrap the kick with no peak-detection machinery. Backward /
    lateral ball motion earns 0 rather than a penalty — a mis-hit shouldn't
    scare the policy away from contacting the ball at all.

    With ``max_speed`` set to a TARGET speed (rather than a large cap), pair
    with ``ball_speed_overshoot_penalty``: the reward saturating at the target
    alone does NOT remove "harder is better" — a harder kick keeps the ball
    at/above the cap for more steps, so the rolling-time integral still grows
    with strike speed. The overshoot penalty is what makes the target the
    actual optimum.
    """
    ball: Entity = env.scene[asset_name]
    vel_xy = ball.data.root_link_lin_vel_w[:, :2]
    fwd = (vel_xy * _ball_kick_dir(env)).sum(dim=1)
    return torch.nan_to_num(fwd, nan=0.0).clamp(0.0, max_speed)


def ball_speed_overshoot_penalty(
    env: ManagerBasedRlEnv,
    asset_name: str = "ball",
    target_speed: float = 1.0,
    max_penalty: float = 5.0,
) -> torch.Tensor:
    """Ball forward speed in excess of ``target_speed`` (linear, ≥ 0).

    Companion to ``ball_forward_velocity`` for a target-speed kick: below the
    target this is 0 (the capped linear reward provides the upward gradient);
    above it, each m/s of overshoot costs linearly every step it persists.
    Keep this term's |weight| BELOW the capped reward's weight so the combined
    landscape peaks at the target with a gentler slope on the overshoot side —
    erring slightly hard must stay cheaper than not kicking at all.
    """
    ball: Entity = env.scene[asset_name]
    vel_xy = ball.data.root_link_lin_vel_w[:, :2]
    fwd = (vel_xy * _ball_kick_dir(env)).sum(dim=1)
    over = torch.nan_to_num(fwd, nan=0.0) - target_speed
    return over.clamp(0.0, max_penalty)


# --------------------------------------------------------------------------- #
# Tâche SPIN — rotation rapide sur place sur rollers                            #
# --------------------------------------------------------------------------- #
# Enveloppe de phase : la commande du slot bouton porte une phase, qui pilote
# une VITESSE DE LACET cible en trapèze (et non une pose comme le crouch).
#   [0, accel_end)        0.5 s   0 -> rate_max    (lancement)
#   [accel_end, hold_end) 1.6 s   rate_max         (régime)
#   [hold_end, brake_end) 0.5 s   rate_max -> 0    (freinage)
#   [brake_end, 1.0)      1.4 s   0                (repos debout)
# Aire sous l'enveloppe sur un cycle = 2.1 * SPIN_RATE_MAX rad. À 3.0 rad/s :
# 2.1 * 3.0 = 6.3 rad ~ 1 tour (et non ~2, comme avec l'ancienne cible 6.0).
SPIN_RATE_MAX = 3.0
SPIN_ACCEL_END = 0.125
SPIN_HOLD_END = 0.525
SPIN_BRAKE_END = 0.650


def spin_rate_by_phase(
    phase: torch.Tensor,
    rate_max: float = SPIN_RATE_MAX,
    accel_end: float = SPIN_ACCEL_END,
    hold_end: float = SPIN_HOLD_END,
    brake_end: float = SPIN_BRAKE_END,
) -> torch.Tensor:
    """Vitesse de lacet cible (rad/s, positive = anti-horaire) le long de la phase."""
    w = torch.zeros_like(phase)
    accel = phase < accel_end
    w = torch.where(accel, rate_max * phase / accel_end, w)
    hold = (phase >= accel_end) & (phase < hold_end)
    w = torch.where(hold, torch.full_like(phase, rate_max), w)
    brake = (phase >= hold_end) & (phase < brake_end)
    w = torch.where(
        brake, rate_max * (1.0 - (phase - hold_end) / (brake_end - hold_end)), w
    )
    return w


def spin_gate_by_phase(
    phase: torch.Tensor,
    rate_max: float = SPIN_RATE_MAX,
    accel_end: float = SPIN_ACCEL_END,
    hold_end: float = SPIN_HOLD_END,
    brake_end: float = SPIN_BRAKE_END,
) -> torch.Tensor:
    """Porte de shaping dans [0,1] = enveloppe normalisée.

    Vaut 0 sur tout le segment de repos : les amorces (ciseau des jambes,
    différentiel des roues) ne s'appliquent que pendant lancement + régime, donc
    le robot revient en station neutre avant de rendre la main à la policy roller.
    """
    return spin_rate_by_phase(phase, rate_max, accel_end, hold_end, brake_end) / rate_max


def spin_phase_from_command(cmd: torch.Tensor) -> torch.Tensor:
    """Récupère la phase [0,1) depuis la commande [cos(2πφ), sin(2πφ), 0] du slot."""
    return (torch.atan2(cmd[:, 1], cmd[:, 0]) / (2 * torch.pi)) % 1.0


def _spin_target_rate(
    env: ManagerBasedRlEnv,
    command_name: str,
    rate_max: float,
    accel_end: float,
    hold_end: float,
    brake_end: float,
) -> torch.Tensor:
    phase = spin_phase_from_command(env.command_manager.get_command(command_name))
    return spin_rate_by_phase(phase, rate_max, accel_end, hold_end, brake_end)


def _spin_gate(
    env: ManagerBasedRlEnv,
    command_name: str,
    rate_max: float,
    accel_end: float,
    hold_end: float,
    brake_end: float,
) -> torch.Tensor:
    phase = spin_phase_from_command(env.command_manager.get_command(command_name))
    return spin_gate_by_phase(phase, rate_max, accel_end, hold_end, brake_end)


def spin_rate_reward_from_values(
    omega_z: torch.Tensor, omega_target: torch.Tensor, std: float
) -> torch.Tensor:
    """Gaussienne sur l'erreur de vitesse de lacet (fonction pure, testable)."""
    return torch.exp(-(((omega_z - omega_target) / std) ** 2))


def spin_rate_track(
    env: ManagerBasedRlEnv,
    command_name: str = "twist",
    std: float = 1.5,
    rate_max: float = SPIN_RATE_MAX,
    accel_end: float = SPIN_ACCEL_END,
    hold_end: float = SPIN_HOLD_END,
    brake_end: float = SPIN_BRAKE_END,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Objectif principal du spin : suivre la vitesse de lacet cible ω*(φ).

    ω_z est pris en repère corps (c'est ce que voit le gyro de l'IMU, donc ce que
    la policy observe). Une rotation dans le mauvais sens est plus punie que
    l'immobilité, la gaussienne étant centrée sur une cible positive.
    """
    asset: Entity = env.scene[asset_cfg.name]
    omega_z = asset.data.root_link_ang_vel_b[:, 2]
    target = _spin_target_rate(env, command_name, rate_max, accel_end, hold_end, brake_end)
    return spin_rate_reward_from_values(omega_z, target, std)


SPIN_LAUNCH_DRIFT_SCALE = 0.2  # atténuation du coût de dérive pendant le lancement


def spin_stay_in_place(
    env: ManagerBasedRlEnv,
    command_name: str = "twist",
    launch_scale: float = SPIN_LAUNCH_DRIFT_SCALE,
    accel_end: float = SPIN_ACCEL_END,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Coût ‖v_xy‖² du tronc : tourner SUR PLACE, et tuer l'élan d'entrée.

    Pas d'état de référence (contrairement à une dérive mesurée depuis le reset),
    donc reste valide sur les 5 cycles d'un épisode. À utiliser avec un poids
    NÉGATIF.

    ATTÉNUÉ PENDANT LE LANCEMENT : sur `[0, accel_end)` le robot doit pousser au
    sol pour s'injecter du moment angulaire, et l'état d'entrée lui donne jusqu'à
    0.3 m/s qu'il est censé CONVERTIR en rotation. Facturer la translation à plein
    tarif à cet instant s'oppose donc directement à l'objectif. Le coût est
    multiplié par `launch_scale` sur ce seul segment, et vaut plein tarif ensuite
    (régime, freinage, repos) où « sur place » est le vrai critère.

    Contrairement aux autres amorces du spin, ce terme n'est PAS éteint par
    `spin_gate_by_phase` : pendant le repos on veut justement qu'il reste plein,
    puisque c'est là que le robot doit être immobile.
    """
    asset: Entity = env.scene[asset_cfg.name]
    v_xy = asset.data.root_link_lin_vel_b[:, :2]
    cost = torch.sum(torch.square(v_xy), dim=1)

    phase = spin_phase_from_command(env.command_manager.get_command(command_name))
    scale = torch.where(
        phase < accel_end,
        torch.full_like(cost, launch_scale),
        torch.ones_like(cost),
    )
    return cost * scale


# Demi-voie mesurée sur le modèle rollers (pose HOME, sites left_foot/right_foot) :
# 0.0499 m, contre 0.03 m estimé au spec. Conséquence mécanique de SPIN_RATE_MAX
# (A1) : différentiel attendu = 2*SPIN_RATE_MAX*demi_voie/r, r = 0.0175 m.
# À l'ancienne cible 6.0 rad/s : 2*6.0*0.0499/0.0175 = 34.2 rad/s (retenu comme
# 34.0, soit +71% par rapport aux 20.0 estimés au spec -> seuil de 30% dépassé).
# À la nouvelle cible 3.0 rad/s : 2*3.0*0.0499/0.0175 = 17.1 rad/s. Laisser 34.0
# ici plafonnerait le terme à tanh(17.1/34) = 0.47 de son propre maximum, ce qui
# affaiblirait exactement le shaping qu'on veut renforcer (cf. spin_stay_in_place).
SPIN_WHEEL_OMEGA_SCALE = 17.0  # rad/s ; recalibré sur la demi-voie mesurée et SPIN_RATE_MAX = 3.0


def spin_wheel_differential_from_values(
    diff: torch.Tensor, gate: torch.Tensor, omega_scale: float
) -> torch.Tensor:
    """Fonction pure : tanh du différentiel de roues, portée par gate, clampée ≥ 0."""
    return gate * torch.tanh(torch.clamp(diff, min=0.0) / omega_scale)


# =============================================================================
# Backlash model — encoder-through-backlash joint observations
# =============================================================================
# The backlash model (robot_groundcontact_backlash.xml) puts an unactuated
# ``passive_<joint>_backlash`` hinge in series with each servo joint. The link
# angle is qpos[servo] + qpos[backlash], and the real encoder sits on the
# OUTPUT side of the play — it reads the sum. These obs replace joint_pos_rel /
# joint_vel_rel in backlash tasks (see tasks/backlash.py) so the policy sees
# exactly what the runtime will feed it. The asset_cfg regex is expected to
# select only the servo joints (the usual ``^(?!passive_).*``).


def _backlash_encoder_ids(
    env: "ManagerBasedRlEnv",
    asset: Entity,
    asset_cfg: SceneEntityCfg,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """(main_ids, backlash_ids, mask) — cached per (entity, joint selection).

    mask is 1.0 where a matching passive_<name>_backlash joint exists, so the
    same obs functions run unchanged on models without backlash joints.
    """
    key = (asset_cfg.name, str(asset_cfg.joint_ids))
    cache = env.__dict__.setdefault("_backlash_encoder_cache", {})
    hit = cache.get(key)
    if hit is not None:
        return hit

    names = asset.joint_names
    jnt_ids = asset_cfg.joint_ids
    if isinstance(jnt_ids, slice):
        main_ids = list(range(len(names)))[jnt_ids]
    else:
        main_ids = [int(i) for i in jnt_ids]
    name_to_id = {n: i for i, n in enumerate(names)}
    bl_ids, mask = [], []
    for i in main_ids:
        bl = name_to_id.get(f"passive_{names[i]}_backlash")
        bl_ids.append(0 if bl is None else bl)
        mask.append(0.0 if bl is None else 1.0)

    device = asset.data.joint_pos.device
    out = (
        torch.tensor(main_ids, dtype=torch.long, device=device),
        torch.tensor(bl_ids, dtype=torch.long, device=device),
        torch.tensor(mask, dtype=torch.float32, device=device),
    )
    cache[key] = out
    return out


def joint_pos_rel_backlash(
    env: "ManagerBasedRlEnv",
    biased: bool = False,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """joint_pos_rel where the encoder reads through the backlash hinge.

    Returns (qpos[servo] + qpos[backlash]) - default[servo]. With biased=True
    the per-env encoder-calibration bias is applied to the servo reading (one
    encoder per servo → one bias per joint; the backlash summand stays raw).
    """
    asset: Entity = env.scene[asset_cfg.name]
    main_ids, bl_ids, mask = _backlash_encoder_ids(env, asset, asset_cfg)
    joint_pos = asset.data.joint_pos_biased if biased else asset.data.joint_pos
    pos = joint_pos[:, main_ids] + asset.data.joint_pos[:, bl_ids] * mask
    default_joint_pos = asset.data.default_joint_pos
    assert default_joint_pos is not None
    return pos - default_joint_pos[:, main_ids]


# ─────────────────────────────────────────────────────────────────────────────
# Sit↔Stand posture command + posture-conditioned rewards (sitstand env).
#
# One policy, both directions: the command is a single sit/stand flag carried
# in the twist slot (cmd = [sit_flag, 0, 0], so "stand" is the all-zero
# command — same deployment idle as every other policy). All task rewards
# below select their target (SIT keyframe + SIT_Z vs HOME + STAND_Z) from the
# live command, per env, so the same reward stack drives the descent, the
# seated rest, the rise and the standing rest. Uses the _servo_* helpers →
# backlash-model compatible.
# ─────────────────────────────────────────────────────────────────────────────


class SitStandCommand(UniformVelocityCommand):
    """Posture command: cmd = [sit_flag, 0, 0] with dwell-time resampling and a
    SLEWED internal target blend.

    sit_flag ∈ {0.0, 1.0}. Resampled by the command manager on the cfg's
    resampling_time_range (the dwell time in each posture) and on episode
    reset. cfg.sit_prob is the probability a resample commands SIT; with the
    reset-state mix this trains all four (start-state × command) combinations,
    including "hold what you're already doing".

    ``alpha`` (0 = STAND target, 1 = SIT target) slews toward the flag at a
    constant rate (full transition in cfg.ramp_s seconds) and is what the
    posture_* rewards track. THE anti-crash mechanism: with a binary target,
    arriving early pays the full goal-state jackpot for every step saved,
    while the linear speed-cap penalties integrate to a bounded excess-
    distance cost — an instant drop beat a 1 s descent by ~7×. With the
    slewed target, being AHEAD of the ramp scores ~0 on the height/composite
    stack (z far from the commanded height), so tracking the slow setpoint IS
    the argmax; the caps remain as backstops for overshoot/bounce. The OBS
    stays the raw binary flag (deployment: runtime writes 0/1; the trained
    response to a flip is the ~ramp_s glide).

    On episode reset, alpha is initialised from the robot's ACTUAL trunk
    height, not the flag — a seated spawn must not be dragged upward by a
    stand-initialised ramp (and vice versa).
    """

    def __init__(self, cfg, env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self._sit_prob = float(getattr(cfg, "sit_prob", 0.5))
        self._ramp_s = float(getattr(cfg, "ramp_s", 2.0))
        self._sit_z = float(getattr(cfg, "sit_z", 0.060))
        self._stand_z = float(getattr(cfg, "stand_z", 0.115))
        self._env_ref = env
        self._alpha = torch.zeros(self.num_envs, device=self.device)

    @property
    def command(self) -> torch.Tensor:
        return self.vel_command_b

    @property
    def alpha(self) -> torch.Tensor:
        """Slewed target blend: 0 = STAND target, 1 = SIT target."""
        return self._alpha

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        n = len(env_ids)
        if n == 0:
            return
        sit = (torch.rand(n, device=self.device) < self._sit_prob).float()
        self.vel_command_b[env_ids] = 0.0
        self.vel_command_b[env_ids, 0] = sit

    def _alpha_from_height(self) -> torch.Tensor:
        z = torch.nan_to_num(
            self.robot.data.root_link_pos_w[:, 2]
            - self._env_ref.scene.terrain.env_origins[:, 2],
            nan=self._stand_z,
        )
        return torch.clamp(
            (self._stand_z - z) / max(self._stand_z - self._sit_z, 1e-6), 0.0, 1.0
        )

    def compute(self, dt: float, env_ids=None) -> None:
        super().compute(dt, env_ids)
        # Episode-start re-init of the blend from the ACTUAL trunk height.
        # Done here (not in reset()) because the command manager resets BEFORE
        # the set_ground_state event teleports the robot, so reset() would read
        # the pre-teleport height. On the first compute of an episode the spawn
        # state is in place.
        fresh = self._env_ref.episode_length_buf <= 1
        if fresh.any():
            self._alpha = torch.where(fresh, self._alpha_from_height(), self._alpha)
        # Constant-rate slew of the target blend toward the commanded flag.
        step = dt / max(self._ramp_s, 1e-6)
        delta = self.vel_command_b[:, 0] - self._alpha
        self._alpha += torch.clamp(delta, -step, step)

    def _update_command(self, env_ids: torch.Tensor | None = None) -> None:
        pass  # No heading controller / standing-env machinery.

    def _update_metrics(self) -> None:
        pass  # No velocity-tracking metrics for a posture flag.


def _posture_blend(env: ManagerBasedRlEnv, command_name: str) -> torch.Tensor:
    """Target blend ∈ [0, 1] (0 = STAND, 1 = SIT) for the posture rewards.

    Uses the SitStandCommand's slewed ``alpha`` (the moving setpoint) when the
    term exposes it; falls back to the raw binary flag otherwise.
    """
    term = env.command_manager.get_term(command_name)
    alpha = getattr(term, "alpha", None)
    if alpha is not None:
        return alpha
    return env.command_manager.get_command(command_name)[:, 0]


def _posture_targets(
    env: ManagerBasedRlEnv,
    asset: Entity,
    command_name: str,
    sit_overrides: dict,
) -> tuple[torch.Tensor, torch.Tensor]:
    """(target blend, per-env joint target) for the commanded posture.

    STAND target = default_joint_pos (HOME); SIT target = HOME with the
    keyframe overrides applied; the SLEWED blend interpolates between them,
    so mid-ramp the rewarded pose folds in sync with the descending height.
    """
    blend = _posture_blend(env, command_name)
    stand_target = _servo_default_joint_pos(env, asset)
    sit_target = stand_target.clone()
    for idx, val in sit_overrides.items():
        sit_target[:, idx] = val
    target = stand_target + blend.unsqueeze(-1) * (sit_target - stand_target)
    return blend, target


def _posture_height(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_z: float,
    stand_z: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """(slewed target trunk z, actual trunk z) per env."""
    blend = _posture_blend(env, command_name)
    target_z = stand_z + blend * (sit_z - stand_z)
    asset = env.scene["robot"]
    z = torch.nan_to_num(
        asset.data.root_link_pos_w[:, 2] - env.scene.terrain.env_origins[:, 2], nan=0.0
    )
    return target_z, z


def posture_pose_match(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_overrides: dict,
    joint_indices: list,
    std: float = 0.5,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Gaussian pose-match against the commanded posture's target pose."""
    asset = env.scene[asset_cfg.name]
    _, target = _posture_targets(env, asset, command_name, sit_overrides)
    joint_pos = _servo_joint_pos(env, asset)[:, joint_indices]
    target = target[:, joint_indices]
    return torch.exp(-((joint_pos - target) / std) ** 2).mean(dim=-1)


def posture_height_gaussian(
    env: ManagerBasedRlEnv,
    command_name: str,
    sit_z: float,
    stand_z: float,
    std: float = 0.02,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Gaussian on trunk z against the commanded posture's target height."""
    del asset_cfg  # trunk z read via _posture_height
    target_z, z = _posture_height(env, command_name, sit_z, stand_z)
    return torch.exp(-((z - target_z) / std) ** 2)


# ==============================================================================
# Roulade (forward roll) task — episodic dynamic maneuver
# ==============================================================================
#
# Third attempt at the roulade. What the first two taught us:
#   • origin/roulade (phase-clock + time-windowed reward stages): plateaued
#     face-down at ~90° — time windows are keyframes-in-time, campable local
#     optima (the sit/standup lesson exactly). Also integrated -ω_y as forward
#     progress, which by this codebase's own convention (face-down = +90° pitch
#     = rotation about +y, see set_random_ground_state) is the WRONG SIGN — the
#     progress reward paid for backward rotation.
#   • origin/roulade later commits (keyframe imitation): same waypoint-camping
#     family, dropped per feedback-episodic-pose-landing.
#
# This design uses the proven episodic recipe instead:
#   • ONE dense progress signal: paid INCREMENTS of the max-so-far cumulative
#     forward rotation (potential-based — a camping policy earns zero/step, a
#     full roll earns exactly 2π worth no matter the path or speed).
#   • Landing rewards (composite product, upright, height, rise velocity) are
#     gated on ROLL COMPLETION (max rotation ≥ threshold) — state-based gates,
#     not clock-based. "Do nothing" earns nothing; standing at spawn earns
#     nothing; only rolling opens the standing-attractor annuity.
#   • Reverse curriculum via mid-roll spawns (the face-up partial-roll trick
#     that fixed back-recovery): a slice of episodes starts pitched 50°–185°
#     into the roll, tucked, optionally with forward angular momentum, and the
#     rotation accumulator is initialized to the spawn angle so the progress
#     accounting stays consistent.
#
# RUN-1 LESSON (2026-08): with unsupported rotation counting and uncapped
# paid rate, the optimal policy is a violent ballistic whip ("breakdance") —
# same 2π, finishes sooner, more discounted annuity. Doesn't transfer. Fixes:
#   • SUPPORT GATE: the accumulator only integrates while some robot geom
#     touches the terrain (robot_ground_contact sensor) — a real roulade never
#     leaves the ground; airborne rotation now earns nothing and cannot open
#     the completion gate.
#   • HEAD LATCH: the landing annuity additionally requires head-ground
#     contact to have occurred while accum was in the first-quadrant window —
#     "went over the head" is a requirement, not a 0.5-weight suggestion.
#   • PAID-RATE CAP: progress increments are capped at max_paid_rate; rotation
#     faster than the cap FORFEITS the excess (not deferred), so speed no
#     longer pays. An explicit overspeed penalty backs this up.
#
# Per-env state on the env object (created lazily, reset by
# reset_roulade_state):
#   env._roulade_accum      — supported-only integral of forward pitch rate (rad)
#   env._roulade_max        — max(accum) so far this episode (progress frontier)
#   env._roulade_paid       — frontier already paid out by roulade_progress
#   env._roulade_head_latch — True once the head touched ground mid-first-quadrant

# Forward-roll sign: face-down is +90° pitch = rotation about body +y
# (set_random_ground_state convention), so forward roll = POSITIVE body-frame
# ω_y. Verified empirically (see claude_experiments smoke test): a positive
# qvel about +y pitches the robot nose-down/forward and drives accum upward.
_ROULADE_FWD_SIGN = 1.0

# Sensor names read by the accumulator update (must match the env cfg).
_ROULADE_SUPPORT_SENSOR = "robot_ground_contact"
_ROULADE_HEAD_SENSOR = "head_ground_contact"

# Head-latch window: head-ground contact while accum is inside this window
# marks the episode as a genuine over-the-head roll. In a real roulade the
# head plants at ~60–120° of body rotation; the window is generous around it.
_HEAD_LATCH_LO = math.radians(20.0)
_HEAD_LATCH_HI = math.radians(170.0)

# Head-top axis in jaw_soft's LOCAL frame (measured empirically 2026-08-13:
# world-up expressed in jaw_soft's frame with the robot settled at HOME).
# The latch requires this axis to point DOWN at contact — "the flat top of
# the head on the floor", not the face or the side of the shell (run-5 fix:
# the run-4 policy rolled over the shoulder, which still touched jaw_soft).
_HEAD_TOP_AXIS = (0.882, 0.0, 0.471)
# dot(top_axis_world, -z) threshold. Measured landmarks (trunk pitched 110°):
# passive face-plant (neck at HOME) reads +0.6, full chin-tuck (neck_pitch −1,
# head_pitch +1) reads −0.99 — 0.3 accepts partial tucks while staying far
# from any face/side contact.
_HEAD_TOP_DOWN_MIN = 0.3

# Sagittal flatness gate on the accumulator (run-5): in a clean forward roll
# the body's LATERAL axis stays horizontal the whole way — its world-z
# component is 2(q_y·q_z + q_w·q_x) ≈ 0 for ANY amount of pure pitch, and
# grows toward ±1 as the roll goes over the shoulder instead. Full rotation
# credit while the lateral axis is within ~30° of horizontal, zero beyond
# ~60°: a side roll does not count as rotation, earns no progress, and never
# opens the landing gate.
_FLAT_FULL = 0.5    # |lateral_axis_z| = sin(30°): full credit below
_FLAT_ZERO = 0.866  # sin(60°): zero credit above


def _lateral_axis_z(quat: torch.Tensor) -> torch.Tensor:
    """World-z component of the body's lateral (y) axis. 0 = flat/sagittal."""
    return 2.0 * (quat[:, 2] * quat[:, 3] + quat[:, 0] * quat[:, 1])


def _head_top_down(env: ManagerBasedRlEnv, asset: Entity) -> torch.Tensor:
    """True where the head-top axis points at the floor (dot with -z > min)."""
    if not hasattr(env, "_roulade_head_body_id"):
        ids, _ = asset.find_bodies("jaw_soft")
        env._roulade_head_body_id = ids[0]
    q = asset.data.body_link_quat_w[:, env._roulade_head_body_id]
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    a, b, c = _HEAD_TOP_AXIS
    # z-component of R(q) @ axis_local
    axis_world_z = (
        2.0 * (x * z - w * y) * a + 2.0 * (y * z + w * x) * b + (1.0 - 2.0 * (x * x + y * y)) * c
    )
    return axis_world_z < -_HEAD_TOP_DOWN_MIN


def _sensor_any_contact(env: ManagerBasedRlEnv, name: str) -> torch.Tensor | None:
    if name not in env.scene.sensors:
        return None
    found = env.scene.sensors[name].data.found
    return (found.view(found.shape[0], -1) > 0).any(dim=-1)


def _roulade_state(env: ManagerBasedRlEnv) -> tuple:
    if not hasattr(env, "_roulade_accum"):
        z = torch.zeros(env.num_envs, device=env.device)
        env._roulade_accum = z.clone()
        env._roulade_max = z.clone()
        env._roulade_paid = z.clone()
        env._roulade_head_latch = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
        env._roulade_last_update_step = -1
    return env._roulade_accum, env._roulade_max, env._roulade_paid


def _update_roulade_accum(env: ManagerBasedRlEnv, asset: Entity) -> None:
    """Integrate forward pitch rate into the per-env rotation accumulator.

    Step-guarded so that multiple reward terms reading the accumulator in the
    same control step don't double-integrate. The frontier (max) only moves
    forward; backward rocking (wind-up) neither pays nor un-pays.

    SUPPORT GATE (run-1 fix): rotation is integrated only while the robot
    touches the terrain — a roulade is a supported motion; ballistic flips
    accumulate nothing, so they neither get paid nor open the completion gate.

    Also latches env._roulade_head_latch when the head touches the ground
    while accum is inside the first-quadrant window — the landing annuity
    requires this, making "over the head" a hard requirement of the task.
    """
    _roulade_state(env)
    step = int(env.common_step_counter)
    if step != env._roulade_last_update_step:
        omega_fwd = _ROULADE_FWD_SIGN * asset.data.root_link_ang_vel_b[:, 1]
        delta = torch.nan_to_num(omega_fwd, nan=0.0) * env.step_dt
        supported = _sensor_any_contact(env, _ROULADE_SUPPORT_SENSOR)
        if supported is not None:
            delta = delta * supported.float()
        # Sagittal flatness gate (run-5): side/shoulder rolls don't count.
        y_z = torch.nan_to_num(_lateral_axis_z(asset.data.root_link_quat_w), nan=1.0).abs()
        t = torch.clamp((_FLAT_ZERO - y_z) / (_FLAT_ZERO - _FLAT_FULL), 0.0, 1.0)
        delta = delta * (t * t * (3.0 - 2.0 * t))
        env._roulade_accum = env._roulade_accum + delta
        env._roulade_max = torch.maximum(env._roulade_max, env._roulade_accum)

        head_contact = _sensor_any_contact(env, _ROULADE_HEAD_SENSOR)
        if head_contact is not None:
            in_window = (env._roulade_accum > _HEAD_LATCH_LO) & (
                env._roulade_accum < _HEAD_LATCH_HI
            )
            # Run-5: contact must be with the FLAT TOP of the head (top axis
            # pointing at the floor) — face/side shell contacts don't latch.
            env._roulade_head_latch = env._roulade_head_latch | (
                head_contact & in_window & _head_top_down(env, asset)
            )
        env._roulade_last_update_step = step


def _roulade_completion_gate(
    env: ManagerBasedRlEnv,
    gate_lo: float,
    gate_hi: float,
    require_head: bool = False,
) -> torch.Tensor:
    """Smoothstep on the progress frontier: 0 below gate_lo rad, 1 above gate_hi.

    State-based replacement for the old phase-clock landing window — it can
    only be opened by actually rotating (while SUPPORTED — the accumulator is
    contact-gated), so neither pre-roll standing nor a ballistic flip collects.
    With require_head=True the gate additionally requires the head latch —
    the episode must have rolled over the head to unlock the landing annuity.
    """
    _, max_accum, _ = _roulade_state(env)
    t = torch.clamp((max_accum - gate_lo) / max(gate_hi - gate_lo, 1e-6), 0.0, 1.0)
    gate = t * t * (3.0 - 2.0 * t)
    if require_head:
        gate = gate * env._roulade_head_latch.float()
    return gate


def reset_roulade_state(
    env: ManagerBasedRlEnv,
    env_ids: torch.Tensor,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    standing_prob: float = 0.5,
    midroll_prob: float = 0.5,
    standing_z_min: float = 0.11,
    standing_z_max: float = 0.12,
    standing_tilt_max: float = 0.0,
    forward_vel_range: tuple = (0.0, 0.0),
    midroll_pitch_min: float = math.radians(50.0),
    midroll_pitch_max: float = math.radians(185.0),
    midroll_z_min: float = 0.05,
    midroll_z_max: float = 0.10,
    midroll_omega_range: tuple = (0.0, 0.0),
    tuck_overrides: Optional[dict] = None,
    tuck_factor_range: tuple = (0.3, 1.0),
    joint_noise_std: float = 0.0,
):
    """Reset to a standing start or a mid-roll state (reverse curriculum).

    Standing bucket: upright (±standing_tilt_max pitch/roll noise), random yaw,
    HOME joints (left from reset_robot_joints), z in [standing_z_min, _max].
    ``forward_vel_range`` is the élan hook: a per-env forward base velocity
    (body x, mapped to world through the spawn yaw) sampled uniformly — 0 for
    a standstill roll, widen it later to train rolls out of a walk.

    Mid-roll bucket: pitched ``midroll_pitch_min..max`` into the roll (90° =
    on the head, 180° = on the back), random yaw, legs lerped HOME→tuck by a
    per-env factor in ``tuck_factor_range``, z in [midroll_z_min, _max],
    optional forward angular momentum from ``midroll_omega_range``. The
    rotation accumulator is initialized to the spawn pitch so progress
    accounting (and the completion gates) stay consistent: a 170° spawn only
    gets paid for the remaining ~190°.
    """
    if env_ids is None or len(env_ids) == 0:
        return
    env_ids = env_ids.to(env.device, dtype=torch.long)
    num = len(env_ids)
    asset: Entity = env.scene[asset_cfg.name]
    accum, max_accum, paid = _roulade_state(env)

    total = standing_prob + midroll_prob
    is_mid = torch.rand(num, device=env.device) < (midroll_prob / max(total, 1e-6))

    yaw = torch.rand(num, device=env.device) * 2 * np.pi - np.pi
    cy = torch.cos(yaw * 0.5)
    sy = torch.sin(yaw * 0.5)

    # Pitch per bucket: small noise for standing, mid-roll angle otherwise.
    pitch = (torch.rand(num, device=env.device) * 2 - 1) * standing_tilt_max
    mid_pitch = (
        torch.rand(num, device=env.device) * (midroll_pitch_max - midroll_pitch_min)
        + midroll_pitch_min
    )
    pitch = torch.where(is_mid, mid_pitch, pitch)
    roll = (torch.rand(num, device=env.device) * 2 - 1) * max(standing_tilt_max, math.radians(5.0))

    cp = torch.cos(pitch * 0.5); sp = torch.sin(pitch * 0.5)
    cr = torch.cos(roll * 0.5); sr = torch.sin(roll * 0.5)
    # ZYX intrinsic Euler → quaternion (yaw * pitch * roll), as in
    # set_random_ground_state.
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    quat = torch.stack([qw, qx, qy, qz], dim=1)

    z_stand = torch.rand(num, device=env.device) * (standing_z_max - standing_z_min) + standing_z_min
    z_mid = torch.rand(num, device=env.device) * (midroll_z_max - midroll_z_min) + midroll_z_min
    new_z = torch.where(is_mid, z_mid, z_stand)

    env.sim.data.qpos[env_ids, 2] = new_z
    env.sim.data.qpos[env_ids, 3:7] = quat
    env.sim.data.qvel[env_ids, :6] = 0.0

    servo_ids = _servo_joint_ids(env, asset)

    # Mid-roll joints: lerp HOME → tuck on the overridden joints, noise on all
    # servo joints (passive_* backlash hinges must stay at 0).
    mid_env_ids = env_ids[is_mid]
    if len(mid_env_ids) > 0 and tuck_overrides:
        u = (
            torch.rand(len(mid_env_ids), device=env.device)
            * (tuck_factor_range[1] - tuck_factor_range[0])
            + tuck_factor_range[0]
        )
        for jnt_idx, angle in tuck_overrides.items():
            col = 7 + servo_ids[jnt_idx]
            home = env.sim.data.qpos[mid_env_ids, col]
            env.sim.data.qpos[mid_env_ids, col] = home + u * (angle - home)
    if len(mid_env_ids) > 0 and joint_noise_std > 0.0:
        cols = torch.tensor([7 + j for j in servo_ids], device=env.device, dtype=torch.long)
        noise = torch.randn(len(mid_env_ids), len(cols), device=env.device) * joint_noise_std
        env.sim.data.qpos[mid_env_ids.unsqueeze(1), cols.unsqueeze(0)] += noise

    # Mid-roll forward angular momentum: rotation about body +y. MuJoCo free
    # joint qvel[3:6] is the angular velocity in the BODY frame, so [0, ω, 0]
    # is the forward-roll axis regardless of spawn yaw (verified in the smoke
    # test — a yawed spawn still rolls straight ahead in its own frame).
    if len(mid_env_ids) > 0 and midroll_omega_range[1] > 0.0:
        omega = (
            torch.rand(len(mid_env_ids), device=env.device)
            * (midroll_omega_range[1] - midroll_omega_range[0])
            + midroll_omega_range[0]
        )
        env.sim.data.qvel[mid_env_ids, 4] = _ROULADE_FWD_SIGN * omega

    # Élan hook: forward base velocity for STANDING spawns, body x → world xy
    # through the spawn yaw. (0, 0) = standstill start, disabled.
    stand_env_ids = env_ids[~is_mid]
    if len(stand_env_ids) > 0 and forward_vel_range[1] > 0.0:
        vx = (
            torch.rand(len(stand_env_ids), device=env.device)
            * (forward_vel_range[1] - forward_vel_range[0])
            + forward_vel_range[0]
        )
        yaw_s = yaw[~is_mid]
        env.sim.data.qvel[stand_env_ids, 0] = vx * torch.cos(yaw_s)
        env.sim.data.qvel[stand_env_ids, 1] = vx * torch.sin(yaw_s)

    # Progress accounting: standing starts at 0, mid-roll at the spawn pitch.
    spawn_angle = torch.where(is_mid, mid_pitch, torch.zeros_like(mid_pitch))
    accum[env_ids] = spawn_angle
    max_accum[env_ids] = spawn_angle
    paid[env_ids] = spawn_angle
    # Head latch: mid-roll spawns are considered already past the head phase
    # (the reverse curriculum teaches roll COMPLETION; requiring a latch they
    # never had the chance to earn would keep their landing gate shut forever).
    # Standing spawns must earn it by actually rolling over the head.
    env._roulade_head_latch[env_ids] = is_mid


def roulade_progress(
    env: ManagerBasedRlEnv,
    target_angle: float = 2 * math.pi,
    max_paid_rate: float = 3.0,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """Pay increments of the progress frontier, up to one full roll.

    reward = Δ(min(max_accum, target)) / (step_dt · target), CAPPED at
    max_paid_rate rad/s of paid rotation. Nothing to farm by camping
    face-down (0/step), rocking below the frontier (0/step), or spinning past
    2π (clamped). The accumulator is support-gated, so airborne rotation pays
    nothing either.

    max_paid_rate (run-1 fix): rotation faster than the cap FORFEITS the
    excess — the paid pointer still jumps to the frontier, it just pays the
    capped amount. A violent whip therefore collects LESS total progress
    reward than a controlled ≤cap roll, instead of the same total sooner.
    """
    asset: Entity = env.scene[asset_cfg.name]
    _update_roulade_accum(env, asset)
    _, max_accum, paid = _roulade_state(env)
    new_paid = torch.clamp(max_accum, max=target_angle)
    delta = torch.clamp(new_paid - torch.clamp(paid, max=target_angle), min=0.0)
    delta = torch.clamp(delta, max=max_paid_rate * env.step_dt)
    env._roulade_paid = torch.maximum(paid, new_paid)
    return delta / (env.step_dt * target_angle)


