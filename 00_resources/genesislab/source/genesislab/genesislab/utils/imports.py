from __future__ import annotations

"""Utility helpers for dynamic import / resolution of callables.

These helpers allow configuration objects to specify functions either as
direct Python callables or as string paths like
``\"package.module:function_name\"`` or ``\"package.module.func_name\"``.
"""

from importlib import import_module
from typing import Any, Callable


def _split_path(spec: str) -> tuple[str, str]:
    """Split an import specification into (module_path, attribute_name).

    Supported formats:
    - ``\"pkg.mod:attr\"``
    - ``\"pkg.mod.attr\"`` (last segment is treated as attribute)
    """
    if ":" in spec:
        module_path, attr = spec.split(":", maxsplit=1)
    else:
        parts = spec.rsplit(".", maxsplit=1)
        if len(parts) != 2:
            raise ValueError(
                f"Invalid callable specification '{spec}'. Expected 'pkg.mod:attr' or 'pkg.mod.attr'."
            )
        module_path, attr = parts
    return module_path, attr


def resolve_callable(spec: Any) -> Any:
    """Resolve *spec* into a callable or class, if needed.

    - If *spec* is already callable (function or class), it is returned as-is.
    - If *spec* is a string, it is interpreted as an import path and resolved.

    This is primarily used by manager term configurations so that configuration
    files can refer to functions by string path.
    """
    # Fast path: already a callable (functions / classes / functors)
    if callable(spec):
        return spec

    # String path – import dynamically.
    if isinstance(spec, str):
        module_path, attr = _split_path(spec)
        try:
            module = import_module(module_path)
        except ImportError as exc:
            raise ImportError(
                f"Failed to import module '{module_path}' while resolving callable '{spec}'."
            ) from exc

        try:
            resolved = getattr(module, attr)
        except AttributeError as exc:
            raise AttributeError(
                f"Module '{module_path}' does not define attribute '{attr}' "
                f"(while resolving callable '{spec}')."
            ) from exc

        if not callable(resolved):
            raise TypeError(
                f"Resolved object '{spec}' is not callable. Got type: {type(resolved)!r}."
            )
        return resolved

    # Anything else is unsupported.
    raise TypeError(
        f"Unsupported callable specification of type {type(spec)!r}: {spec!r}."
    )

