"""
Detect AprilTag 36h11 ID=0 (180mm) with the Go2 front fisheye camera,
then drive to exactly 1m in front of it using:
  - Trapezoidal velocity profile for forward axis (accelerate → cruise → decelerate)
  - PD controller for yaw axis (align to tag center)

The trapezoidal profile guarantees the velocity is always physically executable
right up to the stop point — no minimum velocity clamping needed.

Usage:
    python3 tag_approach_trapezoidal.py [network_interface]
    python3 tag_approach_trapezoidal.py eth0
"""

import sys
import os
import time
import math
import numpy as np
import cv2
import pupil_apriltags as apriltag

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.video.video_client import VideoClient
from unitree_sdk2py.go2.sport.sport_client import SportClient

from camera_intrinsics import DOG_K_FISHEYE, DOG_D_FISHEYE, DOG_IMG_W, DOG_IMG_H

# ── Config ─────────────────────────────────────────────────────────────────────
TAG_FAMILY     = "tag36h11"
TAG_ID         = 0
TAG_SIZE       = 0.18    # 180 mm → meters
TARGET_DIST    = 1.0     # desired final distance from tag (meters)
STOP_THRESHOLD = 0.03    # stop when within 3 cm of target
# In-motion depth reads ~6cm farther than actual (motion blur + detection lag).
# Compensate by aiming 6cm farther so the robot stops at the real 1.0m.
DEPTH_OVERSHOOT_COMP = 0.06

LOOP_HZ = 50             # control loop rate

# Trapezoidal profile — forward axis
MAX_VX   = 0.7    # m/s    cruise speed
ACCEL    = 0.5    # m/s²   acceleration rate (ramp up)
DECEL    = 0.4    # m/s²   deceleration rate (ramp down)
#
# The braking distance formula: v_brake = sqrt(2 * DECEL * remaining)
# This gives the speed that will decelerate to exactly 0 at the target.
# The profile takes the minimum of (current ramp-up speed) and (v_brake),
# so it naturally slows to 0 without any minimum clamping.

# PD gains — yaw axis only
Kp_vyaw = 1.8    # P: rotate proportional to angle error
Kd_vyaw = 0.1    # D: damp oscillation
MAX_VYAW = 0.5   # rad/s

# Coast window — frames to hold last velocity when tag is briefly lost
# At 50 Hz, 6 frames = 120 ms (covers gait-induced motion blur)
COAST_FRAMES = 3
# ───────────────────────────────────────────────────────────────────────────────


def build_undistort_maps():
    """Pre-compute fisheye undistortion maps once at startup."""
    K_new = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
        DOG_K_FISHEYE, DOG_D_FISHEYE,
        (DOG_IMG_W, DOG_IMG_H),
        np.eye(3),
        balance=1.0
    )
    map1, map2 = cv2.fisheye.initUndistortRectifyMap(
        DOG_K_FISHEYE, DOG_D_FISHEYE,
        np.eye(3), K_new,
        (DOG_IMG_W, DOG_IMG_H),
        cv2.CV_16SC2
    )
    return map1, map2, K_new


def get_frame(video_client):
    """Grab one JPEG frame from the robot camera and decode it."""
    code, data = video_client.GetImageSample()
    if code != 0:
        return None
    arr = np.frombuffer(bytes(data), dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def detect_tag(detector, frame, map1, map2, K_new):
    """
    Undistort fisheye frame and detect AprilTag ID=TAG_ID.
    Returns (depth, lateral, annotated) or (None, None, annotated).
      depth   = Z in camera frame (meters, along optical axis)
      lateral = X in camera frame (meters, positive = tag to the right)
    """
    undistorted = cv2.remap(frame, map1, map2, cv2.INTER_LINEAR)
    gray = cv2.cvtColor(undistorted, cv2.COLOR_BGR2GRAY)

    # Suppress "Error, more than one new minima found" from the C library
    devnull    = os.open(os.devnull, os.O_WRONLY)
    old_stdout = os.dup(1)
    os.dup2(devnull, 1)
    detections = detector.detect(
        gray,
        estimate_tag_pose=True,
        camera_params=(K_new[0, 0], K_new[1, 1], K_new[0, 2], K_new[1, 2]),
        tag_size=TAG_SIZE
    )
    os.dup2(old_stdout, 1)
    os.close(devnull)
    os.close(old_stdout)

    for det in detections:
        if det.tag_id == TAG_ID:
            depth   = float(det.pose_t[2])
            lateral = float(det.pose_t[0])

            corners = det.corners.astype(int)
            cv2.polylines(undistorted, [corners], isClosed=True,
                          color=(0, 255, 0), thickness=2)
            cx_tag, cy_tag = int(det.center[0]), int(det.center[1])
            cv2.circle(undistorted, (cx_tag, cy_tag), 6, (0, 0, 255), -1)
            yaw_deg = math.degrees(math.atan2(lateral, depth))
            cv2.putText(undistorted,
                        f"ID={det.tag_id}  dist={depth:.3f}m  yaw={yaw_deg:+.1f}deg",
                        (cx_tag + 10, cy_tag - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            return depth, lateral, undistorted

    return None, None, undistorted


def trapezoidal_vx(vx_current, remaining, dt):
    """
    Compute the next forward velocity using a trapezoidal profile.

    Three regions:
      1. Braking zone  — v_brake = sqrt(2 * DECEL * remaining)
                         If current speed > v_brake, decelerate.
      2. Cruise zone   — hold MAX_VX.
      3. Accel zone    — ramp up by ACCEL * dt each step.

    The profile always takes the minimum of (ramped-up speed) and (v_brake),
    so it naturally decelerates to 0 exactly at the target.
    """
    # Speed needed to stop exactly at target given current distance
    v_brake = math.sqrt(2.0 * DECEL * max(remaining, 0.0))

    # Ramp up from current speed
    v_accel = vx_current + ACCEL * dt

    # Cruise cap
    v_cruise = min(v_accel, MAX_VX)

    # Take whichever is lower: cruise ramp or braking curve
    vx_next = min(v_cruise, v_brake)

    return max(vx_next, 0.0)   # never negative


def main():
    # ── DDS init ───────────────────────────────────────────────────────────────
    if len(sys.argv) > 1:
        ChannelFactoryInitialize(0, sys.argv[1])
    else:
        ChannelFactoryInitialize(0)

    # ── Clients ────────────────────────────────────────────────────────────────
    video = VideoClient()
    video.SetTimeout(5.0)
    video.Init()

    sport = SportClient()
    sport.SetTimeout(10.0)
    sport.Init()

    # ── Pre-compute undistortion maps ─────────────────────────────────────────
    print("Building undistortion maps...")
    map1, map2, K_new = build_undistort_maps()

    # ── AprilTag detector ──────────────────────────────────────────────────────
    detector = apriltag.Detector(families=TAG_FAMILY)

    interval     = 1.0 / LOOP_HZ
    snapshot_path = "/home/unitree/go2_sdk_docs/detection_snapshot.jpg"

    # ── Phase 1: scan until tag is found ──────────────────────────────────────
    print(f"Scanning for {TAG_FAMILY} ID={TAG_ID} (size={TAG_SIZE*1000:.0f}mm)...")
    print("Press Ctrl+C to abort.\n")

    distance = lateral = None
    frame_count = 0
    try:
        while distance is None:
            frame = get_frame(video)
            if frame is None:
                time.sleep(interval)
                continue

            frame_count += 1
            distance, lateral, annotated = detect_tag(detector, frame, map1, map2, K_new)

            if frame_count % 30 == 0:
                print(".", end="", flush=True)

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nAborted.")
        return

    print()
    cv2.imwrite(snapshot_path, annotated)
    print(f"Tag found!  depth={distance:.4f}m")
    print(f"Snapshot saved → {snapshot_path}")

    if distance <= TARGET_DIST + STOP_THRESHOLD:
        print(f"Already at or closer than {TARGET_DIST}m — no movement needed.")
        return

    print(f"\nApproaching with trapezoidal profile "
          f"(cruise={MAX_VX} m/s  accel={ACCEL} m/s²  decel={DECEL} m/s²)...")
    print("Press Ctrl+C to stop.\n")

    # ── Phase 2: trapezoidal approach + yaw PD ────────────────────────────────
    vx_current      = 0.0    # current forward speed (profile state)
    prev_yaw_error  = None
    prev_time       = time.time()
    lost_frames     = 0

    try:
        while True:
            frame = get_frame(video)
            if frame is None:
                time.sleep(interval)
                continue

            distance, lateral, annotated = detect_tag(detector, frame, map1, map2, K_new)

            now = time.time()
            dt  = max(now - prev_time, 1e-3)
            prev_time = now

            # ── Tag lost handling ──────────────────────────────────────────────
            if distance is None:
                lost_frames += 1
                if lost_frames <= COAST_FRAMES:
                    # Coast: keep sending current velocity, profile freezes
                    sport.Move(vx_current, 0.0, 0.0)
                    print(f"Tag gap ({lost_frames}/{COAST_FRAMES}) — "
                          f"coasting at vx={vx_current:.3f}",
                          end="\r", flush=True)
                else:
                    # Decelerate gracefully using the profile (remaining unknown,
                    # so just ramp down by one DECEL step)
                    vx_current = max(vx_current - DECEL * dt, 0.0)
                    if vx_current < 0.01:
                        vx_current = 0.0
                        sport.StopMove()
                        print("\nTag lost — stopped.                        ")
                    else:
                        sport.Move(vx_current, 0.0, 0.0)
                time.sleep(interval)
                continue

            lost_frames = 0
            remaining = distance - (TARGET_DIST + DEPTH_OVERSHOOT_COMP)

            # ── Stop check ────────────────────────────────────────────────────
            if remaining <= STOP_THRESHOLD:
                sport.StopMove()
                print(f"\nReached target. Last loop distance: {distance:.4f}m")
                cv2.imwrite(snapshot_path, annotated)
                print(f"Final snapshot saved → {snapshot_path}")

                # ── Post-stop verification: re-measure distance ───────────
                print("\nWaiting 2s for robot to settle...")
                time.sleep(2.0)

                print("Re-measuring distance (5 samples)...")
                measurements = []
                for i in range(20):
                    f2 = get_frame(video)
                    if f2 is None:
                        time.sleep(interval)
                        continue
                    d2, l2, ann2 = detect_tag(detector, f2, map1, map2, K_new)
                    if d2 is not None:
                        measurements.append((d2, l2))
                        print(f"  sample {len(measurements)}: depth={d2:.4f}m  lateral={l2:+.4f}m")
                        if len(measurements) >= 5:
                            break
                    time.sleep(interval)

                if measurements:
                    avg_depth = sum(m[0] for m in measurements) / len(measurements)
                    avg_lat   = sum(m[1] for m in measurements) / len(measurements)
                    cv2.imwrite(snapshot_path, ann2)
                    print(f"\n  ── Verification ──────────────────────────")
                    print(f"  Last loop reading:  depth={distance:.4f}m")
                    print(f"  Post-stop average:  depth={avg_depth:.4f}m  "
                          f"lateral={avg_lat:+.4f}m")
                    print(f"  Difference:         {avg_depth - distance:+.4f}m")
                    print(f"  Actual remaining:   {avg_depth - TARGET_DIST:+.4f}m")
                    print(f"  ─────────────────────────────────────────")
                else:
                    print("  Could not re-detect tag for verification.")

                break

            # ── Forward: trapezoidal profile ──────────────────────────────────
            vx_current = trapezoidal_vx(vx_current, remaining, dt)

            # ── Yaw: PD controller ────────────────────────────────────────────
            yaw_error = math.atan2(lateral, distance)   # + = tag to right
            d_yaw = ((yaw_error - prev_yaw_error) / dt
                     if prev_yaw_error is not None else 0.0)
            prev_yaw_error = yaw_error

            vyaw = -(Kp_vyaw * yaw_error + Kd_vyaw * d_yaw)
            vyaw = max(-MAX_VYAW, min(MAX_VYAW, vyaw))

            sport.Move(vx_current, 0.0, vyaw)

            yaw_deg = math.degrees(yaw_error)
            print(f"dist={distance:.4f}m  rem={remaining:+.4f}m  "
                  f"vx={vx_current:.3f}  vyaw={vyaw:+.3f}  "
                  f"yaw_err={yaw_deg:+.1f}deg    ",
                  end="\r", flush=True)

            time.sleep(interval)

    except KeyboardInterrupt:
        sport.StopMove()
        print(f"\nStopped by user. Last distance: {distance:.4f}m"
              if distance else "\nStopped by user.")


if __name__ == "__main__":
    main()
