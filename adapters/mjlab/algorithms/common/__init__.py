"""Shared building blocks for the algorithm plugins.

Moved verbatim from ``local_tasks/learning`` so the plugin layer has no
reverse dependency on any robot's task package; ``local_tasks`` now re-imports
these symbols to keep its legacy entrypoints resolvable.
"""

from .auxiliary_ppo import Go2AuxiliaryPPO, OptimizerMixin
from .motion import (
  GO2_JOINT_NAMES,
  Go2MotionLoader,
  Go2MotionTrajectory,
  joint_permutation,
)
from .storage import (
  Go2AmpReplayBuffer,
  Go2RolloutStorage,
  Go2RunningNormalizer,
  Go2Transition,
)

__all__ = [
  "GO2_JOINT_NAMES",
  "Go2AmpReplayBuffer",
  "Go2AuxiliaryPPO",
  "Go2MotionLoader",
  "Go2MotionTrajectory",
  "Go2RolloutStorage",
  "Go2RunningNormalizer",
  "Go2Transition",
  "OptimizerMixin",
  "joint_permutation",
]
