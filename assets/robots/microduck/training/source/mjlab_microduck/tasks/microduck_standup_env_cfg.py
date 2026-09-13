"""Microduck *stand* task (v1.5) — specialized: sitting pose → standing.

Episodic policy that gently rises from the sitting keyframe to the standing
keyframe. Companion to the sit env — together they form a clean sit↔stand
pair, each policy doing one direction.

Reset:  sitting keyframe (trunk z ≈ 0.07, knees/ankles bent, head at HOME).
Target: standing keyframe (trunk z ≈ 0.12, HOME joints).
Reward design (mirror of sit env): a single fixed target is rewarded from
t=0 to end of episode; gentleness is enforced via |a_z| only; smoothness is
enforced by the usual sim2real regularisers. No trajectory waypoints, no
episode-progress gating — the policy is free to discover its own rise path.

Body control (reintroduced 2026-07-29): once standing, the policy tracks a
commanded trunk delta [z, roll, pitch] from the nominal stand (the real
body_pose command in the previously zero-padded 6D obs slot). Kicks in at
iter 2500 via the body-control curricula at the bottom of this file, after
the ground_state_mix recovery curriculum has finished ramping.
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
COM_RANDOMIZATION_RANGE             = 0.003           # ramped to 0.015 via com_range curriculum (velocity's 2026-07 audit cap; was 0.02 here)
HEAD_COM_RANDOMIZATION_RANGE        = 0.003           # ramped to 0.01 via head_com_range curriculum
MASS_INERTIA_RANDOMIZATION_RANGE    = (0.95, 1.05)
ARMATURE_RANDOMIZATION_RANGE        = (0.9, 1.1)
JOINT_FRICTION_RANDOMIZATION_RANGE  = (0.9, 1.1)
ENCODER_BIAS_RANGE                  = (-0.015, 0.015)
KP_RANDOMIZATION_RANGE              = (0.85, 1.15)    # unused (kp DR off)
KD_RANDOMIZATION_RANGE              = (0.9, 1.1)      # unused (kd DR off)
VELOCITY_PUSH_INTERVAL_S            = (3.0, 6.0)
# Match velocity's ±0.3 (velocity was itself softened from ±0.5 in the 2026-07
# audit). The push curriculum below still ramps 0 → ±0.08 → this final value so
# the sit-rise bootstrap isn't shoved around from step 0 (velocity pushes at
# full strength from step 0, but it starts standing, not seated/prone).
VELOCITY_PUSH_RANGE                 = (-0.3, 0.3)
IMU_ORIENTATION_RANDOMIZATION_ANGLE = 6.0  # match velocity (was 2.0 — pre-audit value; real IMU has ~5° systematic pitch error + estimator drift, 2° trained too narrow a band)

# Episode length: long enough for a gentle rise + brief stabilisation.
EPISODE_LENGTH_S = 6.0

# ── Sitting source pose (asset.data.joint_pos index → angle in rad) ───────────
# Must match the *actual end-state* of the sit policy. Mirrors the sit env's
# SITTING_TARGET_OVERRIDES (microduck_sit_env_cfg.py) — the swept stable
# equilibrium pose (knee ±1.35 ≈ 77°, hip_pitch ∓0.4079 = slight fwd lean,
# ankles 0). Keep the two in sync: this reset IS the sit→stand hand-off.
# Neck/head intentionally omitted → reset stays at HOME so the standup policy
# starts from exactly where the sit policy converges.
# Articulation joint indices under mjlab 1.3.0 + canonical BAM. The passive jaw
# joints are NO LONGER part of the articulation (excluded from qpos), so the
# layout is the clean 14-joint order: 0-4 left leg, 5-8 neck/head, 9-13 right leg.
# (Previously passive_1/passive_2 sat at 9,10 and shifted the right leg to 11-15.)
SITTING_JOINT_OVERRIDES = {
    1:   0.0,      # left  hip_roll   (HOME -0.0873)
    2:  -0.4079,   # left  hip_pitch  (HOME -0.4579; +0.05 = slight fwd lean)
    3:   1.35,     # left  knee       (HOME -0.0049)
    4:   0.0,      # left  ankle      (HOME +0.4530)
    10:  0.0,      # right hip_roll   (HOME +0.0873)
    11:  0.4079,   # right hip_pitch  (HOME +0.4579)
    12: -1.35,     # right knee       (HOME +0.0049)
    13:  0.0,      # right ankle      (HOME -0.4530)
}

_LEG_JOINTS  = [0, 1, 2, 3, 4, 9, 10, 11, 12, 13]

# Trunk height targets (m).
# SIT_Z matches the sit env's measured seated equilibrium (trunk z at rest in
# the swept stable pose above). Was 0.07 (old robot); keep in sync with
# microduck_sit_env_cfg.py.
SIT_Z = 0.060
# STAND_Z = empirically-measured trunk z at the natural standing equilibrium
# (HOME joint pose, vertical trunk). Previously was 0.120 — 5 mm above
# what's mechanically reachable at HOME — which forced the policy into a
# back-lean compromise to satisfy the impossible height target. Measured
# via the velocity policy holding the robot still at zero command: 115 mm.
STAND_Z = 0.115

# ── Body pose command (reintroduced 2026-07-29) ───────────────────────────────
# Master toggle. OFF restores the previous env exactly: no body_pose command,
# zero-padded body_command obs slot (obs stays 61D either way), no tracking
# reward, no body-control curricula (including the conflict-relax stages on
# height_stand_sharp / upright_sharp / standing_composite).
ENABLE_BODY_CONTROL = True
# 6D command slot [x, y, z, roll, pitch, yaw] for obs parity with velocity/
# velstand, but only z/roll/pitch are tracked (axis_weights below) — the same
# 3 axes as the original standup body control and the runtime interface.
# x/y/yaw stay at a tiny "alive" range forever: the policy learns to ignore
# them (they're reward-uncorrelated noise) instead of leaving dead weights.
# z range is ASYMMETRIC: STAND_Z is the natural equilibrium at HOME, so there
# is plenty of crouch below it but only ~1 cm of leg extension above it.
# Angles capped at ±15°: velocity body-control run 1 showed ±20° trains
# twitchy/overdriven tilting.
BODY_CMD_MAX_Z_DOWN  = 0.04             # m, crouch below STAND_Z
BODY_CMD_MAX_Z_UP    = 0.030             # m, extend above STAND_Z
BODY_CMD_MAX_ANGLE   = math.radians(15)  # rad, trunk pitch/roll
BODY_CMD_ALIVE_XY    = 0.005             # m, permanent x/y noise range
BODY_CMD_ALIVE_ANGLE = 0.05              # rad, stage-0 / permanent-yaw range
# Exact-zero command probability at resample: keeps the deployment idle case
# ("stand at nominal, no command") trained (velocity run-1 lesson — uniform
# sampling never produces the all-zero command).
BODY_CMD_ZERO_PROB   = 0.3

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
    BODY_POSE_CMD_RESAMPLE_S,
)
from mjlab_microduck.tasks.symmetry import PpoWithSymmetryCfg, SYMMETRY_CFG


# ── RL runner config ──────────────────────────────────────────────────────────

