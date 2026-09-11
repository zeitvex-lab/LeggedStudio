"""Framework-neutral semantic contract for the first RoboLab robot."""

from __future__ import annotations

from robolab.core.contracts import TensorContract


UNITREE_A1_JOINT_ORDER = (
    "FL_hip_joint",
    "RL_hip_joint",
    "FR_hip_joint",
    "RR_hip_joint",
    "FL_thigh_joint",
    "RL_thigh_joint",
    "FR_thigh_joint",
    "RR_thigh_joint",
    "FL_calf_joint",
    "RL_calf_joint",
    "FR_calf_joint",
    "RR_calf_joint",
)

VELOCITY_OBSERVATION = TensorContract(
    name="velocity_observation",
    shape=(45,),
    semantics="Isaac Gym A1 velocity-policy observation in fixed legged_gym order",
)
ACTION = TensorContract(
    name="joint_position_offset",
    shape=(12,),
    semantics="normalized position offsets in UNITREE_A1_JOINT_ORDER",
)
CONTROL_DT = 0.02
