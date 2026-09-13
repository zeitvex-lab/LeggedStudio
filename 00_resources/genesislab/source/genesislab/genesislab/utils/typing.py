"""Common typing helpers and aliases used across GenesisLab."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple, TypeVar

import torch

Tensor = torch.Tensor

T = TypeVar("T")

EnvId = int
EnvIdTensor = Tensor  # 1D tensor of env indices on the appropriate device.

TermName = str
GroupName = str


__all__ = [
    "Any",
    "Callable",
    "Dict",
    "Iterable",
    "Mapping",
    "MutableMapping",
    "Optional",
    "Sequence",
    "Tensor",
    "Tuple",
    "TypeVar",
    "EnvId",
    "EnvIdTensor",
    "TermName",
    "GroupName",
]

