"""Thin re-export shim: algorithm model classes moved to the plugin layer.

Canonical implementations now live in
``adapters/mjlab/algorithms/{cts,dreamwaq,amp,distill}/models.py`` (shared
building blocks in ``adapters/mjlab/algorithms/common/modules.py``).  Every
``local_tasks.learning.models.<Class>`` entrypoint string keeps resolving to
the exact same class objects, so runner configs, the training catalog and the
legacy mjlab alias map are unaffected.
"""

from __future__ import annotations

from adapters.mjlab.algorithms.amp.models import AmpDiscriminator
from adapters.mjlab.algorithms.common.modules import (
  Go2ClampedGaussianDistribution,
  PolicyOutput,
  _GaussianPolicy,
  _activation,
  _mlp,
)
from adapters.mjlab.algorithms.cts.models import (
  CtsActorCritic,
  CtsActorModel,
  CtsCriticModel,
  CtsStudentActorModel,
)
from adapters.mjlab.algorithms.distill.models import (
  StudentActorModel,
  TeacherActorModel,
  TeacherStudentActorCritic,
)
from adapters.mjlab.algorithms.dreamwaq.models import (
  DreamWaQActorCritic,
  DreamWaQActorModel,
  DreamWaQVAE,
)

__all__ = [
  "AmpDiscriminator",
  "CtsActorCritic",
  "CtsActorModel",
  "CtsCriticModel",
  "CtsStudentActorModel",
  "DreamWaQActorCritic",
  "DreamWaQActorModel",
  "DreamWaQVAE",
  "Go2ClampedGaussianDistribution",
  "PolicyOutput",
  "StudentActorModel",
  "TeacherActorModel",
  "TeacherStudentActorCritic",
]
