#!/usr/bin/env python3
"""
camera_streamer.py
==================
Responsible for connecting to and pulling frames from both the dog camera
and the arm camera.  Provides a live implementation for the robot and a
mock implementation that reads local MP4 files for offboard testing.

Two background threads run continuously:
  - _update_dog_camera  : fetches from Unitree VideoClient (or a callback)
  - _update_arm_camera  : reads from an OpenCV VideoCapture device
"""

import threading
import time
from typing import Callable, Optional, Tuple

import cv2
import numpy as np

try:
    from unitree_sdk2py.go2.video.video_client import VideoClient
except ImportError:
    VideoClient = None


class CameraStreamer:
    """Base class — subclass must implement get_dog_frame / get_arm_frame / stop."""

    def get_dog_frame(self) -> Tuple[Optional[np.ndarray], float]:
        raise NotImplementedError

    def get_arm_frame(self) -> Tuple[Optional[np.ndarray], float]:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


class LiveCameraStreamer(CameraStreamer):
    """
    Live camera streamer for the robot.

    Parameters
    ----------
    arm_device : str
        OpenCV device path for the arm camera (e.g. "/dev/video0").
    fps : float
        Target polling rate for the dog camera background thread.
    dog_frame_provider : optional callable
        If provided, dog frames are sourced from this callback instead of the
        Unitree VideoClient.  Pass ``go2_io.get_frame`` here.
    """

    def __init__(
        self,
        arm_device: str = "/dev/video0",
        arm_width: int = 1280,
        arm_height: int = 720,
        arm_fps: float = 30.0,
        fps: float = 20.0,
        dog_frame_provider: Optional[Callable[[], Tuple[Optional[np.ndarray], float]]] = None,
    ):
        self.fps = fps
        self._stop_event = threading.Event()
        self._dog_frame_provider = dog_frame_provider

        # ── Dog camera ────────────────────────────────────────────────────────
        self.video_client = None
        self._dog_frame: Optional[np.ndarray] = None
        self._dog_time: float = 0.0
        self._dog_lock = threading.Lock()

        if self._dog_frame_provider is None:
            if VideoClient is None:
                raise RuntimeError(
                    "unitree_sdk2py not installed and no dog_frame_provider supplied."
                )
            self.video_client = VideoClient()
            self.video_client.SetTimeout(3.0)
            self.video_client.Init()

        # ── Arm camera ────────────────────────────────────────────────────────
        self.arm_cap = cv2.VideoCapture(arm_device)
        self.arm_cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.arm_cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(arm_width))
        self.arm_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(arm_height))
        self.arm_cap.set(cv2.CAP_PROP_FPS, float(arm_fps))
        self._arm_frame: Optional[np.ndarray] = None
        self._arm_time: float = 0.0
        self._arm_lock = threading.Lock()

        # ── Background threads ────────────────────────────────────────────────
        self._dog_thread: Optional[threading.Thread] = None
        if self._dog_frame_provider is None:
            self._dog_thread = threading.Thread(
                target=self._update_dog_camera, daemon=True, name="dog-cam"
            )
        self._arm_thread = threading.Thread(
            target=self._update_arm_camera, daemon=True, name="arm-cam"
        )

        if self._dog_thread is not None:
            self._dog_thread.start()
        self._arm_thread.start()

    # ── Background workers ────────────────────────────────────────────────────

    def _update_dog_camera(self) -> None:
        dt = 1.0 / self.fps
        while not self._stop_event.is_set():
            t0 = time.time()
            code, data = self.video_client.GetImageSample()
            if code == 0:
                buf = np.frombuffer(bytes(data), dtype=np.uint8)
                img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if img is not None:
                    with self._dog_lock:
                        self._dog_frame = img
                        self._dog_time = time.time()
            elapsed = time.time() - t0
            time.sleep(max(0.001, dt - elapsed))

    def _update_arm_camera(self) -> None:
        while not self._stop_event.is_set():
            ret, frame = self.arm_cap.read()
            if ret:
                with self._arm_lock:
                    self._arm_frame = frame
                    self._arm_time = time.time()
            else:
                time.sleep(0.05)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_dog_frame(self) -> Tuple[Optional[np.ndarray], float]:
        if self._dog_frame_provider is not None:
            return self._dog_frame_provider()
        with self._dog_lock:
            frame = self._dog_frame.copy() if self._dog_frame is not None else None
            return frame, self._dog_time

    def get_arm_frame(self) -> Tuple[Optional[np.ndarray], float]:
        with self._arm_lock:
            frame = self._arm_frame.copy() if self._arm_frame is not None else None
            return frame, self._arm_time

    def stop(self) -> None:
        self._stop_event.set()
        if self._dog_thread is not None:
            self._dog_thread.join(timeout=1.0)
        self._arm_thread.join(timeout=1.0)
        self.arm_cap.release()
