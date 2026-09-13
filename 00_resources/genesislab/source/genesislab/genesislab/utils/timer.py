"""Simple timing utilities for GenesisLab.

For now, this module provides a context-manager style :class:`Timer` that
mirrors the basic interface used in the terrain generation utilities.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class Timer:
    """Simple wall-clock timer context manager.

    Example
    -------
    >>> with Timer("[INFO] Doing work took"):
    ...     expensive_call()
    [INFO] Doing work took: 0.123 s
    """

    msg: str = "Elapsed time"
    enabled: bool = True
    _start: Optional[float] = None

    def __enter__(self) -> "Timer":
        if self.enabled:
            self._start = time.time()
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:  # noqa: ANN001
        if self.enabled and self._start is not None:
            dt = time.time() - self._start
            print(f"{self.msg}: {dt:.3f} s")


__all__ = ["Timer"]

