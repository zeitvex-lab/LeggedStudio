#!/usr/bin/env python3
"""
camera_subsystem.py
===================
Arm camera background thread for /dev/video0.

Stores the latest frame in a thread-safe buffer so any part of the pipeline
can call get_frame() at any time without blocking the capture loop.

The dog (body) camera is already managed by Go2IO in go2_io.py.
Use io.get_frame() for that.  This module only adds the arm camera.
"""

import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np


class ArmCameraThread:
    """
    Background thread that reads frames from the wrist/arm camera continuously.

    Tries a GStreamer MJPEG pipeline first for low latency.
    Falls back to plain V4L2 if GStreamer is unavailable.

    Args:
      device  - V4L2 device path  (default: /dev/video0)
      width   - capture width  (pixels)
      height  - capture height (pixels)
      fps     - target capture rate (Hz)
    """

    def __init__(
        self,
        device: str = "/dev/video0",
        width:  int = 1280,
        height: int = 720,
        fps:    int = 30,
    ):
        self._device = device
        self._width  = int(width)
        self._height = int(height)
        self._fps    = int(fps)

        self._lock     = threading.Lock()
        self._frame:   Optional[np.ndarray] = None
        self._frame_t: float = 0.0

        self._stop_evt = threading.Event()
        self._thread:  Optional[threading.Thread] = None

    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Start the background capture thread."""
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="arm-cam"
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the background thread to stop (non-blocking)."""
        self._stop_evt.set()

    def get_frame(self) -> Tuple[Optional[np.ndarray], float]:
        """
        Return a copy of the latest captured frame and its timestamp.

        Returns (None, 0.0) if no frame has been captured yet.
        Safe to call from any thread at any time.
        """
        with self._lock:
            if self._frame is None:
                return None, 0.0
            return self._frame.copy(), float(self._frame_t)

    # -------------------------------------------------------------------------

    def _run(self) -> None:
        # Try GStreamer MJPEG pipeline first (lower latency on Jetson / v4l2)
        gst = (
            f"v4l2src device={self._device} ! "
            f"image/jpeg,width={self._width},height={self._height},"
            f"framerate={self._fps}/1 ! "
            f"jpegdec ! videoconvert ! video/x-raw,format=BGR ! appsink"
        )
        cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)

        if not cap.isOpened():
            # GStreamer not available — fall back to plain V4L2
            cap = cv2.VideoCapture(self._device)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self._width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        if not cap.isOpened():
            print(f"[arm-cam] ERROR: cannot open {self._device}")
            return

        # Discard the first few buffered frames so we start fresh
        for _ in range(5):
            cap.read()
            time.sleep(0.02)

        print(f"[arm-cam] Started: {self._device} @ {self._width}×{self._height}")

        dt = 1.0 / max(1, self._fps)

        while not self._stop_evt.is_set():
            t0 = time.time()
            try:
                ret, frame = cap.read()
                if ret and frame is not None:
                    with self._lock:
                        self._frame   = frame
                        self._frame_t = time.time()
            except Exception as e:
                print(f"[arm-cam] read error: {e}")
                time.sleep(0.1)

            elapsed = time.time() - t0
            if elapsed < dt:
                time.sleep(dt - elapsed)

        cap.release()
        print("[arm-cam] Stopped.")
