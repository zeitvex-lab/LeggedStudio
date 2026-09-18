"""Training algorithm implementations exposed by the MJLab adapter.

Layers live here:

1. **Capability registry** (``registry.py`` / ``ppo.py`` / ``off_policy.py``):
   the lightweight control-plane algorithm catalog (PPO/SAC/TD3) used by the
   API/Web/CLI, plus ``resolve(name)`` for plugin lookup.  No torch imports at
   module scope.
2. **Plugin layer** (``base.py`` / ``plugin_registry.py`` / ``registry.json`` +
   one package per family: ``cts`` / ``dreamwaq`` / ``amp`` / ``distill`` /
   ``him`` / ``hora`` / ``appo``): pluggable algorithms with a minimal
   four-method protocol.  Plugin families import the training stack and are
   therefore resolved lazily via ``plugin_registry.resolve_plugin`` —
   importing *this* package stays control-plane safe.
3. **Family main classes** (lazy): the per-family algorithm / model / plugin
   classes listed in ``_LAZY_EXPORTS`` are importable as package attributes
   (``from adapters.mjlab.algorithms import CtsPPO``) but only load their
   submodule on first access, so the control plane never pays for torch.

Adding an algorithm = create ``<name>/`` with ``__init__.py`` (plugin class),
``algorithms.py``, ``models.py``, ``config.py``, ``README.md``, then register
it in ``registry.json``.  No runner-side if/elif changes required.
"""

from __future__ import annotations

import importlib
from typing import Any

from .base import (
  BUILD_METHODS,
  METADATA_FIELDS,
  REGISTRY_SCHEMA_VERSION,
  AlgorithmPlugin,
  plugin_metadata,
  verify_plugin,
)
from .plugin_registry import (
  PluginRegistryError,
  bind_algorithm_to_runner_cfg,
  get_plugin_metadata,
  list_plugins,
  load_registry,
  plugin_variants,
  resolve_plugin,
  variant_entrypoints,
)

#: Family main classes importable as package attributes (lazy, torch deferred
#: to first access).  Maps class name -> submodule path below this package.
_LAZY_EXPORTS: dict[str, str] = {
  # cts
  "CtsActorCritic": "cts",
  "CtsActorModel": "cts",
  "CtsAlgorithm": "cts",
  "CtsAlgorithmConfig": "cts",
  "CtsCriticModel": "cts",
  "CtsPlugin": "cts",
  "CtsPPO": "cts",
  "CtsStudentActorModel": "cts",
  # dreamwaq
  "DreamWaQActorCritic": "dreamwaq",
  "DreamWaQActorModel": "dreamwaq",
  "DreamWaQAlgorithm": "dreamwaq",
  "DreamWaQAlgorithmConfig": "dreamwaq",
  "DreamWaQPlugin": "dreamwaq",
  "DreamWaQPPO": "dreamwaq",
  "DreamWaQVAE": "dreamwaq",
  # amp
  "AmpAlgorithm": "amp",
  "AmpAlgorithmConfig": "amp",
  "AmpDiscriminator": "amp",
  "AmpPlugin": "amp",
  "AmpPPO": "amp",
  # distill
  "DistillAlgorithmConfig": "distill",
  "DistillPlugin": "distill",
  "StudentActorModel": "distill",
  "TeacherActorModel": "distill",
  "TeacherStudentActorCritic": "distill",
  "TeacherStudentAlgorithm": "distill",
  "TeacherStudentPPO": "distill",
  "Go2AuxiliaryPPO": "common.auxiliary_ppo",
  # him
  "HIMActorCritic": "him",
  "HIMEstimator": "him",
  "HIMPPO": "him",
  "HIMPlugin": "him",
  "HIMRolloutStorage": "him",
  "HimAlgorithmConfig": "him",
  # hora
  "HoraActorModel": "hora",
  "HoraAlgorithmConfig": "hora",
  "HoraCriticModel": "hora",
  "HoraLatentDistiller": "hora",
  "HoraPlugin": "hora",
  "HoraPPO": "hora",
  "HoraRolloutStorage": "hora",
  "HoraSharedActorCritic": "hora",
  # appo
  "APPOActor": "appo",
  "APPOLearner": "appo",
  "APPOCritic": "appo",
  "AppoActorCritic": "appo",
  "AppoAlgorithmConfig": "appo",
  "AppoPlugin": "appo",
  "vtrace_advantages": "appo",
}


def __getattr__(name: str) -> Any:
  """PEP 562 lazy export: load a family submodule on first attribute access."""
  submodule = _LAZY_EXPORTS.get(name)
  if submodule is None:
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
  return getattr(importlib.import_module(f"{__name__}.{submodule}"), name)


def __dir__() -> list[str]:
  return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
  "AlgorithmPlugin",
  "BUILD_METHODS",
  "METADATA_FIELDS",
  "PluginRegistryError",
  "REGISTRY_SCHEMA_VERSION",
  "bind_algorithm_to_runner_cfg",
  "get_plugin_metadata",
  "list_plugins",
  "load_registry",
  "plugin_metadata",
  "plugin_variants",
  "resolve_plugin",
  "variant_entrypoints",
  "verify_plugin",
]
