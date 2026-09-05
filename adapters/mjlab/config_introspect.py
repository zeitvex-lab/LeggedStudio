"""Config-tree introspection and dot-path overrides for training profiles.

This module is the bridge that removes the "source-code black box" from
profile-mode training: the full ``ManagerBasedRlEnvCfg`` / runner-config tree
authored inside a robot package is dumped to JSON (``build_profile_schema`` /
``dump_config_tree``) so the Web console can render and edit it, and user
edits are written back onto the live config objects with ``set_by_path``.

Only the standard library is imported here on purpose: the control plane can
unit-test this module without mjlab or torch, and the worker's
``--dump-schema`` short-circuit runs before any heavy import.
"""

from __future__ import annotations

import copy
import enum
import importlib
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Iterator

_MAX_REPR_LEN = 120
_DEPTH_MARKER = "…"


def _short_repr(obj: Any) -> str:
    try:
        text = repr(obj)
    except Exception as exc:  # repr() of foreign cfg objects may raise
        text = f"<repr failed: {type(exc).__name__}>"
    return text if len(text) <= _MAX_REPR_LEN else text[: _MAX_REPR_LEN - 1] + "…"


def _is_dataclass(obj: Any) -> bool:
    return hasattr(obj, "__dataclass_fields__")


def _enum_value(obj: Any) -> Any:
    value = obj.value
    if isinstance(value, Path):
        return str(value)
    return value


def dump_config_tree(obj: Any, max_depth: int = 8, _depth: int = 0, _seen: set[int] | None = None) -> Any:
    """Convert a (nested) config object into a JSON-safe tree.

    - dataclass        -> ``{"__type__": ClassName, <field>: dump(...)}`` (private
      / underscore fields are skipped, recursive references collapse to "…")
    - callable         -> ``"fn:" + qualname``
    - enum             -> its ``.value``
    - Path             -> string
    - bool/int/float/str/None -> as-is
    - list/tuple/set   -> list of dumps
    - dict             -> ``{str(key): dump(value)}`` (reward/observation term
      maps and plain payload dicts such as ``distribution_cfg``)
    - anything else    -> ``repr`` truncated to 120 chars
    """
    if _depth >= max_depth:
        return _DEPTH_MARKER
    if _is_dataclass(obj):
        seen = _seen if _seen is not None else set()
        if id(obj) in seen:
            return _DEPTH_MARKER
        fields: dict[str, Any] = {}
        for name in obj.__dataclass_fields__:
            if name.startswith("_"):
                continue
            try:
                value = getattr(obj, name)
            except Exception:
                fields[name] = "<unavailable>"
                continue
            fields[name] = dump_config_tree(value, max_depth, _depth + 1, seen | {id(obj)})
        return {"__type__": type(obj).__name__, **fields}
    if callable(obj):
        return "fn:" + str(getattr(obj, "__qualname__", None) or _short_repr(obj))
    if isinstance(obj, enum.Enum):
        return _enum_value(obj)
    if isinstance(obj, Path):
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(key): dump_config_tree(value, max_depth, _depth + 1, _seen) for key, value in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [dump_config_tree(value, max_depth, _depth + 1, _seen) for value in obj]
    return _short_repr(obj)


def _coerce_like_current(value: Any, current: Any) -> Any:
    """Convert an incoming override value to the current attribute's type."""
    if current is None:
        return value
    if isinstance(current, bool):
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if isinstance(current, int):
        return int(value)
    if isinstance(current, float):
        return float(value)
    if isinstance(current, str):
        return str(value)
    if isinstance(current, (list, tuple)):
        values = list(value) if isinstance(value, (list, tuple)) else [value]
        return tuple(values) if isinstance(current, tuple) else values
    return value


def _child(obj: Any, segment: str) -> Any:
    """Descend one path segment through dict keys or dataclass attributes."""
    if isinstance(obj, dict):
        if segment in obj:
            return obj[segment]
        raise KeyError(segment)
    if _is_dataclass(obj):
        if segment in obj.__dataclass_fields__:
            try:
                return getattr(obj, segment)
            except AttributeError as exc:
                raise KeyError(segment) from exc
        raise KeyError(segment)
    raise KeyError(segment)


def get_by_path(root_obj: Any, dot_path: str, default: Any = None) -> Any:
    """Read a nested dataclass/dict attribute addressed by a dot path.

    Mirrors :func:`set_by_path` addressing; unknown segments (or a traversal
    through a non-container) return ``default`` instead of raising, so callers
    can probe catalog paths against arbitrary configs without try/except.
    """
    current = root_obj
    for segment in (part for part in str(dot_path).split(".") if part):
        try:
            current = _child(current, segment)
        except KeyError:
            return default
        except (TypeError, AttributeError):
            return default
    return current


def set_by_path(root_obj: Any, dot_path: str, value: Any) -> None:
    """Set a nested dataclass/dict attribute addressed by a dot path.

    The incoming value is coerced to the current attribute's type (bool, int,
    float, str; list/tuple round-trip; ``None`` stays untouched). Unknown
    segments raise ``KeyError``.
    """
    parts = [segment for segment in str(dot_path).split(".") if segment]
    if not parts:
        raise KeyError("empty override path")
    parent = root_obj
    for segment in parts[:-1]:
        parent = _child(parent, segment)
    last = parts[-1]
    if isinstance(parent, dict):
        if last not in parent:
            raise KeyError(dot_path)
        parent[last] = _coerce_like_current(value, parent[last])
        return
    if _is_dataclass(parent):
        if last not in parent.__dataclass_fields__:
            raise KeyError(dot_path)
        setattr(parent, last, _coerce_like_current(value, getattr(parent, last)))
        return
    raise KeyError(dot_path)


_PRIMITIVE_TYPES = (bool, int, float, str)


def _leaf_value(obj: Any) -> Any:
    if isinstance(obj, enum.Enum):
        return _enum_value(obj)
    if isinstance(obj, Path):
        return str(obj)
    return obj


def iter_leaves(obj: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Yield ``(dot_path, value)`` for primitive leaves of a config tree.

    Lists/tuples of primitives are yielded whole (network shapes, command
    ranges); nested containers are recursed; callables and complex objects are
    skipped. Paths match the keys accepted by :func:`set_by_path`.
    """
    def join(segment: str) -> str:
        return f"{prefix}.{segment}" if prefix else segment

    if _is_dataclass(obj):
        for name in obj.__dataclass_fields__:
            if name.startswith("_"):
                continue
            try:
                child = getattr(obj, name)
            except Exception:
                continue
            yield from iter_leaves(child, join(name))
        return
    if isinstance(obj, dict):
        for key, child in obj.items():
            yield from iter_leaves(child, join(str(key)))
        return
    if isinstance(obj, (list, tuple)):
        if obj and all(item is None or isinstance(item, _PRIMITIVE_TYPES) for item in obj):
            yield prefix, [_leaf_value(item) for item in obj]
        return
    if obj is None or isinstance(obj, _PRIMITIVE_TYPES) or isinstance(obj, (enum.Enum, Path)):
        if prefix:
            yield prefix, _leaf_value(obj)


def _resolve_entrypoint_attr(entrypoint: str) -> Any:
    """Resolve a ``module:attr`` entrypoint to a config instance.

    Callable attributes (factories) are invoked with no arguments — package
    env factories use ``play=False`` defaults, so this yields the training
    config; plain config objects are deep-copied so callers can mutate freely.
    """
    module_name, separator, attr_name = str(entrypoint).partition(":")
    if not separator or not module_name or not attr_name:
        raise ValueError(f"invalid entrypoint: {entrypoint!r}; expected module:attr")
    attr = getattr(importlib.import_module(module_name), attr_name, None)
    if attr is None:
        raise AttributeError(f"entrypoint attribute not found: {entrypoint}")
    if callable(attr):
        return attr()
    return copy.deepcopy(attr)


def build_profile_schema(source_root: Path | str, entrypoints: dict, profile_id: str | None = None) -> dict:
    """Dump the full env + runner config trees declared by a training profile.

    Imports the package-owned entrypoints with ``source_root`` on ``sys.path``
    (and as CWD for relative asset loading), so this runs inside the isolated
    adapter interpreter, never the control plane.
    """
    source_root = Path(source_root)
    if not source_root.exists():
        raise FileNotFoundError(f"profile source root not found: {source_root}")
    source_str = str(source_root)
    if source_str not in sys.path:
        sys.path.insert(0, source_str)
    os.chdir(source_root)
    entrypoints = dict(entrypoints or {})
    env_entrypoint = entrypoints.get("env")
    runner_entrypoint = entrypoints.get("runner")
    if not env_entrypoint or not runner_entrypoint:
        raise ValueError(f"profile {profile_id!r} must declare entrypoints.env and entrypoints.runner")
    env_cfg = _resolve_entrypoint_attr(env_entrypoint)
    runner_cfg = _resolve_entrypoint_attr(runner_entrypoint)
    return {
        "profile_id": profile_id,
        "environment": dump_config_tree(env_cfg),
        "runner": dump_config_tree(runner_cfg),
        "entrypoints": entrypoints,
    }
