"""Algorithm plugin protocol (B: algorithm plugin layer).

Algorithms are pluggable: any family (CTS / DreamWaQ / AMP / distill, and
beyond -- UniLab-style third-party algorithms) implements this minimal
interface and registers itself in ``registry.json`` to become trainable
through the standard mjlab/RSL-RL chain.

Design constraints:

- **Zero heavy imports**: this module must stay importable in the lightweight
  control plane (no torch/mjlab), so registry tooling and fail-closed checks
  can run everywhere.  Torch-typed annotations are strings under
  ``from __future__ import annotations`` and only evaluated by type checkers.
- **Four build methods**: ``build_actor_critic`` / ``build_storage`` /
  ``build_optimizer`` / ``export_onnx``.  The last one exists so a plugin can
  self-certify its deployment artifact (B44 lineage: exported ONNX must carry
  the same contract metadata as the runner-produced artifact).
- **Metadata as class attributes**: ``name`` / ``upstream`` / ``license`` /
  ``supported_obs_types``.  The registry file mirrors these for static
  consumers; ``plugin_registry.py`` cross-checks the two so they cannot drift.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - static analysis only
  from collections.abc import Iterable, Mapping

  import torch
  from torch import nn

#: The four construction/interop methods every plugin must provide.
BUILD_METHODS: tuple[str, ...] = (
  "build_actor_critic",
  "build_storage",
  "build_optimizer",
  "export_onnx",
)

#: Metadata class attributes every plugin must declare.
METADATA_FIELDS: tuple[str, ...] = (
  "name",
  "upstream",
  "license",
  "supported_obs_types",
)

#: Registry schema stamp (mirrors ``registry.json``).
REGISTRY_SCHEMA_VERSION = "algorithm-plugin-registry-1.0"


class AlgorithmPlugin(abc.ABC):
  """Minimal contract that makes an algorithm usable by the training chain.

  A plugin is a stateless factory: the runner/worker asks it for the actor
  critic module, a rollout-storage-compatible container, an optimizer over the
  model parameters, and an ONNX export of a trained (or fresh) policy.  All
  hyper-parameters arrive via the ``cfg`` mapping (the family ``config.py``
  dataclass is the schema), so one plugin class serves every robot profile.
  """

  # ---- metadata (class attributes; mirrored in registry.json) ----
  name: str
  """Short registry key, e.g. ``"cts"``. Must match the registry.json key."""

  upstream: str
  """Human-readable provenance of the algorithm implementation."""

  license: str
  """SPDX identifier or explicit provenance note for the upstream code."""

  supported_obs_types: tuple[str, ...]
  """Observation group names the algorithm can consume (actor/critic/history/...)."""

  # ---- construction ----
  @abc.abstractmethod
  def build_actor_critic(
    self,
    obs_dim: int,
    action_dim: int,
    cfg: "Mapping[str, Any] | None" = None,
  ) -> "nn.Module":
    """Build the family actor-critic for the given observation/action widths."""

  @abc.abstractmethod
  def build_storage(self, cfg: "Mapping[str, Any] | None" = None) -> Any:
    """Build a rollout storage compatible with the mjlab/RSL-RL runner loop."""

  @abc.abstractmethod
  def build_optimizer(
    self,
    params: "Iterable[torch.nn.Parameter]",
    cfg: "Mapping[str, Any] | None" = None,
  ) -> "torch.optim.Optimizer":
    """Build the training optimizer over the given parameters."""

  # ---- deployment artifact (B44 self-certification) ----
  @abc.abstractmethod
  def export_onnx(self, path: str, model: "nn.Module | None" = None) -> str:
    """Export ``model`` (or a freshly built default policy) to ONNX.

    Returns the absolute path of the written artifact.  Implementations must
    produce an ONNX-safe deterministic wrapper, not a stochastic training
    graph.
    """


def plugin_metadata(plugin: "AlgorithmPlugin | type[AlgorithmPlugin]") -> dict[str, Any]:
  """Return the four metadata fields as a plain dict (registry cross-check)."""
  return {
    "name": plugin.name,
    "upstream": plugin.upstream,
    "license": plugin.license,
    "supported_obs_types": list(plugin.supported_obs_types),
  }


def verify_plugin(obj: Any) -> list[str]:
  """Runtime protocol-compliance check; returns a list of violations.

  Empty list means the object satisfies the plugin contract (four build
  methods callable + four metadata fields populated).  Used by tests and by
  ``plugin_registry.resolve_plugin`` as a fail-closed gate.
  """
  violations: list[str] = []
  for method in BUILD_METHODS:
    attribute = getattr(obj, method, None)
    if attribute is None:
      violations.append(f"missing build method: {method}")
    elif not callable(attribute):
      violations.append(f"build method is not callable: {method}")
  for field in METADATA_FIELDS:
    value = getattr(obj, field, None)
    if value is None:
      violations.append(f"missing metadata field: {field}")
    elif field == "supported_obs_types" and not tuple(value):
      violations.append("supported_obs_types must be non-empty")
  if isinstance(obj, type) and not issubclass(obj, AlgorithmPlugin):
    violations.append("plugin class does not subclass AlgorithmPlugin")
  return violations


__all__ = [
  "BUILD_METHODS",
  "METADATA_FIELDS",
  "REGISTRY_SCHEMA_VERSION",
  "AlgorithmPlugin",
  "plugin_metadata",
  "verify_plugin",
]
