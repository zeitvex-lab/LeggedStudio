#!/usr/bin/env python3
"""
dock_control.py
===============
Stage 3:
  - Compute planar errors from T_base_tag_pred
  - Decide mode (SERVO / PRED_YAW_REACQ / SEARCH)
  - Compute vx, vy, vyaw commands (same control logic as original)
"""

from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any
import numpy as np
import math


def wrap_pi(a: float) -> float:
    """Wrap an angle (radians) into the range (-pi, pi]."""
    while a <= -math.pi:
        a += 2.0 * math.pi
    while a > math.pi:
        a -= 2.0 * math.pi
    return a


def clamp(v: float, vmin: float, vmax: float) -> float:
    """Clamp value v to the closed interval [vmin, vmax]."""
    return max(vmin, min(vmax, v))


def compute_planar_errors_from_T_base_tag(
    T_base_tag: np.ndarray,
    target_dist_m: float
) -> Tuple[float, float, float, float, float]:
    """
    Decompose a base→tag transform into planar control errors.

    Projects the tag's 3-D position and surface normal into the ground (XY) plane
    and returns five scalar values used directly by the docking controller:

      dist_along  - current distance to the tag along the approach axis (metres)
      lateral     - signed lateral offset from the approach axis (metres, +ve = left)
      yaw_err     - heading error: angle the robot must rotate to face the tag (radians)
      e_dist      - range error = dist_along - target_dist_m  (negative means too close)
      e_lat       - lateral error = lateral  (alias, kept for controller symmetry)

    The "forward direction" (approach axis) is derived from the tag's Z-axis (surface
    normal) projected onto XY, choosing the sign that points back toward the robot.
    If the projected normal is degenerate (tag facing straight up/down), the position
    vector is used as the fallback.

    Edge case: if the tag is at the robot's origin (p_norm < 1e-6), all positional
    errors are zero and e_dist is returned as -target_dist_m (robot is at the tag).
    """
    p = T_base_tag[:3, 3].copy()   # tag origin in base frame
    R = T_base_tag[:3, :3].copy()  # tag orientation in base frame

    p_xy = p[:2]
    p_norm = float(np.linalg.norm(p_xy))
    if p_norm < 1e-6:
        # Tag is essentially at the robot's origin
        return 0.0, 0.0, 0.0, -float(target_dist_m), 0.0

    # Project the tag's surface normal (tag Z-axis) into the horizontal plane
    n = R @ np.array([0.0, 0.0, 1.0], dtype=np.float64)
    n_xy = n[:2]
    n_norm = float(np.linalg.norm(n_xy))

    if n_norm < 1e-6:
        # Degenerate normal — fall back to the position vector as forward direction
        forward_dir = p_xy / p_norm
    else:
        n_xy = n_xy / n_norm
        # Pick the normal direction that points toward the robot (faces away from tag)
        if float(np.dot(-n_xy, p_xy)) > float(np.dot(n_xy, p_xy)):
            forward_dir = -n_xy
        else:
            forward_dir = n_xy
        forward_dir = forward_dir / (np.linalg.norm(forward_dir) + 1e-12)

    # Left direction is 90° counter-clockwise from forward in the XY plane
    left_dir = np.array([-forward_dir[1], forward_dir[0]], dtype=np.float64)

    dist_along = float(np.dot(p_xy, forward_dir))   # range along approach axis
    lateral = float(np.dot(p_xy, left_dir))          # signed lateral deviation

    # Yaw error: angle between the robot's forward axis (x) and the approach direction
    yaw_err = wrap_pi(math.atan2(forward_dir[1], forward_dir[0]))

    e_dist = dist_along - float(target_dist_m)  # positive = still too far away
    e_lat = lateral
    return dist_along, lateral, yaw_err, e_dist, e_lat


@dataclass
class ControlOutput:
    """
    Velocity commands and status produced by DockingController.step().

    Fields:
      vx         - forward velocity command (m/s, +ve = forward)
      vy         - lateral velocity command (m/s, +ve = left)
      vyaw       - yaw rate command (rad/s, +ve = counter-clockwise)
      done       - True when all errors are within tolerance and the tag is fresh
      mode       - current controller mode: "SERVO", "PRED_YAW_REACQ", or "SEARCH"
      recovering - True when the stuck-recovery push is active
    """
    vx: float
    vy: float
    vyaw: float
    done: bool
    mode: str
    recovering: bool


class DockingController:
    """
    Proportional docking controller that drives a robot to a target distance
    in front of an AprilTag using three velocity axes: vx, vy, vyaw.

    The controller operates in one of three modes each step:

      SERVO          - tag is visible (or was seen very recently); full PD control
                       on distance, lateral offset, and yaw simultaneously.
      PRED_YAW_REACQ - tag was lost for short_loss_s < loss_dt < long_loss_s;
                       translation is zeroed, only yaw correction is applied to
                       help the camera re-acquire the tag using the last known estimate.
      SEARCH         - tag has been lost for >= long_loss_s; robot spins in place
                       at a fixed rate to scan for the tag.

    Control gains and limits are all configurable at construction time.

    Args:
      target_dist        - desired stopping distance in front of the tag (m)
      hz                 - control loop rate, used for documentation only (s^-1)
      k_dist             - proportional gain on range error
      k_lat              - proportional gain on lateral error
      k_yaw              - proportional gain on yaw error
      max_vx             - forward speed limit (m/s)
      max_vy             - lateral speed limit (m/s)
      max_vyaw           - yaw rate limit (rad/s)
      min_vyaw           - minimum yaw rate applied when yaw error exceeds tol_yaw
                           (deadband compensation for turning friction)
      min_vx_cmd         - minimum forward speed when outside tol_dist + margin
      min_vy_cmd         - minimum lateral speed when outside tol_lat + margin
      yaw_first_deg      - if |yaw_err| > this threshold, translation is suppressed
                           and the robot rotates to face the tag first (degrees)
      tol_dist           - range tolerance for done condition (m)
      tol_lat            - lateral tolerance for done condition (m)
      tol_yaw_deg        - yaw tolerance for done condition (degrees)
      min_cmd_dist_margin- extra margin added to tol_dist before applying min_vx_cmd
      min_cmd_lat_margin - extra margin added to tol_lat before applying min_vy_cmd
      short_loss_s       - seconds of tag loss before switching to PRED_YAW_REACQ
      long_loss_s        - seconds of tag loss before switching to SEARCH
      dropout_scale      - translation speed scale during short dropout (0–1)
      dropout_yaw_scale  - yaw speed scale during short dropout (0–1)
      search_vyaw        - constant yaw rate used in SEARCH mode (rad/s)
      allow_backward     - if False, negative vx commands are zeroed
      stuck_warn_s       - seconds of non-movement before the stuck detector fires
      stuck_cmd_min      - minimum commanded speed (m/s) that triggers stuck monitoring
      stuck_odom_step    - maximum odometry displacement (m) counted as "not moving"
      stuck_recover_s    - seconds stuck before the recovery push activates
      stuck_recover_vx   - forward speed override during recovery push (m/s)
      lat_vx_assist      - minimum vx applied as a locomotion assist when the lateral
                           deadband fires and vx_cmd is below this value; needed because
                           small vy alone may not move the robot, but vy + small vx can.
                           Only applied when e_dist > 0 (robot not past target). (m/s)
    """
    def __init__(
        self,
        target_dist: float = 1.0,

        hz: float = 15.0,
        k_dist: float = 0.8,
        k_lat: float = 1.0,
        k_yaw: float = 1.6,

        max_vx: float = 0.45,
        max_vy: float = 0.25,
        max_vyaw: float = 0.6,
        min_vyaw: float = 0.22,

        min_vx_cmd: float = 0.20,
        min_vy_cmd: float = 0.10,

        yaw_first_deg: float = 15.0,
        tol_dist: float = 0.03,
        tol_lat: float = 0.03,
        tol_yaw_deg: float = 2.5,

        min_cmd_dist_margin: float = 0.0,
        min_cmd_lat_margin: float = 0.0,

        short_loss_s: float = 0.7,
        long_loss_s: float = 2.5,
        dropout_scale: float = 0.4,
        dropout_yaw_scale: float = 1.0,

        search_vyaw: float = 0.25,
        allow_backward: bool = False,

        stuck_warn_s: float = 1.0,
        stuck_cmd_min: float = 0.05,
        stuck_odom_step: float = 0.002,
        stuck_recover_s: float = 1.5,
        stuck_recover_vx: float = 0.24,

        lat_vx_assist: float = 0.0,
    ):
        self.target_dist = float(target_dist)

        self.hz = float(hz)
        # Proportional gains
        self.k_dist = float(k_dist)
        self.k_lat = float(k_lat)
        self.k_yaw = float(k_yaw)

        # Velocity limits
        self.max_vx = float(max_vx)
        self.max_vy = float(max_vy)
        self.max_vyaw = float(max_vyaw)
        self.min_vyaw = float(min_vyaw)

        # Minimum command magnitudes (deadband compensation)
        self.min_vx_cmd = float(min_vx_cmd)
        self.min_vy_cmd = float(min_vy_cmd)

        # Convert degree-based parameters to radians for internal use
        self.yaw_first = math.radians(float(yaw_first_deg))
        self.tol_dist = float(tol_dist)
        self.tol_lat = float(tol_lat)
        self.tol_yaw = math.radians(float(tol_yaw_deg))

        self.min_cmd_dist_margin = float(min_cmd_dist_margin)
        self.min_cmd_lat_margin = float(min_cmd_lat_margin)

        # Tag-loss timeout thresholds
        self.short_loss_s = float(short_loss_s)
        self.long_loss_s = float(long_loss_s)
        self.dropout_scale = float(dropout_scale)
        self.dropout_yaw_scale = float(dropout_yaw_scale)

        self.search_vyaw = float(search_vyaw)
        self.allow_backward = bool(allow_backward)

        # Stuck-detection parameters
        self.stuck_warn_s = float(stuck_warn_s)
        self.stuck_cmd_min = float(stuck_cmd_min)
        self.stuck_odom_step = float(stuck_odom_step)
        self.stuck_recover_s = float(stuck_recover_s)
        self.stuck_recover_vx = float(stuck_recover_vx)

        self.lat_vx_assist = float(lat_vx_assist)

        # Stuck-detection mutable state
        self._stuck_since_t: Optional[float] = None   # timestamp when stuck condition began
        self._last_stuck_warn_t: float = -1e9          # rate-limiter for stuck warnings

    def step(
        self,
        T_base_tag_pred: np.ndarray,
        tag_visible: bool,
        loss_dt: float,
        odom_step_xy: float,
        now: float,
    ) -> ControlOutput:
        """
        Run one control step and return velocity commands.

        Args:
          T_base_tag_pred - predicted tag pose in the robot base frame (4x4),
                            may come from the filter even when tag is not currently visible
          tag_visible     - whether the tag was detected in the most recent frame
          loss_dt         - seconds since the last accepted tag measurement
          odom_step_xy    - odometry displacement (m) since the previous step,
                            used by the stuck detector to check if the robot is moving
          now             - current timestamp (seconds)

        Returns:
          ControlOutput with velocity commands and controller status.
        """
        dist_along, lateral, yaw_err, e_dist, e_lat = compute_planar_errors_from_T_base_tag(
            T_base_tag_pred, self.target_dist
        )

        # Classify the tag-loss duration into time windows
        short_ok = loss_dt <= self.short_loss_s   # tag seen very recently — full servo
        long_lost = loss_dt >= self.long_loss_s   # tag gone too long — spin and search

        # --- Mode: SEARCH ---
        # Tag has been missing too long; spin in place to scan for it.
        if long_lost:
            return ControlOutput(
                vx=0.0, vy=0.0, vyaw=self.search_vyaw,
                done=False, mode="SEARCH", recovering=False
            )

        # --- Mode: PRED_YAW_REACQ ---
        # Tag not currently visible, but lost for less than long_loss_s.
        # Use the last known yaw estimate to rotate toward where the tag should be.
        if (not tag_visible) and (not short_ok):
            vyaw_cmd = self.k_yaw * float(yaw_err)
            # Apply minimum yaw rate to overcome static friction when not yet aligned
            if abs(yaw_err) > self.tol_yaw and abs(vyaw_cmd) < self.min_vyaw:
                vyaw_cmd = math.copysign(self.min_vyaw, yaw_err)
            # If already close to the correct heading, do a slow search spin instead
            if abs(yaw_err) <= self.tol_yaw:
                vyaw_cmd = math.copysign(self.search_vyaw, yaw_err if abs(yaw_err) > 1e-4 else 1.0)
            vyaw_cmd = clamp(vyaw_cmd, -self.max_vyaw, self.max_vyaw)
            return ControlOutput(
                vx=0.0, vy=0.0, vyaw=vyaw_cmd,
                done=False, mode="PRED_YAW_REACQ", recovering=False
            )

        # --- Mode: SERVO ---
        # Tag is visible or was seen within short_loss_s.
        # During brief dropouts, scale down translation to avoid overshooting on stale data.
        if tag_visible:
            trans_scale = 1.0           # full speed when tag is fresh
            yaw_scale = 1.0
        else:
            trans_scale = self.dropout_scale      # reduced translation on stale estimate
            yaw_scale = self.dropout_yaw_scale    # yaw authority may also be scaled

        # Yaw-first: if the heading error is large, suppress translation and rotate first.
        # This prevents the robot from driving sideways into an obstacle while misaligned.
        if abs(yaw_err) > self.yaw_first:
            vx_cmd = 0.0
            vy_cmd = 0.0
            vyaw_cmd = self.k_yaw * float(yaw_err)
        else:
            # All three axes are active: approach, strafe, and rotate simultaneously
            vx_cmd = self.k_dist * float(e_dist)
            vy_cmd = self.k_lat * float(e_lat)
            vyaw_cmd = self.k_yaw * float(yaw_err)

        # Prevent the robot from backing away unless explicitly allowed
        if (not self.allow_backward) and (vx_cmd < 0.0):
            vx_cmd = 0.0

        # Apply dropout scaling then clamp to velocity limits
        vx_cmd = clamp(vx_cmd * trans_scale, -self.max_vx, self.max_vx)
        vy_cmd = clamp(vy_cmd * trans_scale, -self.max_vy, self.max_vy)
        vyaw_cmd = vyaw_cmd * yaw_scale

        # Deadband compensation: if the error is non-trivial but the proportional
        # command is too small to overcome static friction, bump it up to min_v*_cmd.
        # Only applied when the tag is freshly visible and heading is acceptable.
        if tag_visible and abs(yaw_err) <= self.yaw_first:
            dist_thr = self.tol_dist + self.min_cmd_dist_margin
            lat_thr = self.tol_lat + self.min_cmd_lat_margin
            if abs(e_dist) > dist_thr and abs(vx_cmd) > 1e-6 and abs(vx_cmd) < self.min_vx_cmd:
                vx_cmd = math.copysign(self.min_vx_cmd, vx_cmd)
            if abs(e_lat) > lat_thr and abs(vy_cmd) > 1e-6 and abs(vy_cmd) < self.min_vy_cmd:
                vy_cmd = math.copysign(self.min_vy_cmd, vy_cmd)
                # Locomotion assist: small vy alone may not move the robot, but
                # vy + small vx can. If vx_cmd is below the assist threshold and
                # the robot is not yet past the target, apply a minimum forward push.
                if self.lat_vx_assist > 0 and e_dist > 0 and vx_cmd < self.lat_vx_assist:
                    vx_cmd = self.lat_vx_assist

        # Minimum yaw rate when a heading correction is needed (friction compensation)
        if abs(yaw_err) > self.tol_yaw and abs(vyaw_cmd) < self.min_vyaw:
            vyaw_cmd = math.copysign(self.min_vyaw, yaw_err)
        vyaw_cmd = clamp(vyaw_cmd, -self.max_vyaw, self.max_vyaw)

        # --- Stuck detection ---
        # If the controller is commanding significant motion but the odometry shows
        # the robot is barely moving, start the stuck timer.
        cmd_trans = math.hypot(vx_cmd, vy_cmd)
        if cmd_trans >= self.stuck_cmd_min and odom_step_xy < self.stuck_odom_step:
            if self._stuck_since_t is None:
                self._stuck_since_t = float(now)   # begin timing the stuck condition
            elif (now - self._stuck_since_t) >= self.stuck_warn_s and (now - self._last_stuck_warn_t) > 0.8:
                self._last_stuck_warn_t = float(now)  # rate-limited warning log opportunity
        else:
            self._stuck_since_t = None  # robot is moving — reset the timer

        # --- Recovery push ---
        # If stuck for long enough and heading is acceptable, override vx with a
        # minimum forward push to break free, and zero lateral / yaw to stay aligned.
        recovering = False
        if (self._stuck_since_t is not None and
            (now - self._stuck_since_t) >= self.stuck_recover_s and
            abs(yaw_err) <= self.yaw_first and
            e_dist > (self.tol_dist + self.min_cmd_dist_margin)):
            vx_cmd = max(abs(vx_cmd), self.stuck_recover_vx)  # at least the recovery speed
            vx_cmd = clamp(vx_cmd, 0.0, self.max_vx)
            vy_cmd = 0.0
            vyaw_cmd = 0.0
            recovering = True

        # --- Done condition ---
        # All three errors must be within tolerance AND the tag must be recently seen.
        done = (
            abs(e_dist) < self.tol_dist and
            abs(e_lat) < self.tol_lat and
            abs(yaw_err) < self.tol_yaw and
            loss_dt < 0.4
        )

        return ControlOutput(
            vx=float(vx_cmd),
            vy=float(vy_cmd),
            vyaw=float(vyaw_cmd),
            done=bool(done),
            mode="SERVO",
            recovering=bool(recovering),
        )