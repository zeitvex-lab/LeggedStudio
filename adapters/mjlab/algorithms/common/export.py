"""Shared ONNX export helper for algorithm plugins (B44 self-certification).

Plugins must be able to produce a deployment-grade ONNX artifact without the
mjlab runner: ``export_onnx(path)`` on the plugin builds an ONNX-safe
deterministic wrapper and writes it through this helper, so the exported
contract (input/output names, dynamic batch axes) matches what the runner-side
exporter produces for the same family.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import torch
from torch import nn


def export_onnx_module(
  module: nn.Module,
  path: str | Path,
  dummy_inputs: Sequence[torch.Tensor],
  input_names: Sequence[str],
  output_names: Sequence[str],
  dynamic_axes: dict[str, dict[int, str]] | None = None,
  opset_version: int = 17,
) -> str:
  """Export ``module`` to ONNX and return the absolute artifact path."""
  target = Path(path)
  target.parent.mkdir(parents=True, exist_ok=True)
  module = module.eval()
  with torch.no_grad():
    torch.onnx.export(
      module,
      tuple(dummy_inputs),
      str(target),
      input_names=list(input_names),
      output_names=list(output_names),
      dynamic_axes=dict(dynamic_axes or {}),
      opset_version=opset_version,
      dynamo=False,
    )
  return str(target.resolve())


def batch_axes(names: Sequence[str], outputs: Sequence[str]) -> dict[str, dict[int, str]]:
  """Standard dynamic batch axes for the given input/output names."""
  axes: dict[str, dict[int, str]] = {name: {0: "batch"} for name in names}
  for name in outputs:
    axes[name] = {0: "batch"}
  return axes


def first_device(module: nn.Module) -> torch.device:
  """Device of the module's first parameter/buffer (cpu when parameterless)."""
  for tensor in module.parameters():
    return tensor.device
  for tensor in module.buffers():
    return tensor.device
  return torch.device("cpu")


def zeros_like_on(module: nn.Module, inputs: Sequence[tuple[int, ...]]) -> tuple[Any, ...]:
  """Dummy zero inputs shaped ``inputs`` on the module's device."""
  device = first_device(module)
  return tuple(torch.zeros(shape, device=device) for shape in inputs)


__all__ = [
  "batch_axes",
  "export_onnx_module",
  "first_device",
  "zeros_like_on",
]
