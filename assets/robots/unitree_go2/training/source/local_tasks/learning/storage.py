"""Thin re-export shim: rollout storage moved to the plugin layer.

Canonical implementations live in
``adapters/mjlab/algorithms/common/storage.py``.  Every
``local_tasks.learning.storage.<Class>`` entrypoint string keeps resolving to
the exact same class objects.
"""

from __future__ import annotations

from adapters.mjlab.algorithms.common.storage import (
  Go2AmpReplayBuffer,
  Go2RolloutStorage,
  Go2RunningNormalizer,
  Go2Transition,
)

__all__ = [
  "Go2AmpReplayBuffer",
  "Go2RolloutStorage",
  "Go2RunningNormalizer",
  "Go2Transition",
]
