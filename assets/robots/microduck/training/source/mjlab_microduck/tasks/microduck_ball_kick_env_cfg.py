"""Microduck BallKick task — kick a ball forward with one foot (KICK_FOOT flag).

Episodic policy: the robot starts STANDING (HOME pose + noise) with a 70mm /
15g ball sitting just in front of its kicking foot (KICK_FOOT below — train a
right-footed and a left-footed policy as two separate runs). The goal is to
kick the ball forward (robot's heading at reset) at BALL_TARGET_SPEED while
keeping balance and staying robust to external pushes, then settle back into
a clean stand.

Key design decisions:
  - The policy is BLIND to the ball (no ball obs in the actor): the real robot
    has no ball sensing — the operator aims the robot at the ball. Robustness
    to placement error comes from ±2cm ball-position DR at reset instead. The
    CRITIC does see ball pos/vel (asymmetric actor-critic) so the value
    function can anticipate the kick payoff.
  - No phase command: the kick reward is available from t=0 and an earlier
    kick collects more ball-rolling reward, so the policy kicks immediately.
    At deployment: hard ONNX swap to this policy (à la jump/ground-pick), it
    kicks, then auto-swap back after ~2s.
  - Right-foot kick is enforced geometrically + economically: the ball spawns
    at the right toe, and an always-on LEFT-foot-grounded reward makes the
    left leg the support leg (lifting it costs reward every step; anti-hop).
  - Kick reward is LINEAR in ball forward speed (clamped at 5 m/s), not a
    saturating tanh — "as hard as possible" needs gradient at high speeds.
  - Obs layout is the unified 61D actor layout (twist + zero-padded head/body
    command slots) so the runtime can hard-swap ONNX files with one buffer.

DR / noise / regularization: velocity-parity, copied from the standup env
(which is itself matched to velocity — the recipe with proven transfer).
Task reward mass ~10 ≈ velocity's ~11, so the shared regularizer weights act
at the same relative strength.
"""

import math
from copy import deepcopy

# ── Kicking foot: "right" or "left" ───────────────────────────────────────────
# Flips the ball spawn side and the support-foot (anti-hop) sensor. Everything
# else is left/right symmetric (HOME pose has mirrored signs). Train the two
# policies as separate runs — wandb experiment/run name follows this flag.
KICK_FOOT = "right"
assert KICK_FOOT in ("right", "left")

# Symmetry — must stay OFF: the kick task is inherently one-footed.
ENABLE_SYMMETRY = False

# ── Domain randomisation (matched to velocity / standup) ─────────────────────
ENABLE_COM_RANDOMIZATION             = True
ENABLE_HEAD_COM_RANDOMIZATION        = True
ENABLE_KP_RANDOMIZATION              = False
ENABLE_KD_RANDOMIZATION              = False
ENABLE_MASS_INERTIA_RANDOMIZATION    = True
ENABLE_JOINT_FRICTION_RANDOMIZATION  = True
ENABLE_ARMATURE_RANDOMIZATION        = True
ENABLE_VELOCITY_PUSHES               = True
ENABLE_IMU_ORIENTATION_RANDOMIZATION = True
ENABLE_ENCODER_BIAS                  = True

# ── Ranges (matched to velocity / standup) ───────────────────────────────────
COM_RANDOMIZATION_RANGE             = 0.003           # ramped to 0.015 via curriculum
HEAD_COM_RANDOMIZATION_RANGE        = 0.003           # ramped to 0.01 via curriculum
MASS_INERTIA_RANDOMIZATION_RANGE    = (0.95, 1.05)
ARMATURE_RANDOMIZATION_RANGE        = (0.9, 1.1)
JOINT_FRICTION_RANDOMIZATION_RANGE  = (0.9, 1.1)
ENCODER_BIAS_RANGE                  = (-0.015, 0.015)
KP_RANDOMIZATION_RANGE              = (0.85, 1.15)    # unused (kp DR off)
KD_RANDOMIZATION_RANGE              = (0.9, 1.1)      # unused (kd DR off)
VELOCITY_PUSH_INTERVAL_S            = (3.0, 6.0)
VELOCITY_PUSH_RANGE                 = (-0.3, 0.3)     # ramped in via push curriculum
IMU_ORIENTATION_RANDOMIZATION_ANGLE = 6.0

# ── Task constants ────────────────────────────────────────────────────────────
# Long enough for kick + several seconds of ball-rolling reward + settle-back.
EPISODE_LENGTH_S = 5.0

# 70mm-diameter / 15g ball (see ball.xml).
BALL_RADIUS = 0.035
# Nominal ball-center offset in the robot's yaw frame. Measured at HOME: foot
# centers at (0, ±0.042), toe tip x≈0.034. With radius 0.035 and ±0.015 noise
# the ball's rear surface is at worst x=0.040 → always ≥6mm clear of the toe.
# (0.08 ± 0.02 allowed spawn-penetration with the toe: the solver ejected the
# ball at reset — free "kick" reward with no kick.)
# The lateral sign follows the kicking foot (right = -y, left = +y).
BALL_OFFSET_X     = 0.09
BALL_OFFSET_ABS_Y = 0.042
# Uniform ± placement noise per axis. This is the DR that makes the BLIND
# policy's swing robust to real-world aiming error.
BALL_POS_NOISE_XY = 0.015

# Target kick speed (m/s). The first trained policy (linear reward capped at
# 5 m/s) kicked much harder than needed — this tames the kick to a gentle,
# controlled tap. NOTE: the kick reward weights below are scaled to keep the
# at-target payoff ≈ +3/step regardless of this value (weight ≈ 3/target for
# the capped term) — if you change the target, rescale the weights with it.
BALL_TARGET_SPEED = 1.0

# Trunk standing height (measured natural equilibrium at HOME — see standup env).
STAND_Z = 0.115

_LEG_JOINTS  = [0, 1, 2, 3, 4, 9, 10, 11, 12, 13]
_NECK_JOINTS = [5, 6, 7, 8]

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

from mjlab_microduck.robot.microduck_constants import (
    MICRODUCK_BALL_CFG,
    MICRODUCK_STANDUP_ROBOT_CFG,
)
from mjlab_microduck.tasks import mdp as microduck_mdp
from mjlab_microduck.tasks.microduck_velocity_env_cfg import HEAD_BODY_NAMES
from mjlab_microduck.tasks.symmetry import PpoWithSymmetryCfg, SYMMETRY_CFG


# ── RL runner config ──────────────────────────────────────────────────────────

