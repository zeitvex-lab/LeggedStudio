#!/usr/bin/env python3
"""
arm_controller.py
=================
All WidowX-250 arm control: poses, IK, grasping, and the extrinsic
transform that converts arm-camera detections into arm-base-frame
coordinates.

Public API
----------
go_home()                          — Interbotix home pose
go_sleep()                         — Stow/sleep pose (safe for walking)
go_carry()                         — Travel-safe carry pose
go_position_2()                    — Arm-camera viewing pose
open_gripper() / close_gripper()

ball_cam_to_base(p_cam)            — Camera → arm base frame transform
grasp_after_pitch(x, y, z, pitch) — Floor grasp with pitched body
scan_wrist(vision, streamer)       — Oscillate wrist to find ball
"""

import math
import threading
import time
import numpy as np


ARM_MODEL   = "wx250"
MOVING_TIME = 2.0
ACCEL_TIME  = 0.6
SETTLE_S    = 0.15

# Grasp orientation — gripper pointing down (roll=0) with pitch compensating
# for body tilt.  GRASP_ROLL=π/2 is the sideways-grasp variant.
PRE_GRASP_RETRACT_M = 0.05
HOVER_Z_OFFSET_M    = 0.06   # hover 6 cm above ball centre before descending
GRASP_CLEARANCE_Z_M = 0.10   # safe transit height above arm-base plane

CARRY_PRESET_DEG   = [0.0, -90.0, 70.0, 5.0, 0.0]
# POSITION_2_DEG     = [-0.0, -15.0, 48.0, -6.0, 0.0]   # arm-cam viewing pose
POSITION_2_DEG     = [-0.0, -20.0, 40.0, -11.0, 0.0]   # arm-cam viewing pose



# ── Hand-eye calibration: camera frame → end-effector frame ──────────────────
# p_ee = T_EE_CAM @ p_cam
T_EE_CAM = np.array([
    [-0.01829869, -0.71656913,  0.69727601, -0.04152233],
    [-0.99937559, -0.00797410, -0.03442146,  0.00367226],
    [ 0.03022550, -0.69747049, -0.71597579,  0.07381512],
    [ 0.00000000,  0.00000000,  0.00000000,  1.00000000],
], dtype=np.float64)


class ArmController:
    """
    High-level, thread-safe interface to the WidowX-250 arm.

    All blocking arm moves hold self._lock, so calling stop() or any
    other method from a different thread will wait for the current move
    to finish — preventing mid-motion interruptions.
    """

    def __init__(self):
        from interbotix_xs_modules.arm import InterbotixManipulatorXS
        self.bot = InterbotixManipulatorXS(
            robot_model=ARM_MODEL,
            group_name="arm",
            gripper_name="gripper",
        )
        self.bot.arm.set_trajectory_time(moving_time=MOVING_TIME, accel_time=ACCEL_TIME)
        self._lock = threading.RLock()

    # ── Gripper ───────────────────────────────────────────────────────────────

    def open_gripper(self) -> None:
        with self._lock:
            self.bot.gripper.open()

    def close_gripper(self) -> None:
        with self._lock:
            self.bot.gripper.close()

    # ── Named poses ───────────────────────────────────────────────────────────

    def go_home(self) -> None:
        with self._lock:
            self.bot.arm.go_to_home_pose()
            time.sleep(SETTLE_S)

    def go_sleep(self) -> None:
        """Stow the arm — safe for walking."""
        with self._lock:
            self.bot.arm.go_to_sleep_pose()
            time.sleep(SETTLE_S)

    def go_carry(self) -> None:
        """Travel-safe carry position."""
        q = np.deg2rad(np.array(CARRY_PRESET_DEG, dtype=float)).tolist()
        with self._lock:
            self.bot.arm.set_joint_positions(q, blocking=True)
            time.sleep(SETTLE_S)

    def go_position_2(self) -> None:
        """Arm-camera viewing pose used as the ARM_SEARCH start position."""
        q = np.deg2rad(np.array(POSITION_2_DEG, dtype=float)).tolist()
        with self._lock:
            self.bot.arm.set_joint_positions(q, blocking=True)
            time.sleep(SETTLE_S)

    # ── Extrinsic transform ───────────────────────────────────────────────────

    def get_ee_pose(self) -> np.ndarray:
        """Return current 4×4 T_base_ee from forward kinematics."""
        with self._lock:
            return self.bot.arm.get_ee_pose()

    def ball_cam_to_base(self, p_cam: np.ndarray) -> np.ndarray:
        """
        Transform a homogeneous point from camera frame to arm base frame.

        Parameters
        ----------
        p_cam : shape (4,)  [X, Y, Z, 1] in camera frame.

        Returns
        -------
        shape (3,)  [x, y, z] in arm base frame:
          x = forward distance from arm base
          y = lateral offset (positive = left)
          z = height
        """
        T_base_ee = self.get_ee_pose()
        p_base    = T_base_ee @ T_EE_CAM @ p_cam
        return p_base[:3]

    # ── IK helpers ────────────────────────────────────────────────────────────

    # Pre-built IK seeds biased toward forward-down configurations (floor grasp).
    # The solver tries each in order; first success wins.
    _IK_GUESSES = [
        [0.0, -0.35, 1.40,  1.20, 0.0],
        [0.0, -0.50, 1.60,  1.40, 0.0],
        [0.0, -0.20, 1.20,  0.90, 0.0],
        [0.0,  0.0,  0.0,   0.0,  0.0],
    ]

    def _move_ee(
        self,
        x: float, y: float, z: float,
        roll: float, pitch: float, yaw: float = 0.0,
        custom_guess: list = None,
    ) -> bool:
        """Move end effector via IK, retrying with pre-built seed guesses."""
        guesses = ([custom_guess] if custom_guess else []) + self._IK_GUESSES
        for guess in guesses:
            ret = self.bot.arm.set_ee_pose_components(
                x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw,
                custom_guess=guess,
            )
            if isinstance(ret, (list, tuple)):
                ok = bool(ret[1]) if len(ret) >= 2 else bool(ret[0])
            else:
                ok = bool(ret)
            if ok:
                return True
        return False

    # ── Grasp sequences ───────────────────────────────────────────────────────

    def grasp_flat(
        self,
        grasp_x: float,
        grasp_y: float,
        grasp_z: float,
        hover_z_offset: float = HOVER_Z_OFFSET_M,
    ) -> bool:
        """
        Grasp a ball with the robot body level (no pitch).
        Gripper points straight down (pitch = π/2, roll = 0).

        Sequence
        --------
        1. Go home for a clean IK warm-start.
        2. Hover  at (grasp_x, grasp_y, grasp_z + hover_z_offset)
        3. Descend to (grasp_x, grasp_y, grasp_z)
        4. Close gripper
        5. Lift back to hover height
        6. Return to POSITION_2

        Returns True on success, False if any IK step fails.
        """
        import logging
        log = logging.getLogger(__name__)

        gripper_pitch = math.pi / 2.0   # straight down, body flat
        gripper_roll  = 0.0
        hover_z       = grasp_z + hover_z_offset

        log.info(
            f"grasp_flat: x={grasp_x:.3f} y={grasp_y:.3f} z={grasp_z:.3f} "
            f"hover_z={hover_z:.3f}"
        )
        log.info("grasp_flat: going home for clean IK start")
        self.go_home()

        with self._lock:
            log.info(f"Step 1 — hover ({grasp_x:.3f}, {grasp_y:.3f}, {hover_z:.3f})")
            if not self._move_ee(grasp_x, grasp_y, hover_z, gripper_roll, gripper_pitch):
                log.error("IK FAILED at hover")
                return False
            time.sleep(0.3)

            log.info(f"Step 2 — descend ({grasp_x:.3f}, {grasp_y:.3f}, {grasp_z:.3f})")
            if not self._move_ee(grasp_x, grasp_y, grasp_z, gripper_roll, gripper_pitch):
                log.error("IK FAILED at descend")
                return False
            time.sleep(0.2)

            log.info("Step 3 — close gripper")
            self.close_gripper()
            time.sleep(0.6)

            log.info("Step 4 — lift to hover")
            self._move_ee(grasp_x, grasp_y, hover_z, gripper_roll, gripper_pitch)
            time.sleep(0.3)

        log.info("Step 5 — return to POSITION_2")
        self.go_position_2()
        return True

    def grasp_after_pitch(
        self,
        grasp_x: float,
        grasp_y: float,
        grasp_z: float,
        body_pitch_deg: float = 18.0,
        hover_z_offset: float = HOVER_Z_OFFSET_M,
    ) -> bool:
        """
        Grasp a ball on the floor after the robot body has been pitched forward.

        Orientation: roll=0, pitch = π/2 - body_pitch_rad so the gripper
        points straight down toward the floor, compensating for body tilt.

        Sequence
        --------
        1. Go home for a clean IK warm-start.
        2. Hover  (grasp_x, grasp_y, grasp_z + hover_z_offset)
        3. Descend (grasp_x, grasp_y, grasp_z)
        4. Close gripper
        5. Lift back to hover
        6. Return to POSITION_2 (safe for body to un-pitch)

        Returns True on success, False if any IK step fails.
        """
        import logging
        log = logging.getLogger(__name__)

        gripper_pitch = math.pi / 2.0 - math.radians(body_pitch_deg)
        gripper_roll  = 0.0
        hover_z       = grasp_z + hover_z_offset

        log.info(
            f"grasp_after_pitch: x={grasp_x:.3f} y={grasp_y:.3f} z={grasp_z:.3f} "
            f"hover_z={hover_z:.3f} pitch={gripper_pitch:.3f}rad"
        )
        log.info("grasp_after_pitch: going home for clean IK start")
        self.go_home()

        with self._lock:
            log.info(f"Step 1 — hover target=({grasp_x:.3f},{grasp_y:.3f},{hover_z:.3f})")
            if not self._move_ee(grasp_x, grasp_y, hover_z, gripper_roll, gripper_pitch):
                log.error("IK FAILED at hover")
                return False
            time.sleep(0.3)

            log.info(f"Step 2 — descend target=({grasp_x:.3f},{grasp_y:.3f},{grasp_z:.3f})")
            if not self._move_ee(grasp_x, grasp_y, grasp_z, gripper_roll, gripper_pitch):
                log.error("IK FAILED at descend")
                return False
            time.sleep(0.2)

            log.info("Step 3 — close gripper")
            self.close_gripper()
            time.sleep(0.6)

            log.info("Step 4 — lift to hover")
            self._move_ee(grasp_x, grasp_y, hover_z, gripper_roll, gripper_pitch)
            time.sleep(0.3)

        log.info("Step 5 — return to POSITION_2")
        self.go_position_2()
        return True

    def scan_wrist(self, vision, streamer, max_steps: int = 5):
        """
        Oscillate wrist_angle (joint 4) to scan for the ball when it is not
        visible.  Checks the arm camera after each increment and stops as
        soon as the ball is detected.

        Parameters
        ----------
        vision   : VisionCore instance
        streamer : LiveCameraStreamer instance
        max_steps : number of +/- angle pairs to try before giving up

        Returns
        -------
        p_cam (4,) homogeneous array if detected, else None.
        """
        STEP_RAD    = math.radians(3)
        WRIST_JOINT = "wrist_angle"

        angles = [0.0]
        for i in range(1, max_steps + 1):
            angles.append( i * STEP_RAD)
            angles.append(-i * STEP_RAD)

        for angle in angles:
            try:
                with self._lock:
                    self.bot.arm.set_single_joint_position(WRIST_JOINT, angle, blocking=True)
            except Exception:
                continue
            time.sleep(0.1)

            frame, _ = streamer.get_arm_frame()
            if frame is None:
                continue
            td, _, p_cam = vision.process_arm_frame(frame)
            if td.detected and p_cam is not None:
                return p_cam

        return None
