"""Shared utilities for Genesis-native sensor wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import torch

if TYPE_CHECKING:
    try:
        import genesis as gs  # type: ignore
    except Exception:  # pragma: no cover - optional at type-check time
        gs = Any  # type: ignore


def resolve_entity_idx(lab_scene: Any, entity_name: str) -> int:
    """Resolve entity name to Genesis entity index."""
    if not entity_name or entity_name not in lab_scene.entities:
        raise KeyError(
            f"Entity '{entity_name}' not found. Available: {list(lab_scene.entities.keys())}"
        )
    raw = lab_scene.entities[entity_name].raw_entity
    if not hasattr(raw, "idx"):
        raise AttributeError(f"Entity '{entity_name}' has no .idx (not a Genesis entity?).")
    return int(raw.idx)


def resolve_link_idx_local(lab_scene: Any, entity_name: str, link_name: str | None) -> int:
    """Resolve link name to local link index for an entity. Returns 0 if link_name is None."""
    if not link_name:
        return 0
    if not entity_name or entity_name not in lab_scene.entities:
        raise KeyError(
            f"Entity '{entity_name}' not found. Available: {list(lab_scene.entities.keys())}"
        )
    lab_entity = lab_scene.entities[entity_name]
    if lab_entity.robot_asset is None:
        return 0
    body = lab_entity.robot_asset.get_body(link_name, normalized=True)
    if body is None:
        body = lab_entity.robot_asset.get_body(link_name, normalized=False)
    if body is not None and hasattr(body, "idx_local"):
        return int(body.idx_local)
    return 0


def to_tensor(x: Any, device: str, dtype: torch.dtype = None) -> torch.Tensor:
    """Best-effort conversion of Genesis sensor outputs to torch.Tensor."""
    if isinstance(x, torch.Tensor):
        t = x
    else:
        t = torch.as_tensor(x)
    if dtype is not None and t.dtype != dtype:
        t = t.to(dtype=dtype)
    if str(t.device) != device:
        t = t.to(device)
    return t

