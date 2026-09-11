#!/usr/bin/env python3
"""
dog_detection_worker.py
=======================
Runs dog-camera YOLO on a background thread using a latest-frame queue.

The state machine can submit fresh frames without blocking on inference and
read back the most recent completed detection result at any time.
"""

import threading
import time
from typing import Callable, Optional, Tuple

import numpy as np

from vision_core import TargetCoordinates


class AsyncDogDetector:
    """Latest-frame asynchronous worker for dog-camera detections."""

    def __init__(
        self,
        process_frame_fn: Callable[[np.ndarray], Tuple[TargetCoordinates, np.ndarray]],
    ):
        self._process_frame = process_frame_fn

        self._lock = threading.Lock()
        self._cv   = threading.Condition(self._lock)

        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._pending_frame: Optional[np.ndarray] = None
        self._pending_ts = 0.0

        self._latest_ts      = 0.0
        self._latest_done_t  = 0.0
        self._latest_target  = TargetCoordinates(detected=False)
        self._latest_debug: Optional[np.ndarray] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="dog-detector"
        )
        self._thread.start()

    def stop(self) -> None:
        with self._cv:
            self._running = False
            self._cv.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def submit(self, frame_bgr: np.ndarray, frame_ts: float) -> None:
        """Queue the latest frame for detection, overwriting older pending work."""
        if frame_bgr is None or frame_ts <= 0.0:
            return
        with self._cv:
            if frame_ts <= self._latest_ts and self._pending_frame is None:
                return
            if frame_ts <= self._pending_ts:
                return
            self._pending_frame = frame_bgr.copy()
            self._pending_ts    = float(frame_ts)
            self._cv.notify()

    def get_latest(
        self,
    ) -> Tuple[float, TargetCoordinates, Optional[np.ndarray], float]:
        """Return (frame_ts, target, debug_frame_copy, completion_time)."""
        with self._lock:
            debug = None if self._latest_debug is None else self._latest_debug.copy()
            return (
                float(self._latest_ts),
                self._latest_target,
                debug,
                float(self._latest_done_t),
            )

    def _loop(self) -> None:
        import logging
        _log = logging.getLogger(__name__)

        while True:
            with self._cv:
                while self._running and self._pending_frame is None:
                    self._cv.wait(timeout=0.1)
                if not self._running:
                    return
                frame    = self._pending_frame
                frame_ts = self._pending_ts
                self._pending_frame = None

            infer_start = time.time()
            target, debug = self._process_frame(frame)
            done_t = time.time()

            infer_ms = (done_t - infer_start) * 1000.0
            queue_ms = (infer_start - frame_ts) * 1000.0
            _log.info(
                f"[LAG] YOLO infer={infer_ms:.0f}ms  queue_wait={queue_ms:.0f}ms  "
                f"total={infer_ms + queue_ms:.0f}ms  "
                f"detected={target.detected}  dist={target.dist_m:.2f}m"
            )

            with self._lock:
                if frame_ts >= self._latest_ts:
                    self._latest_ts     = float(frame_ts)
                    self._latest_done_t = float(done_t)
                    self._latest_target = target
                    self._latest_debug  = debug
