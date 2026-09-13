"""Microduck *sitstand* task (v1.5, mjlab 1.3.0) — commanded sit ↔ stand, GENTLY.

One policy, both directions, driven by a posture command:
    cmd (twist slot) = [sit_flag, 0, 0]   sit_flag ∈ {0 = STAND, 1 = SIT}
"Stand" is the all-zero command — the same deployment idle as every other
policy. The command flips mid-episode with a dwell time of a few seconds, so
each episode trains descents, seated rest, rises and standing rest, plus
"hold what you're already doing" (reset state × command are independent).

2026-08 rebuild from scratch (the old phase-cycle env predates the 1.3.0
migration and every sit/standup lesson). Design synthesis:
  - Posture-conditioned single-target rewards (mdp posture_*): the sit env's
    minimum-viable "organic discovery" stack, but the target (SIT keyframe +
    SIT_Z vs HOME + STAND_Z) is selected per env from the live command. No
    trajectory, no waypoints, no phase timing — the policy discovers its own
    transition path, in as many steps as it likes (knee-down first, head
    assist, etc. are all allowed: full-collision model, no head-ground
    penalty, no fall termination).
  - Gentleness both ways: descent-speed cap (sit env's proven recipe, -10
    from step 0) AND a mirrored rise-speed cap (introduced by curriculum
    AFTER the rise is discovered — the standup attempt-tax lesson), plus the
    |a_z| shock penalty throughout.
  - Rest quality: posture_stillness (velocity-Gaussian at the commanded
    height, tilt-gated) + posture_composite (multiplicative height·upright·
    pose vs the commanded target — partial-sum exploits like plank/flop/lean
    collapse to ~0).
  - Head commandable in BOTH postures (head_pose command + tracking, exactly
    like velocity/standup), body_command slot zero-padded → 61D obs parity.
  - Sim2real: velocity-parity DR / obs noise / delays / regularisers (the
    transferring recipe), sit env's contact-solver hardening (nconmax=200,
    iters 30/50 — seated contact NaN fix), delayed push ramp (pushes early
    made the sit env unlearn sitting).

Keyframes (stability-verified, keep in sync with sit/standup envs):
  SIT  = knee ±1.35, hip_pitch ∓0.4079, ankle/hip_roll 0, trunk z 0.060
         (swept 2026-07-27 — the old keyframe tipped over; verify TILT in sim
         before changing this pose).
  STAND = HOME joints, trunk z 0.115 (measured standing equilibrium).

Joint layout (14 actuated joints):
    0-4 : left  leg (hip_yaw, hip_roll, hip_pitch, knee, ankle)
    5-8 : neck/head (neck_pitch, head_pitch, head_yaw, head_roll)
    9-13: right leg (hip_yaw, hip_roll, hip_pitch, knee, ankle)
"""

import math
from copy import deepcopy

# Symmetry
ENABLE_SYMMETRY = False

# ── Domain randomisation (matched to the velocity env for sim2real parity) ────
ENABLE_COM_RANDOMIZATION             = True
ENABLE_HEAD_COM_RANDOMIZATION        = True   # match velocity: randomize head-assembly CoM
ENABLE_KP_RANDOMIZATION              = False  # match velocity (OFF)
ENABLE_KD_RANDOMIZATION              = False  # match velocity (OFF)
ENABLE_MASS_INERTIA_RANDOMIZATION    = True   # match velocity: dr.pseudo_inertia (mass+inertia)
ENABLE_JOINT_FRICTION_RANDOMIZATION  = True   # match velocity: FrictionDRBamActuator.friction_scale
ENABLE_ARMATURE_RANDOMIZATION        = True   # match velocity: reflected rotor inertia
ENABLE_VELOCITY_PUSHES               = True
ENABLE_IMU_ORIENTATION_RANDOMIZATION = True   # match velocity: obs-level per-env misalignment
ENABLE_ENCODER_BIAS                  = True   # match velocity: per-env joint encoder offset (actor obs)

# ── Ranges (matched to the velocity env) ──────────────────────────────────────
COM_RANDOMIZATION_RANGE             = 0.003           # ramped to 0.015 via com_range curriculum
HEAD_COM_RANDOMIZATION_RANGE        = 0.003           # ramped to 0.01 via head_com_range curriculum
MASS_INERTIA_RANDOMIZATION_RANGE    = (0.95, 1.05)
ARMATURE_RANDOMIZATION_RANGE        = (0.9, 1.1)
JOINT_FRICTION_RANDOMIZATION_RANGE  = (0.9, 1.1)
ENCODER_BIAS_RANGE                  = (-0.015, 0.015)
KP_RANDOMIZATION_RANGE              = (0.85, 1.15)    # unused (kp DR off)
KD_RANDOMIZATION_RANGE              = (0.9, 1.1)      # unused (kd DR off)
VELOCITY_PUSH_INTERVAL_S            = (3.0, 6.0)
# Final magnitude matches velocity's ±0.3 but the ramp is DELAYED (see the
# push_magnitude curriculum): the sit env's lesson — pushes mid-descent before
# the transition motions have consolidated make the policy unlearn them and
# converge to "just stand doing nothing".
VELOCITY_PUSH_RANGE                 = (-0.3, 0.3)
IMU_ORIENTATION_RANDOMIZATION_ANGLE = 6.0  # match velocity (obs-level, zero-centered random axis)

# Episode length: room for 2-3 posture segments (dwell 3.5-6.5 s each), i.e.
# at least one full sit → rest → rise → rest cycle per episode.
EPISODE_LENGTH_S = 12.0
# Dwell time in each commanded posture before a resample may flip it. The
# lower bound must comfortably exceed a gentle transition (~1.5 s) plus some
# rest, so "arrive, then hold still" is always trained.
POSTURE_DWELL_S  = (3.5, 6.5)
# Probability a resample commands SIT (vs STAND). 0.5 → all four combinations
# of (reset state × command) get equal coverage, including both holds.
SIT_PROB         = 0.5

# ── SIT keyframe (joint_pos index → angle in rad). Single fixed target. ─────
# STABILITY-VERIFIED 2026-07-27 (sit env, scratchpad sweep_sit_pose2.py):
# knee ±1.35, hip_pitch = HOME ∓ 0.05 lean, ankle 0, hip_roll 0 settles at
# 3-5° tilt for 95-100% of noisy resets. The old keyframe (knee ±1.0472,
# hip_pitch HOME) is NOT statically stable — it tips to ~88° in 1 s and
# silently drove the sit env's whole hop/back-flop/plank exploit chain.
# If the robot or keyframe changes, RE-RUN THE SWEEP — verify tilt, not z.
# Keep in sync with microduck_sit_env_cfg.SITTING_TARGET_OVERRIDES and
# microduck_standup_env_cfg.SITTING_JOINT_OVERRIDES.
SITTING_TARGET_OVERRIDES = {
    1:   0.0,      # left  hip_roll   (HOME -0.0873)
    2:  -0.4079,   # left  hip_pitch  (HOME -0.4579; +0.05 = slight fwd lean)
    3:   1.35,     # left  knee       (HOME -0.0049)
    4:   0.0,      # left  ankle      (HOME +0.4530)
    # neck/head intentionally omitted → steered by the head_pose command.
    10:  0.0,      # right hip_roll   (HOME +0.0873)
    11:  0.4079,   # right hip_pitch  (HOME +0.4579)
    12: -1.35,     # right knee       (HOME +0.0049)
    13:  0.0,      # right ankle      (HOME -0.4530)
}

_LEG_JOINTS  = [0, 1, 2, 3, 4, 9, 10, 11, 12, 13]

# Trunk height targets (m) — both MEASURED in sim, never carried across robot
# or keyframe changes (sit run-1 / standup lessons).
STAND_Z = 0.115
SIT_Z   = 0.060

# Upright gating window for ``upright_while_tall``: full upright incentive
# above STAND_UPRIGHT_Z, fades to 0 at SIT_UPRIGHT_Z (committed to the sit).
# Blocks the "tip backward while still high" descent exploit; the always-on
# upright_linear floor covers the seated regime.
STAND_UPRIGHT_Z = 0.10
SIT_UPRIGHT_Z   = 0.075

# Target-ramp duration (s): the command term slews an internal target blend
# STAND↔SIT over this time, and the posture rewards track the MOVING target.
# THE anti-crash mechanism (run-1 failure: near-instant transitions). With a
# binary target, arriving early pays the full goal jackpot (~7/step) for
# every step saved, while the linear speed caps integrate to a bounded
# excess-distance cost (~50 total for an instant drop) — crashing won ~7×.
# With the ramp, being AHEAD of the setpoint zeroes the height/composite
# stack for the ramp remainder, so tracking the slow setpoint is the argmax.
# 55 mm over 2 s ≈ 0.028 m/s, comfortably under both caps below.
POSTURE_RAMP_S = 2.0

# Vertical-speed caps (m/s) — now BACKSTOPS for overshoot/bounce around the
# slewed target (see POSTURE_RAMP_S), not the primary gentleness mechanism.
# The rise cap is looser (rising against gravity needs some momentum to get
# over the heels) and is introduced by curriculum only after the rise motion
# has been discovered — see the rise_speed_weight curriculum.
MAX_DESCENT_SPEED = 0.05
MAX_RISE_SPEED    = 0.08

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs.mdp import dr
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers import (
    CurriculumTermCfg,
    EventTermCfg,
    ObservationTermCfg,
    RewardTermCfg,
    TerminationTermCfg,
)
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.rl import (
    RslRlOnPolicyRunnerCfg,
    RslRlModelCfg,
)
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.tasks.velocity import mdp
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise

from mjlab_microduck.robot.microduck_constants import MICRODUCK_STANDUP_ROBOT_CFG
from mjlab_microduck.tasks import mdp as microduck_mdp
from mjlab_microduck.tasks.microduck_velocity_env_cfg import (
    MICRODUCK_ROUGH_TERRAINS_CFG,
    HEAD_BODY_NAMES,
    HEAD_POSE_CMD_RESAMPLE_S,
)
from mjlab_microduck.tasks.symmetry import PpoWithSymmetryCfg, SYMMETRY_CFG


# ── RL runner config ──────────────────────────────────────────────────────────

