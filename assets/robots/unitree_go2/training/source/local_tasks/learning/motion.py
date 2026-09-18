"""Thin re-export shim: the AMP motion loader moved to the plugin layer.

Canonical implementation lives in
``adapters/mjlab/algorithms/common/motion.py``.  Every
``local_tasks.learning.motion.<Symbol>`` entrypoint string keeps resolving to
the exact same objects.
"""

from __future__ import annotations

from adapters.mjlab.algorithms.common.motion import (
  GO2_JOINT_NAMES,
  Go2MotionLoader,
  Go2MotionTrajectory,
  joint_permutation,
)

__all__ = [
  "GO2_JOINT_NAMES",
  "Go2MotionLoader",
  "Go2MotionTrajectory",
  "joint_permutation",
]
