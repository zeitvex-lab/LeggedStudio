"""Framework-neutral RoboLab contracts.

This package must remain importable without Isaac Gym, MJLab, MuJoCo, or a GPU.
Backend adapters may consume these contracts, but the contracts must not import
backend objects in return.
"""

from .contracts import (
    PolicyArtifact,
    Recipe,
    RunRecord,
    TensorContract,
)

__all__ = ["PolicyArtifact", "Recipe", "RunRecord", "TensorContract"]
