"""Framework-neutral method specifications and registry."""

from .registry import MethodSpec, get_method, list_methods, register_method

__all__ = ["MethodSpec", "get_method", "list_methods", "register_method"]
