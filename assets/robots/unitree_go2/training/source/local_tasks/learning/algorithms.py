"""Thin re-export shim: CTS/DreamWaQ/AMP/TS algorithms moved to the plugin layer.

Canonical implementations now live in
``adapters/mjlab/algorithms/{cts,dreamwaq,amp,distill}/``.  This module (and
every ``local_tasks.learning.algorithms.<Class>`` entrypoint string consumed by
``unitree_go2_custom_runner_cfg`` / the training catalog / legacy mjlab
aliases) keeps resolving to the exact same class objects.
"""

from __future__ import annotations

from adapters.mjlab.algorithms.amp.algorithms import AmpAlgorithm, AmpPPO
from adapters.mjlab.algorithms.common.auxiliary_ppo import (
  Go2AuxiliaryPPO,
  OptimizerMixin as _OptimizerMixinAlias,
)
from adapters.mjlab.algorithms.cts.algorithms import AmpCtsPPO, CtsAlgorithm, CtsPPO
from adapters.mjlab.algorithms.distill.algorithms import (
  AmpTeacherStudentPPO,
  TeacherStudentAlgorithm,
  TeacherStudentPPO,
)
from adapters.mjlab.algorithms.dreamwaq.algorithms import (
  AmpDreamWaQPPO,
  DreamWaQAlgorithm,
  DreamWaQPPO,
)

#: Legacy private name preserved for any historical importer.
_OptimizerMixin = _OptimizerMixinAlias

__all__ = [
  "AmpAlgorithm",
  "AmpCtsPPO",
  "AmpDreamWaQPPO",
  "AmpPPO",
  "AmpTeacherStudentPPO",
  "CtsAlgorithm",
  "CtsPPO",
  "DreamWaQAlgorithm",
  "DreamWaQPPO",
  "Go2AuxiliaryPPO",
  "TeacherStudentAlgorithm",
  "TeacherStudentPPO",
]
