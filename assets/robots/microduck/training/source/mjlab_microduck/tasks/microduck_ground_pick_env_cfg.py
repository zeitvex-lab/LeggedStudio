"""Microduck ground pick task.

Episodic policy that crouches to bring its mouth tip AS CLOSE AS POSSIBLE to the
ground WITHOUT touching it (correctly oriented, mouth pointing down), then
returns to a clean standing pose — all while remaining stable and robust to
pushes.  The obs/action spaces are identical to the walking policy so the two
can be switched at runtime with a single key-press.

Objectif espace-tâche (pas de pose DOWN) : mouth_ground_proximity tire la bouche
vers le sol, head_impact_penalty (fort) interdit le contact -> équilibre = bouche
juste au-dessus ; mouth_perpendicular_to_ground l'oriente vers le bas.

Phase encoding (in the command slot, 3-D):
    command = [cos(2π·phase), sin(2π·phase), 0]
    phase ∈ [0, 0.5]  → approach (reward mouth going down)
    phase ∈ [0.5, 1]  → return   (reward returning to standing pose)

Phase is randomised per env on episode reset to de-correlate environments and
avoid synchronised oscillations.  PERIOD = 4 s (2 s down + 2 s up).

── mjlab 1.3.0 + canonical BAM ────────────────────────────────────────────────
Migrated to match the velocity env's sim2real machinery: fixed (non-accumulating)
CoM / head-CoM / mass-inertia / friction / armature DR, obs-level IMU misalignment,
encoder-bias, obs normalization. The task-specific REGULARIZATION is deliberately
kept HEAVIER than velocity's (slow careful reaching wants more damping than
walking) — see the regularisation block.
"""

import math
from copy import deepcopy

# Symmetry — disabled for v1.5: SYMMETRY_CFG's _OBS_PERM is hardcoded for the
# old 51D obs layout and breaks on the new 61D obs (which includes the
# head_command/body_command padding). All v1.5 envs run with symmetry off
# until SYMMETRY_CFG gets rewritten for the new obs structure.
ENABLE_SYMMETRY = False

# ── Domain randomisation toggles (matched to the velocity env) ────────────────
ENABLE_COM_RANDOMIZATION             = True
ENABLE_HEAD_COM_RANDOMIZATION        = True
ENABLE_KP_RANDOMIZATION              = False  # off, like velocity
ENABLE_KD_RANDOMIZATION              = False
ENABLE_MASS_INERTIA_RANDOMIZATION    = True
ENABLE_JOINT_FRICTION_RANDOMIZATION  = True   # scales BAM friction budget per-env
ENABLE_ARMATURE_RANDOMIZATION        = True   # reflected rotor inertia (affects BAM)
ENABLE_VELOCITY_PUSHES               = True
ENABLE_IMU_ORIENTATION_RANDOMIZATION = True   # applied at obs level (per-env rotation)
ENABLE_ENCODER_BIAS                  = True   # actor obs sees joint_pos + per-env bias

# ── Ranges (matched to the velocity env) ──────────────────────────────────────
COM_RANDOMIZATION_RANGE          = 0.003  # ±3mm initial, ramped via curriculum
HEAD_COM_RANDOMIZATION_RANGE     = 0.003  # ±3mm initial, ramped via curriculum
MASS_INERTIA_RANDOMIZATION_RANGE = (0.95, 1.05)
KP_RANDOMIZATION_RANGE           = (0.85, 1.15)
KD_RANDOMIZATION_RANGE           = (0.9, 1.1)
JOINT_FRICTION_RANDOMIZATION_RANGE = (0.9, 1.1)
ARMATURE_RANDOMIZATION_RANGE     = (0.9, 1.1)
VELOCITY_PUSH_INTERVAL_S         = (3.0, 6.0)
VELOCITY_PUSH_RANGE              = (-0.15, 0.15)  # geste quasi-statique -> pushes doux (±0.3 le faisait tomber même droit)
IMU_ORIENTATION_RANDOMIZATION_ANGLE = 6.0       # match velocity (was 1.0)
ENCODER_BIAS_RANGE               = (-0.015, 0.015)

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
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise

from mjlab_microduck.robot.microduck_constants import MICRODUCK_GROUND_PICK_ROBOT_CFG
from mjlab_microduck.tasks import mdp as microduck_mdp
from mjlab_microduck.tasks.microduck_velocity_env_cfg import (
    MICRODUCK_ROUGH_TERRAINS_CFG,
    HEAD_BODY_NAMES,
)
from mjlab_microduck.tasks.symmetry import PpoWithSymmetryCfg, SYMMETRY_CFG


# ── Profil de phase SEGMENTÉ (durées indépendantes) ──────────────────────────
# Au lieu de la pondération sinusoïdale (qui couple descente/palier/remontée),
# on gate les rewards par un profil à 4 segments : descente et remontée LENTES,
# palier bas COURT, repos debout long.
# Durées à GP_PERIOD = 4 s :
#   descente   [0, DESCENT_END)        1.5 s  transition STAND->bas
#   palier bas [DESCENT_END, HOLD_END) 0.2 s  effleure (court)
#   remontée   [HOLD_END, RISE_END)    1.5 s  transition bas->STAND
#   repos      [RISE_END, 1)           0.8 s  debout
# ⚠️ RISE_END=0.80 > coupure φ=0.7 du script infer_policy : la remontée n'est
# complète que si le slot joue jusqu'à φ~1.0 (toute la période). Vérifier la
# fenêtre réelle du runtime.  ⚠️ --ground-pick-period au déploiement = 4.0.
GP_PERIOD    = 4.0
DESCENT_END  = 0.375
HOLD_END     = 0.425
RISE_END     = 0.80


# ── RL runner config ──────────────────────────────────────────────────────────

