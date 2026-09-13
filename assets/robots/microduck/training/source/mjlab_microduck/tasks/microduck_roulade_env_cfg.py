"""Microduck forward-roll (roulade) task — attempt 3, run 2.

Episodic policy: robot starts standing, rolls forward over the flat top of
its head, and lands back on its feet. Triggered at deployment like sit/standup
(policy switch = roll starts immediately; no phase clock, no reference motion).

RUN-2 REWORK (run 1 learned a violent ballistic "breakdance" whip — optimal
under the run-1 rewards: same 2π, sooner, no cost): rotation now only counts
while the robot touches the ground (support-gated accumulator — a roulade
never leaves the floor), the landing annuity requires an over-the-head
contact latch, paid progress rate is capped at 3 rad/s (faster forfeits the
excess), an overspeed penalty taxes |ω| > 4 rad/s, and the impact/smoothness
penalties are active from step 0 (discovery in this env is easy; style is
the scarce resource, not exploration).

Design (see the roulade section of mdp.py for the full history):
  • ONE dense progress signal — paid increments of the max-so-far cumulative
    forward rotation (potential-based: full roll pays 2π worth total, camping
    anywhere pays zero per step).
  • Landing rewards gated on ROLL COMPLETION (rotation frontier ≥ ~260°), not
    on a clock — "do nothing" earns nothing, the standing spawn cannot farm
    them, and no upright/height pressure ever opposes the flip.
  • Reverse curriculum via mid-roll spawns (the trick that fixed face-up
    recovery in standup): a slice of episodes starts 50°–185° into the roll,
    tucked, with forward angular momentum, accumulator pre-set to the spawn
    angle. The second half of a roulade IS the face-up recovery problem, which
    we know is learnable.
  • Élan hook for later: reset_roulade_state.forward_vel_range gives standing
    spawns an initial forward base velocity — set ROULADE_FORWARD_VEL_RANGE
    to e.g. (0.0, 0.3) to train rolls out of a walk. (0, 0) = standstill-only.

DR / obs / regularisers mirror the standup env (velocity sim2real parity),
with the motion-blockers (body_ang_vel, |a_z|, arrival damping) kept near zero
during discovery and introduced late by curriculum — the roll IS a large
angular-velocity, large-impact event; taxing attempts prevents discovery
(proven twice on standup).
"""

import math
from copy import deepcopy

# Symmetry — the roll is sagittal / left-right symmetric; the mirror loss
# directly fights the sideways-collapse failure seen in run 2. Enabled after
# migrating symmetry.py to the 61-dim layout (2026-08-13, includes the
# "policy" → "actor" output-key fix; roulade is the first env to use it).
ENABLE_SYMMETRY = True

# ── Domain randomisation (matched to standup/velocity for sim2real parity) ───
ENABLE_COM_RANDOMIZATION             = True
ENABLE_HEAD_COM_RANDOMIZATION        = True
ENABLE_KP_RANDOMIZATION              = False  # match velocity (OFF)
ENABLE_KD_RANDOMIZATION              = False  # match velocity (OFF)
ENABLE_MASS_INERTIA_RANDOMIZATION    = True
ENABLE_JOINT_FRICTION_RANDOMIZATION  = True
ENABLE_ARMATURE_RANDOMIZATION        = True
ENABLE_IMU_ORIENTATION_RANDOMIZATION = True
ENABLE_ENCODER_BIAS                  = True

# ── Ranges (matched to the standup env) ───────────────────────────────────────
COM_RANDOMIZATION_RANGE             = 0.003   # ramped to 0.015 via curriculum
HEAD_COM_RANDOMIZATION_RANGE        = 0.003   # ramped to 0.01 via curriculum
MASS_INERTIA_RANDOMIZATION_RANGE    = (0.95, 1.05)
ARMATURE_RANDOMIZATION_RANGE        = (0.9, 1.1)
JOINT_FRICTION_RANDOMIZATION_RANGE  = (0.9, 1.1)
ENCODER_BIAS_RANGE                  = (-0.015, 0.015)
KP_RANDOMIZATION_RANGE              = (0.85, 1.15)  # unused (kp DR off)
KD_RANDOMIZATION_RANGE              = (0.9, 1.1)    # unused (kd DR off)
IMU_ORIENTATION_RANDOMIZATION_ANGLE = 6.0

# Episode: a CONTROLLED roll takes ~2 s + rise ~1.5 s + settle. Run-3: 4 → 5 s
# (4 s left no room for the rise after a paced roll).
EPISODE_LENGTH_S = 5.0

# Empirically-measured standing trunk height (standup lesson: don't guess).
STAND_Z = 0.115

# ── Élan (run-up) hook ────────────────────────────────────────────────────────
# (0, 0) = roll from a standstill (run 1). Widen to e.g. (0.0, 0.3) to train
# rolls entered with forward momentum — standing spawns then get a random
# initial forward base velocity, approximating a hand-off from the walking
# policy without simulating the walk itself.
ROULADE_FORWARD_VEL_RANGE = (0.0, 0.0)

# ── Mid-roll spawn (reverse curriculum) ───────────────────────────────────────
# 90° = balanced on the head, 180° = on the back, 270° = supine, ~340° = seated
# leaning back, >260° opens the landing gate. Run-3 change: MAX widened
# 185° → 340° — run-2 wandb showed the second half of the roll (supine →
# seated → rise) was never spawned and never learned; spawns past ~300° open
# the landing gate at birth, giving dense on-policy data on the crouch→stand
# last mile (the velstand run-5 crouch-basin lesson).
MIDROLL_PITCH_MIN   = math.radians(50.0)
MIDROLL_PITCH_MAX   = math.radians(340.0)
MIDROLL_OMEGA_RANGE = (0.0, 3.0)   # rad/s forward momentum at spawn
# Tuck anchor: legs folded (crouch-anchor values from the velstand crouch
# reset) + CHIN TUCK (run-5: neck_pitch −1 / head_pitch +1 puts the flat head
# top squarely on the floor — measured axis_z −0.99 vs +0.6 for the passive
# face-plant; the head-top latch requires this, so mid-roll spawns must
# demonstrate the tucked configuration). Servo-index keyed; mid-roll spawns
# lerp HOME→tuck by a per-env factor.
TUCK_OVERRIDES = {
    2:  -1.15,  # left  hip_pitch
    3:   1.25,  # left  knee
    4:   1.05,  # left  ankle
    5:  -1.0,   # neck_pitch  (chin tuck)
    6:   1.0,   # head_pitch  (chin tuck)
    11:  1.15,  # right hip_pitch
    12: -1.25,  # right knee
    13: -1.05,  # right ankle
}

# Rotation thresholds (rad) for the state-based gates.
LANDING_GATE_LO = math.radians(260.0)
LANDING_GATE_HI = math.radians(330.0)
RISE_GATE_LO    = math.radians(180.0)
RISE_GATE_HI    = math.radians(260.0)

_LEG_JOINTS  = [0, 1, 2, 3, 4, 9, 10, 11, 12, 13]

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
from mjlab_microduck.tasks.microduck_velocity_env_cfg import HEAD_BODY_NAMES
from mjlab_microduck.tasks.symmetry import PpoWithSymmetryCfg, SYMMETRY_CFG


# ── RL runner config ──────────────────────────────────────────────────────────

