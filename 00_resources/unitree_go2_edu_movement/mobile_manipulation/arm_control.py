#!/usr/bin/env python3
"""
arm_control.py
==============
WidowX-250 (wx250) wrapper adapted for upright-object grasping.

Key differences from the old ground-tag pipeline
-------------------------------------------------
- No robot body pitch required.  The object is upright on a 53 cm box,
  roughly level with the arm.
- Horizontal approach: gripper roll=0, pitch=0 (fingers pointing forward).
- Observation pose  = OBS_PRESET_DEG   (POSITION_1 from old_pipeline).
- Carry pose        = CARRY_PRESET_DEG (POSITION_2 from old_pipeline).

Grasp sequence (grasp_upright)
-------------------------------
  1. Open gripper
  2. Move EE to pre-grasp  (grasp_x - PRE_GRASP_RETRACT_M, grasp_y, grasp_z)
  3. Slide forward to grasp point  (grasp_x, grasp_y, grasp_z)
  4. Close gripper
  5. Retract EE back to pre-grasp point  (pulls object away from wall)
  6. Return arm to carry pose

All public methods are thread-safe via a reentrant lock (RLock), so
grasp_upright() can call go_carry() internally without deadlock.
"""

import threading
import time

import numpy as np


# ── Robot model ──────────────────────────────────────────────────────────────
ARM_MODEL   = "wx250"

MOVING_TIME = 2.0    # seconds for a full-range joint move
ACCEL_TIME  = 0.6    # seconds of acceleration ramp at start/end of each move
SETTLE_S    = 0.15   # brief pause after a move completes

# ── Gripper orientation for upright-object horizontal approach ───────────────
# roll=0, pitch=0 → gripper fingers pointing forward along the robot's X axis
GRASP_ROLL  = 0.0
GRASP_PITCH = 0.0

# How far to retract before sliding into the grasp point
PRE_GRASP_RETRACT_M = 0.06   # metres

# ── Hand-eye calibration: camera frame → EE frame ────────────────────────────
# Historical variable name kept from old_pipeline.py. In the transform chain
# T_base_cam = T_base_ee @ T_EE_CAM, this matrix maps camera-frame points into
# the end-effector frame.
T_EE_CAM = np.array([
    [-0.01829869, -0.71656913,  0.69727601, -0.04152233],
    [-0.99937559, -0.00797410, -0.03442146,  0.00367226],
    [ 0.03022550, -0.69747049, -0.71597579,  0.07381512],
    [ 0.00000000,  0.00000000,  0.00000000,  1.00000000],
], dtype=np.float64)

# Alias kept to make the conversion call site read clearly.
T_CAM_EE = T_EE_CAM

# ── Named joint presets (degrees) ────────────────────────────────────────────
# Format: [waist, shoulder, elbow, wrist_angle, wrist_rotate]

# Observation pose: arm camera faces forward toward the pink object.
# This is POSITION_1 from old_pipeline.py, confirmed by the user.
OBS_PRESET_DEG = [0.0, -100.0, 60.0, 10.0, 0.0]

# Carry pose: arm partially retracted while holding the object during travel.
# This is POSITION_2 from old_pipeline.py.
CARRY_PRESET_DEG = [0.0, -15.0, 48.0, -6.0, 0.0]


# =============================================================================
#  ArmControl
# =============================================================================

class ArmControl:
    """
    High-level interface to the WidowX-250 arm.

    All public methods acquire self._lock (RLock) for thread safety.
    Internal helpers (*_nolock) must be called with the lock already held.
    """

    def __init__(self):
        from interbotix_xs_modules.arm import InterbotixManipulatorXS

        self.bot = InterbotixManipulatorXS(
            robot_model=ARM_MODEL,
            group_name="arm",
            gripper_name="gripper",
        )
        self.bot.arm.set_trajectory_time(
            moving_time=MOVING_TIME, accel_time=ACCEL_TIME
        )
        try:
            self.bot.gripper.set_pressure(0.5)
        except Exception:
            pass

        # RLock lets grasp_upright() call go_carry() without deadlocking
        self._lock = threading.RLock()
        print(f"[arm] Initialized {ARM_MODEL}")

    # ── Gripper (public) ──────────────────────────────────────────────────────

    def open_gripper(self) -> None:
        print("[arm] Gripper → OPEN")
        with self._lock:
            self._open_gripper_nolock()

    def close_gripper(self) -> None:
        print("[arm] Gripper → CLOSE")
        with self._lock:
            self._close_gripper_nolock()

    # ── Gripper (internal, call with lock held) ───────────────────────────────

    def _open_gripper_nolock(self) -> None:
        g = self.bot.gripper
        if hasattr(g, "release"):
            try:    g.release(2.0)
            except TypeError: g.release()
        elif hasattr(g, "open"):
            try:    g.open(2.0)
            except TypeError: g.open()

    def _close_gripper_nolock(self) -> None:
        g = self.bot.gripper
        if hasattr(g, "grasp"):
            try:    g.grasp(2.0)
            except TypeError: g.grasp()
        elif hasattr(g, "close"):
            try:    g.close(2.0)
            except TypeError: g.close()

    # ── Named poses ───────────────────────────────────────────────────────────

    def go_home(self) -> None:
        """Move to the arm's built-in home pose."""
        print("[arm] → HOME")
        with self._lock:
            self.bot.arm.go_to_home_pose()
            time.sleep(SETTLE_S)

    def go_sleep(self) -> None:
        """Tuck the arm into sleep pose for safe walking."""
        print("[arm] → SLEEP")
        with self._lock:
            self.bot.arm.go_to_sleep_pose()
            time.sleep(SETTLE_S)

    def go_observation(self) -> None:
        """
        Move to observation pose so the arm camera faces forward
        toward the pink object.  Uses OBS_PRESET_DEG (POSITION_1).

        Always passes through HOME first — going directly from sleep
        to a joint preset can stress the arm or be rejected by the controller.
        """
        q = np.deg2rad(np.array(OBS_PRESET_DEG, dtype=float)).tolist()
        print("[arm] → HOME (via go_observation)")
        with self._lock:
            self.bot.arm.go_to_home_pose()
            time.sleep(SETTLE_S)
        print(f"[arm] → OBSERVATION  joints={OBS_PRESET_DEG}")
        with self._lock:
            self.bot.arm.set_joint_positions(q, blocking=True)
            time.sleep(SETTLE_S)

    def go_carry(self) -> None:
        """
        Move to carry pose: arm retracted while transporting the object.
        Uses CARRY_PRESET_DEG (POSITION_2).
        """
        q = np.deg2rad(np.array(CARRY_PRESET_DEG, dtype=float)).tolist()
        print(f"[arm] → CARRY  joints={CARRY_PRESET_DEG}")
        with self._lock:
            self.bot.arm.set_joint_positions(q, blocking=True)
            time.sleep(SETTLE_S)

    # ── Forward kinematics & coordinate transforms ────────────────────────────

    def get_ee_T(self) -> np.ndarray:
        """
        Return the 4×4 SE(3) transform T_base_ee (EE pose in arm base frame)
        from the arm's forward kinematics at the current joint configuration.
        """
        with self._lock:
            pose = self.bot.arm.get_ee_pose()
        arr = np.array(pose, dtype=np.float64)
        if arr.shape == (4, 4):
            return arr
        # Some API versions return a 6-vector [x, y, z, roll, pitch, yaw]
        if arr.size == 6:
            x, y, z, r, p, yw = arr.reshape(-1)
            from math import cos, sin
            cr, sr = cos(r),  sin(r)
            cp, sp = cos(p),  sin(p)
            cy, sy = cos(yw), sin(yw)
            Rz = np.array([[cy,-sy,0],[sy,cy,0],[0,0,1]], dtype=np.float64)
            Ry = np.array([[cp,0,sp],[0,1,0],[-sp,0,cp]], dtype=np.float64)
            Rx = np.array([[1,0,0],[0,cr,-sr],[0,sr,cr]], dtype=np.float64)
            R  = Rz @ Ry @ Rx
            T  = np.eye(4, dtype=np.float64)
            T[:3, :3] = R
            T[:3,  3] = [x, y, z]
            return T
        raise RuntimeError(f"Unexpected get_ee_pose() shape: {arr.shape}")

    def cam_to_arm_frame(self, pos_cam: np.ndarray) -> np.ndarray:
        """
        Transform a 3D point from camera frame to arm base frame.

        Uses the hand-eye calibration T_EE_CAM and the current FK T_base_ee.

        Formula:
            P_base = T_base_ee  @  T_CAM_EE  @  P_cam_hom

        where T_CAM_EE = inv(T_EE_CAM).

        Args
        ----
        pos_cam   [Xc, Yc, Zc] in camera frame (metres).

        Returns
        -------
        [Xa, Ya, Za] in arm base frame (metres).
        """
        T_base_ee = self.get_ee_T()
        p_hom = np.array([pos_cam[0], pos_cam[1], pos_cam[2], 1.0], dtype=np.float64)
        p_arm = T_base_ee @ T_CAM_EE @ p_hom
        return p_arm[:3]

    # ── IK helper (call with lock held) ───────────────────────────────────────

    def _move_ee(
        self, x: float, y: float, z: float,
        roll: float, pitch: float, label: str = ""
    ) -> bool:
        """
        Move end-effector to (x, y, z) with the given orientation.
        Returns True on success.  Must be called with self._lock held.
        """
        ret = self.bot.arm.set_ee_pose_components(
            x=x, y=y, z=z, roll=roll, pitch=pitch
        )
        ok = True
        if isinstance(ret, bool):
            ok = ret
        elif isinstance(ret, (list, tuple)) and len(ret) > 0 and isinstance(ret[0], bool):
            ok = ret[0]
        if not ok:
            print(
                f"[arm] IK FAIL @ {label}: "
                f"x={x:+.3f} y={y:+.3f} z={z:+.3f} "
                f"roll={roll:+.3f} pitch={pitch:+.3f}"
            )
        return ok

    # ── Full grasp sequence ───────────────────────────────────────────────────

    def grasp_upright(
        self,
        grasp_x: float,
        grasp_y: float,
        grasp_z: float,
    ) -> bool:
        """
        Execute a horizontal-approach grasp on an upright object.

        Moves the gripper from in front of the object (pre-grasp), slides
        it forward onto the object, closes, then retracts before returning
        to the carry pose.

        Args
        ----
        grasp_x   Forward reach from the arm base to the object (metres).
                  Starting value: 0.35 m — calibrate for your setup.
        grasp_y   Lateral offset from the arm centreline (metres).
                  0.0 = aligned with the robot's forward axis.
        grasp_z   Height of the grasp point in the arm base frame (metres).
                  Calculation:
                    box_height (0.53 m) + obj_half_height (0.151 m)
                    - arm_base_height_above_ground (~0.40 m) ≈ 0.28 m

        Returns
        -------
        True on success, False if any IK step fails.
        """
        pre_x = grasp_x - PRE_GRASP_RETRACT_M

        print(f"\n[arm] ── GRASP START ──")
        print(f"[arm]   pre-grasp : ({pre_x:+.3f}, {grasp_y:+.3f}, {grasp_z:+.3f})")
        print(f"[arm]   grasp     : ({grasp_x:+.3f}, {grasp_y:+.3f}, {grasp_z:+.3f})")

        with self._lock:
            # Step 1: open gripper
            print("[arm] Step 1 — open gripper")
            self._open_gripper_nolock()
            time.sleep(0.3)

            # Step 2: move to pre-grasp position (clear of object)
            print("[arm] Step 2 — pre-grasp position")
            if not self._move_ee(
                pre_x, grasp_y, grasp_z, GRASP_ROLL, GRASP_PITCH, "PRE_GRASP"
            ):
                print("[arm] Aborting: IK failed at pre-grasp.")
                return False
            time.sleep(MOVING_TIME + 0.2)

            # Step 3: slide forward onto the object
            print("[arm] Step 3 — slide to grasp")
            if not self._move_ee(
                grasp_x, grasp_y, grasp_z, GRASP_ROLL, GRASP_PITCH, "GRASP"
            ):
                print("[arm] Aborting: IK failed at grasp point.")
                return False
            time.sleep(MOVING_TIME + 0.2)

            # Step 4: close gripper
            print("[arm] Step 4 — close gripper")
            self._close_gripper_nolock()
            time.sleep(0.6)

            # Step 5: retract (pull object away from wall)
            print("[arm] Step 5 — retract")
            self._move_ee(
                pre_x, grasp_y, grasp_z, GRASP_ROLL, GRASP_PITCH, "RETRACT"
            )
            time.sleep(MOVING_TIME + 0.2)

        # Step 6: carry pose — go_carry() acquires the lock itself (RLock)
        print("[arm] Step 6 — carry pose")
        self.go_carry()

        print("[arm] ── GRASP DONE ──\n")
        return True
