from __future__ import annotations

import logging
import time
from typing import Optional


logger = logging.getLogger(__name__)


class DebugTimer:
    """Context manager to log wall-clock time for a code block when logger is in DEBUG.

    Usage:
        from genesislab.utils.timing import timed_block

        with timed_block("physics"):
            scene.step()
    """

    def __init__(self, name: str, logger_: Optional[logging.Logger] = None):
        self._name = name
        self._logger = logger_ or logger
        self._enabled = self._logger.isEnabledFor(logging.DEBUG)
        self._start = 0.0

    def __enter__(self):
        if self._enabled:
            self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._enabled:
            elapsed_ms = (time.perf_counter() - self._start) * 1000.0
            self._logger.debug(f"[Timing] {self._name} took {elapsed_ms:.3f} ms")


def timed_block(name: str, logger_: Optional[logging.Logger] = None) -> DebugTimer:
    """Return a context manager for timing a code block in DEBUG logs."""
    return DebugTimer(name, logger_=logger_)

