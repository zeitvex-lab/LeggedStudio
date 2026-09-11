#!/usr/bin/env python3
"""
pose_filter.py
==============
Stage 2:
  - Outlier rejection + smoothing + dropout behavior
  - Maintains T_odom_tag_est (same as your previous script)
  - Predicts T_base_tag_pred = inv(T_odom_base) @ T_odom_tag_est

NO control commands here.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
import math


def wrap_pi(a: float) -> float:
    """
    Wrap an angle (radians) into the range (-pi, pi].

    Iterative unwrapping handles angles that are more than one full rotation
    outside the target range (e.g. after accumulating odometry drift).
    """
    while a <= -math.pi:
        a += 2.0 * math.pi
    while a > math.pi:
        a -= 2.0 * math.pi
    return a


def inv_T(T: np.ndarray) -> np.ndarray:
    """
    Compute the inverse of a 4x4 rigid-body (SE(3)) transform analytically.

    For a rotation+translation matrix T = [R | t; 0 | 1], the inverse is:
      T^-1 = [R^T | -R^T * t; 0 | 1]

    This is faster and numerically cleaner than np.linalg.inv for SE(3) matrices.
    """
    R = T[:3, :3]
    t = T[:3, 3]
    Ti = np.eye(4, dtype=np.float64)
    Ti[:3, :3] = R.T          # inverse rotation = transpose
    Ti[:3, 3] = -R.T @ t      # inverse translation
    return Ti


def R_to_quat(R: np.ndarray) -> np.ndarray:
    """
    Convert a 3x3 rotation matrix to a unit quaternion [w, x, y, z].

    Uses Shepperd's method: choose the formula based on which diagonal element
    of R is largest to avoid near-zero division and maximise numerical stability.
    The result is always normalised before returning.
    """
    tr = np.trace(R)
    if tr > 0:
        # Trace is positive: standard formula is numerically safe
        S = math.sqrt(tr + 1.0) * 2.0  # S = 4w
        w = 0.25 * S
        x = (R[2, 1] - R[1, 2]) / S
        y = (R[0, 2] - R[2, 0]) / S
        z = (R[1, 0] - R[0, 1]) / S
    else:
        # Trace ≤ 0: pick the largest diagonal element to avoid dividing by ~0
        if (R[0, 0] > R[1, 1]) and (R[0, 0] > R[2, 2]):
            # R[0,0] is largest diagonal → x is the dominant component
            S = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0  # S = 4x
            w = (R[2, 1] - R[1, 2]) / S
            x = 0.25 * S
            y = (R[0, 1] + R[1, 0]) / S
            z = (R[0, 2] + R[2, 0]) / S
        elif R[1, 1] > R[2, 2]:
            # R[1,1] is largest diagonal → y is the dominant component
            S = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0  # S = 4y
            w = (R[0, 2] - R[2, 0]) / S
            x = (R[0, 1] + R[1, 0]) / S
            y = 0.25 * S
            z = (R[1, 2] + R[2, 1]) / S
        else:
            # R[2,2] is largest diagonal → z is the dominant component
            S = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0  # S = 4z
            w = (R[1, 0] - R[0, 1]) / S
            x = (R[0, 2] + R[2, 0]) / S
            y = (R[1, 2] + R[2, 1]) / S
            z = 0.25 * S
    q = np.array([w, x, y, z], dtype=np.float64)
    q /= np.linalg.norm(q) + 1e-12  # normalise; epsilon prevents div-by-zero
    return q


def quat_to_R(q: np.ndarray) -> np.ndarray:
    """
    Convert a unit quaternion [w, x, y, z] to a 3x3 rotation matrix.

    Standard closed-form expansion of the quaternion rotation formula.
    Assumes |q| = 1 (caller is responsible for normalisation).
    """
    w, x, y, z = q
    R = np.array([
        [1 - 2*(y*y + z*z),     2*(x*y - z*w),     2*(x*z + y*w)],
        [    2*(x*y + z*w), 1 - 2*(x*x + z*z),     2*(y*z - x*w)],
        [    2*(x*z - y*w),     2*(y*z + x*w), 1 - 2*(x*x + y*y)]
    ], dtype=np.float64)
    return R


def slerp(q0: np.ndarray, q1: np.ndarray, a: float) -> np.ndarray:
    """
    Spherical linear interpolation (SLERP) between two quaternions.

    Interpolates along the shortest arc on the unit 4-sphere:
      a=0 returns q0, a=1 returns q1.

    Handles two edge cases:
      1. Antipodal quaternions (dot < 0): negate q1 to take the short path.
      2. Nearly identical quaternions (dot > 0.9995): fall back to normalised
         linear interpolation (NLERP) to avoid numerical issues with acos.
    """
    # Normalise inputs to ensure they sit on the unit sphere
    q0 = q0 / (np.linalg.norm(q0) + 1e-12)
    q1 = q1 / (np.linalg.norm(q1) + 1e-12)
    dot = float(np.dot(q0, q1))

    # If the dot product is negative, the quaternions are on opposite hemispheres.
    # Flip q1 so we travel along the shorter arc.
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    dot = max(min(dot, 1.0), -1.0)  # clamp to [-1, 1] to guard against acos domain errors

    if dot > 0.9995:
        # Quaternions are very close — NLERP is a safe, cheap approximation
        q = q0 + a * (q1 - q0)
        q /= np.linalg.norm(q) + 1e-12
        return q

    # Standard SLERP formula
    theta0 = math.acos(dot)        # angle between q0 and q1
    theta = theta0 * a             # fraction of that angle to travel
    sin_theta0 = math.sin(theta0)
    s0 = math.cos(theta) - dot * math.sin(theta) / sin_theta0
    s1 = math.sin(theta) / sin_theta0
    q = s0 * q0 + s1 * q1
    q /= np.linalg.norm(q) + 1e-12
    return q


def blend_T(T0: np.ndarray, T1: np.ndarray, a: float) -> np.ndarray:
    """
    Smoothly interpolate between two 4x4 SE(3) transforms at fraction a.

    Translation is blended with standard linear interpolation (LERP).
    Rotation is blended with SLERP via an intermediate quaternion representation
    to guarantee the result remains a valid rotation matrix.

    a=0 returns T0, a=1 returns T1.
    """
    R0, t0 = T0[:3, :3], T0[:3, 3]
    R1, t1 = T1[:3, :3], T1[:3, 3]
    # Convert rotation matrices to quaternions for SLERP
    q0 = R_to_quat(R0)
    q1 = R_to_quat(R1)
    q = slerp(q0, q1, a)                # interpolated rotation as quaternion
    t = (1.0 - a) * t0 + a * t1        # linearly interpolated translation

    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = quat_to_R(q)           # convert back to rotation matrix
    T[:3, 3] = t
    return T


def compute_planar_metrics_for_gating(T_base_tag: np.ndarray) -> Tuple[float, float, float]:
    """
    Compute planar navigation metrics from a base→tag transform for outlier gating.

    Projects the 3-D tag position and orientation into the ground (XY) plane and
    decomposes them into three scalar values that are easy to threshold:
      dist_along - distance along the forward direction to the tag (metres)
      lateral    - signed lateral offset perpendicular to forward (metres)
      yaw_err    - heading angle from the robot toward the tag (radians, in (-pi, pi])

    "Forward direction" is derived from the tag's surface normal projected onto XY:
    the tag face normal (tag Z axis in camera / base frame) should roughly point
    back toward the robot, so we pick the normal direction that best aligns with
    the vector from tag to robot.  If the projected normal is degenerate (near-zero
    XY component) we fall back to using the tag position direction directly.

    Used ONLY for measurement jump gating — not for control.
    """
    p = T_base_tag[:3, 3].copy()   # tag origin in base frame (metres)
    R = T_base_tag[:3, :3].copy()  # rotation part of the transform

    p_xy = p[:2]
    p_norm = float(np.linalg.norm(p_xy))
    if p_norm < 1e-6:
        # Tag is essentially at the robot's origin — metrics are undefined
        return 0.0, 0.0, 0.0

    # Project the tag's Z-axis (surface normal) into the horizontal plane
    n = R @ np.array([0.0, 0.0, 1.0], dtype=np.float64)
    n_xy = n[:2]
    n_norm = float(np.linalg.norm(n_xy))

    if n_norm < 1e-6:
        # Degenerate normal (tag facing straight up/down) — use position direction
        forward_dir = p_xy / p_norm
    else:
        n_xy = n_xy / n_norm
        # Choose the normal direction that faces the robot (opposite to tag position)
        if float(np.dot(-n_xy, p_xy)) > float(np.dot(n_xy, p_xy)):
            forward_dir = -n_xy
        else:
            forward_dir = n_xy
        forward_dir = forward_dir / (np.linalg.norm(forward_dir) + 1e-12)

    # Left direction is 90° counter-clockwise from forward in the XY plane
    left_dir = np.array([-forward_dir[1], forward_dir[0]], dtype=np.float64)

    dist_along = float(np.dot(p_xy, forward_dir))  # range to tag along forward axis
    lateral = float(np.dot(p_xy, left_dir))         # lateral deviation from forward axis
    yaw_err = wrap_pi(math.atan2(forward_dir[1], forward_dir[0]))  # heading angle
    return dist_along, lateral, yaw_err


@dataclass
class FusionResult:
    """
    Output of TagFusionFilter.update() for one timestep.

    Fields:
      has_estimate      - True if the filter holds a valid tag position estimate
      tag_visible_used  - True if this update actually incorporated a tag measurement
                          (False when the tag was detected but rejected as an outlier)
      meas_rejected     - True if the incoming measurement was discarded by the jump gate
      T_base_tag_pred   - 4x4 transform: predicted tag position in the robot base frame
                          (None if has_estimate is False, i.e. the tag has never been seen)
    """
    has_estimate: bool
    tag_visible_used: bool
    meas_rejected: bool
    T_base_tag_pred: Optional[np.ndarray]  # 4x4 if has_estimate


class TagFusionFilter:
    """
    Fuses noisy AprilTag measurements into a stable tag-position estimate.

    Maintains T_odom_tag_est — the estimated tag pose in the odometry frame —
    which is persistent even when the tag is temporarily invisible.  Each call
    to update() optionally incorporates a new measurement and always returns a
    freshly predicted T_base_tag (tag in the current robot base frame).

    Two-stage measurement pipeline:
      1. Jump gate: reject measurements that jump too far from the current
         estimate in both yaw AND distance simultaneously (likely detection noise).
      2. Exponential smoothing: blend accepted measurements into the estimate
         using a fixed alpha weight (SLERP for rotation, LERP for translation).

    Args:
      alpha_tag              - smoothing weight for new measurements in [0, 1];
                               higher = faster response, lower = more smoothing
      max_meas_yaw_jump_deg  - yaw jump threshold for the outlier gate (degrees)
      max_meas_dist_jump     - distance jump threshold for the outlier gate (metres)
    """
    def __init__(
        self,
        alpha_tag: float = 0.25,
        max_meas_yaw_jump_deg: float = 70.0,
        max_meas_dist_jump: float = 0.35,
    ):
        self.alpha_tag = float(alpha_tag)
        self.max_meas_yaw_jump = math.radians(float(max_meas_yaw_jump_deg))  # store in radians
        self.max_meas_dist_jump = float(max_meas_dist_jump)

        self.T_odom_tag_est: Optional[np.ndarray] = None  # filter state; None until first detection
        self.last_seen_t: float = -1e9   # timestamp of last accepted measurement
        self.last_meas_t: float = -1e9   # timestamp of last attempted measurement (accepted or not)

    def has_estimate(self) -> bool:
        """Return True once the filter has incorporated at least one measurement."""
        return self.T_odom_tag_est is not None

    def loss_dt(self, now: float) -> float:
        """Seconds elapsed since the last accepted tag measurement."""
        return float(now - self.last_seen_t)

    def update(self, T_odom_base: np.ndarray, tag_visible: bool, T_base_tag_meas: Optional[np.ndarray], now: float) -> FusionResult:
        """
        Incorporate one observation and produce a pose prediction.

        Args:
          T_odom_base      - current robot base pose in the odometry frame (4x4)
          tag_visible      - whether the camera detected the tag this frame
          T_base_tag_meas  - raw measured tag pose in the base frame (4x4), or None
          now              - current timestamp (seconds)

        Returns:
          FusionResult with the updated state and predicted tag pose.
        """
        meas_rejected = False
        tag_visible_used = bool(tag_visible)

        if tag_visible and (T_base_tag_meas is not None):
            accept_meas = True  # tentatively accept until the jump gate says otherwise

            if self.T_odom_tag_est is not None:
                # Re-project the current estimate into the base frame so we can
                # compare it directly against the new measurement.
                T_base_tag_prev = inv_T(T_odom_base) @ self.T_odom_tag_est

                # Compute planar metrics for both the new measurement and the estimate
                dm, lm, ym = compute_planar_metrics_for_gating(T_base_tag_meas)
                dp, lp, yp = compute_planar_metrics_for_gating(T_base_tag_prev)

                yaw_jump = abs(wrap_pi(ym - yp))   # angular change between frames
                dist_jump = abs(dm - dp)             # range change between frames
                # lateral jump not used in decision (kept same as your original accept rule)

                # Reject only when BOTH yaw and distance jump exceed their thresholds;
                # requiring both to be violated reduces false rejections on curved approach paths.
                if (yaw_jump > self.max_meas_yaw_jump) and (dist_jump > self.max_meas_dist_jump):
                    accept_meas = False
                    meas_rejected = True

            if accept_meas:
                # Transform the accepted measurement into the odometry frame for storage
                T_odom_tag_meas = T_odom_base @ T_base_tag_meas
                if self.T_odom_tag_est is None:
                    # First ever detection — initialise the filter directly
                    self.T_odom_tag_est = T_odom_tag_meas
                else:
                    # Blend the new measurement into the running estimate (exponential smoothing)
                    self.T_odom_tag_est = blend_T(self.T_odom_tag_est, T_odom_tag_meas, self.alpha_tag)
                self.last_seen_t = float(now)
                self.last_meas_t = float(now)
            else:
                tag_visible_used = False  # measurement was seen but not used

        # Project the odometry-frame estimate back into the current base frame for output
        T_base_tag_pred = None
        if self.T_odom_tag_est is not None:
            T_base_tag_pred = inv_T(T_odom_base) @ self.T_odom_tag_est

        return FusionResult(
            has_estimate=(self.T_odom_tag_est is not None),
            tag_visible_used=tag_visible_used,
            meas_rejected=meas_rejected,
            T_base_tag_pred=T_base_tag_pred
        )