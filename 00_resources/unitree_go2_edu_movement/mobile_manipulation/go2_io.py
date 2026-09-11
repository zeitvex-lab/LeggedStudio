#!/usr/bin/env python3
"""
go2_io.py
=========
Purpose
-------
This file contains all the "robot I/O + plumbing" so that main.py can stay small.

It handles:
  1) Logging paths + logger creation
  2) Unitree DDS initialization + client creation
  3) Motion mode selection ("normal")
  4) StandUp + BalanceStand startup sequence
  5) SportModeState subscriber (odom-like x,y,yaw)
  6) VideoClient camera thread (GetImageSample -> cv2.imdecode)
  7) Safe stop + shutdown

What it does NOT handle:
  - Vision processing (AprilTag detection) -> vision_pose.py
  - Pose filtering/fusion -> pose_filter.py
  - Control law -> dock_control.py

This split makes the project easier to maintain without making a package/library.
"""

import csv
import logging
import os
import sys
import threading
import time
import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import cv2

# ----------------------------- Unitree SDK2 imports -----------------------------
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.go2.sport.sport_client import SportClient
from unitree_sdk2py.go2.video.video_client import VideoClient
from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient

# Obstacle avoidance client is not always present depending on SDK build
try:
    from unitree_sdk2py.go2.obstacles_avoid.obstacles_avoid_client import ObstaclesAvoidClient
except Exception:
    ObstaclesAvoidClient = None

# SportModeState_ message type can live in different locations on different installs
try:
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
except Exception:
    from unitree_sdk2py.idl.default import unitree_go_msg_dds__SportModeState_ as SportModeState_


# =============================================================================
# Small math helpers (kept here because IO uses yaw normalization + SE(2) pose)
# =============================================================================

def wrap_pi(a: float) -> float:
    """Wrap angle to (-pi, pi]."""
    while a <= -math.pi:
        a += 2.0 * math.pi
    while a > math.pi:
        a -= 2.0 * math.pi
    return a


def T_from_xyyaw(x: float, y: float, yaw: float, z: float = 0.0) -> np.ndarray:
    """
    Convert planar odom pose (x,y,yaw) into a 4x4 rigid transform T_odom_base.
    Used by the fusion step (odom->base) exactly like your original script.
    """
    c = math.cos(yaw)
    s = math.sin(yaw)
    T = np.eye(4, dtype=np.float64)
    T[0, 0] = c
    T[0, 1] = -s
    T[1, 0] = s
    T[1, 1] = c
    T[0, 3] = x
    T[1, 3] = y
    T[2, 3] = z
    return T


# =============================================================================
# Shared state containers (thread-safe) for odom + latest camera frame
# =============================================================================

@dataclass
class OdomState:
    """
    Minimal state the controller needs:
      - x, y: position from SportModeState_.position[]
      - yaw: IMU yaw from SportModeState_.imu_state.rpy[2]
      - t: local receipt timestamp (time.time())
      - valid: whether we ever received a message
    """
    t: float = 0.0
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    valid: bool = False


class Shared:
    """
    Thread-safe buffer for:
      - latest odom-like state
      - latest decoded BGR image
    Both are written by background threads and read by the control loop.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.odom = OdomState()
        self.frame_bgr: Optional[np.ndarray] = None
        self.frame_t: float = 0.0

    def set_odom(self, x: float, y: float, yaw: float, t: float):
        """Write odom atomically."""
        with self._lock:
            self.odom = OdomState(
                t=float(t),
                x=float(x),
                y=float(y),
                yaw=wrap_pi(float(yaw)),
                valid=True
            )

    def get_odom(self) -> OdomState:
        """Read odom atomically."""
        with self._lock:
            return self.odom

    def set_frame(self, img: np.ndarray, t: float):
        """Write frame atomically."""
        with self._lock:
            self.frame_bgr = img
            self.frame_t = float(t)

    def get_frame(self) -> Tuple[Optional[np.ndarray], float]:
        """
        Read frame atomically.
        Returns a copy of the image so the control loop can safely process it.
        """
        with self._lock:
            return (None if self.frame_bgr is None else self.frame_bgr.copy(), float(self.frame_t))


# =============================================================================
# Logging + CSV helpers (kept here so main stays short)
# =============================================================================

def setup_logger_and_paths(log_dir: str) -> Tuple[logging.Logger, str, str]:
    """
    Creates:
      - a console INFO logger
      - a file DEBUG logger
      - unique log + csv paths under log_dir
    """
    os.makedirs(log_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"go2_apriltag_{ts}.log")
    csv_path = os.path.join(log_dir, f"go2_apriltag_{ts}.csv")

    logger = logging.getLogger("go2_apriltag")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s", "%H:%M:%S")

    # Console handler: INFO
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler: DEBUG
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f"Logging to: {log_path}")
    logger.info(f"CSV trace to: {csv_path}")
    return logger, log_path, csv_path


def open_trace_csv(csv_path: str):
    """
    Opens the CSV trace and writes the header exactly like your original script.
    Returns (file_handle, csv_writer).
    """
    csv_f = open(csv_path, "w", newline="")
    csv_w = csv.writer(csv_f)
    csv_w.writerow([
        "t", "odom_x", "odom_y", "odom_yaw",
        "tag_visible", "dist_along", "lateral", "yaw_err",
        "e_dist", "e_lat",
        "vx_cmd", "vy_cmd", "vyaw_cmd",
        "loss_dt"
    ])
    csv_f.flush()
    return csv_f, csv_w


# =============================================================================
# Go2IO: Owns Unitree clients + threads; provides clean API to main
# =============================================================================

class Go2IO:
    """
    A lightweight wrapper around Unitree SDK clients and the IO threads.
    This keeps main.py focused only on:
      vision -> filter -> control -> Move
    """
    def __init__(self, iface: str, state_topic: str, cam_fps: float, logger: logging.Logger):
        self.iface = str(iface)
        self.state_topic = str(state_topic)
        self.cam_fps = float(cam_fps)
        self.logger = logger

        self.shared = Shared()
        self.stop_evt = threading.Event()

        self.msc: Optional[MotionSwitcherClient] = None
        self.sc: Optional[SportClient] = None
        self.video: Optional[VideoClient] = None
        self._sub = None
        self._cam_th = None

    # ----------------------------- Startup sequence -----------------------------
    def startup(self, speed_level: int, avoid_control: str):
        """
        Initializes:
          - DDS / ChannelFactory
          - MotionSwitcherClient, SportClient, VideoClient
          - optional obstacle avoidance switch
          - ensures motion mode = 'normal'
          - stand up and balance
          - starts subscriber + camera thread
        """
        self.logger.info(f"ChannelFactoryInitialize(domain=0, iface='{self.iface}')")
        ChannelFactoryInitialize(0, self.iface)

        # Motion switcher for mode selection
        self.msc = MotionSwitcherClient()
        self.msc.SetTimeout(5.0)
        self.msc.Init()

        # High-level sport client (Move)
        self.sc = SportClient()
        self.sc.SetTimeout(10.0)
        self.sc.Init()

        # Speed level affects max/feel in sport mode
        try:
            code = self.sc.SpeedLevel(int(speed_level))
            self.logger.info(f"SpeedLevel({int(speed_level)}) -> code={code}")
        except Exception as e:
            self.logger.warning(f"SpeedLevel setup failed: {e}")

        # Optional obstacle avoidance control (usually OFF for wall docking)
        if ObstaclesAvoidClient is not None and avoid_control != "keep":
            try:
                oa = ObstaclesAvoidClient()
                oa.SetTimeout(5.0)
                oa.Init()
                target_on = (avoid_control == "on")
                c_set = oa.SwitchSet(target_on)
                c_get, enabled = oa.SwitchGet()
                self.logger.info(f"ObstaclesAvoid {avoid_control}: set={c_set} get={c_get} enabled={enabled}")
            except Exception as e:
                self.logger.warning(f"ObstaclesAvoid control failed: {e}")
        elif ObstaclesAvoidClient is None and avoid_control != "keep":
            self.logger.warning("ObstaclesAvoidClient unavailable; cannot change avoid switch.")

        # Video client for onboard camera stream
        self.video = VideoClient()
        self.video.SetTimeout(3.0)
        self.video.Init()

        # Ensure mode is 'normal' so SportClient can Move
        code, mode = self.msc.CheckMode()
        self.logger.info(f"CheckMode() code={code}, mode={mode}")
        if (not isinstance(mode, dict)) or (mode.get("name", "") != "normal"):
            self.logger.info("Selecting motion mode: 'normal'")
            ret = self.msc.SelectMode("normal")
            self.logger.info(f"SelectMode('normal') ret={ret}")
            time.sleep(0.5)

        # Stand and stabilize (same as original script)
        self.logger.info("StandUp()")
        self.sc.StandUp()
        time.sleep(2.0)
        self.logger.info("BalanceStand()")
        self.sc.BalanceStand()
        time.sleep(1.0)

        # Start background threads
        self._start_state_subscriber()
        self._start_camera_thread()

    def _start_state_subscriber(self):
        """
        Subscribes to SportModeState_ and stores:
          x = msg.position[0]
          y = msg.position[1]
          yaw = msg.imu_state.rpy[2]
        into Shared.odom.
        """
        def on_state(msg: SportModeState_):
            try:
                x = float(msg.position[0])
                y = float(msg.position[1])
                yaw = float(msg.imu_state.rpy[2])
                self.shared.set_odom(x, y, yaw, time.time())
            except Exception as e:
                self.logger.debug(f"State parse error: {e}")

        self._sub = ChannelSubscriber(self.state_topic, SportModeState_)
        self._sub.Init(handler=on_state, queueLen=10)
        self.logger.info(f"Subscribed sport state: {self.state_topic}")

    def _start_camera_thread(self):
        """
        Background thread that pulls frames from VideoClient at cam_fps.

        - VideoClient.GetImageSample() returns encoded bytes.
        - We decode with cv2.imdecode() into BGR.
        - Store latest frame in Shared.frame_bgr.
        """
        def run():
            dt_min = 1.0 / max(1e-6, self.cam_fps)
            t_next = time.time()
            while not self.stop_evt.is_set():
                now = time.time()

                # simple rate limiting
                if now < t_next:
                    time.sleep(min(0.005, t_next - now))
                    continue
                t_next = now + dt_min

                try:
                    code, data = self.video.GetImageSample()
                    if code != 0:
                        self.logger.debug(f"Video.GetImageSample() code={code}")
                        continue

                    # bytes -> np buffer -> decode
                    buf = np.frombuffer(bytes(data), dtype=np.uint8)
                    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                    if img is None:
                        self.logger.debug("cv2.imdecode returned None")
                        continue

                    self.shared.set_frame(img, time.time())

                except Exception as e:
                    self.logger.debug(f"Camera thread error: {e}")
                    time.sleep(0.05)

        self._cam_th = threading.Thread(target=run, daemon=True)
        self._cam_th.start()
        self.logger.info("Camera thread started.")

    # ----------------------------- IO accessors used by main -----------------------------
    def get_odom(self) -> OdomState:
        """Return the latest odom-like state."""
        return self.shared.get_odom()

    def get_frame(self) -> Tuple[Optional[np.ndarray], float]:
        """Return (latest BGR frame copy, timestamp)."""
        return self.shared.get_frame()

    # ----------------------------- Robot actuation + safety -----------------------------
    def move(self, vx: float, vy: float, vyaw: float):
        """Send high-level velocity command."""
        self.sc.Move(float(vx), float(vy), float(vyaw))

    def stop_and_stand(self):
        """StopMove + BalanceStand (used on exit and on done)."""
        try:
            self.sc.StopMove()
            time.sleep(0.2)
            self.sc.BalanceStand()
        except Exception:
            pass

    def shutdown(self):
        """Stop threads and stop the robot safely."""
        self.stop_evt.set()
        self.stop_and_stand()

    # ----------------------------- Convenience transform -----------------------------
    def odom_to_T_odom_base(self, od: OdomState) -> np.ndarray:
        """Convert OdomState into 4x4 odom->base transform."""
        return T_from_xyyaw(od.x, od.y, od.yaw)