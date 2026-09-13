"""Command-line argument helpers for GenesisLab scripts.

This small subpackage centralizes common CLI flags (viewer, rendering, etc.)
so that examples and test scripts can share a consistent interface.
"""

from .args import add_viewer_args

__all__ = ["add_viewer_args"]

