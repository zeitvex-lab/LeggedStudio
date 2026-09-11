"""
Detect AprilTag 36h11 ID=0 (180mm) and achieve fronto-parallel pose at 1m.

Phase 1 — Approach (proven trapezoidal):
  Trapezoidal vx + PD vyaw on atan2(lateral, depth).
  Fast, smooth, stops at ~1.0m. No lateral correction.

Phase 2 — Fine alignment (P controllers, small corrections):
  Robot is already close (~1.0m). Tag is large in frame = accurate pose.
  All three axes corrected simultaneously with P controllers:
    vx:   P on depth error      (nudge forward/backward to hit 1.0m)
    vy:   P on lateral error    (strafe to center on tag)
    vyaw: P on fronto_yaw       (rotate to face perpendicular)
  Converges when all three within tolerance for 1.5s.

Usage:
    python3 tag_approach_trapezoidal_v3.py [network_interface]
    python3 tag_approach_trapezoidal_v3.py eth0
"""

import sys
import os
import time
import math
import csv
import datetime
import numpy as np
import cv2
import pupil_apriltags as apriltag

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.video.video_client import VideoClient
from unitree_sdk2py.go2.sport.sport_client import SportClient

from camera_intrinsics import DOG_K_FISHEYE, DOG_D_FISHEYE, DOG_IMG_W, DOG_IMG_H

# ── Tag ──────────────────────────────────────────────────────────────────────
TAG_FAMILY = "tag36h11"
TAG_ID     = 0
TAG_SIZE   = 0.18         # meters

# ── Phase 1: Approach ────────────────────────────────────────────────────────
TARGET_DIST          = 1.0
STOP_THRESHOLD       = 0.03
DEPTH_OVERSHOOT_COMP = 0.06   # in-motion lag compensation

MAX_VX   = 0.7
ACCEL    = 0.5
DECEL    = 0.4

Kp_vyaw_approach = 1.8
Kd_vyaw_approach = 0.1
MAX_VYAW_APPROACH = 0.5

COAST_FRAMES = 3

# ── Phase 2: Fine alignment (trapezoidal vx + P vy/vyaw) ───────────────────
# Trapezoidal profile for depth — slower than Phase 1
P2_MAX_VX  = 0.3         # m/s   cruise speed
P2_ACCEL   = 0.4         # m/s²  ramp up
P2_DECEL   = 0.3         # m/s²  ramp down (braking)

# P gains for lateral and yaw (execute while gait is active from vx)
P2_KP_VY   = 1.9         # lateral error → vy
P2_KP_VYAW = 1.5         # fronto_yaw error → vyaw
P2_MAX_VY   = 0.20       # m/s
P2_MAX_VYAW = 0.40       # rad/s

# Convergence thresholds
P2_THRESH_DEPTH  = 0.03  # ±3 cm
P2_THRESH_LAT    = 0.06  # ±6 cm
P2_THRESH_FRONTO = math.radians(3.0)  # ±3°

# Must stay converged for this long
P2_CONVERGE_TIME = 0.5   # seconds

# Give up after this long
P2_TIMEOUT = 20.0        # seconds

# Input low-pass filters (at 1m range, fronto_yaw noise is moderate)
P2_ALPHA_DEPTH  = 0.6
P2_ALPHA_LAT    = 0.5
P2_ALPHA_FRONTO = 0.35

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_DIR = "/home/unitree/go2_sdk_docs/logs"

LOOP_HZ  = 50
INTERVAL = 1.0 / LOOP_HZ


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lpf(prev, new, alpha):
    if prev is None:
        return new
    return alpha * new + (1.0 - alpha) * prev


def build_undistort_maps():
    K_new = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
        DOG_K_FISHEYE, DOG_D_FISHEYE,
        (DOG_IMG_W, DOG_IMG_H), np.eye(3), balance=1.0)
    map1, map2 = cv2.fisheye.initUndistortRectifyMap(
        DOG_K_FISHEYE, DOG_D_FISHEYE,
        np.eye(3), K_new, (DOG_IMG_W, DOG_IMG_H), cv2.CV_16SC2)
    return map1, map2, K_new


def get_frame(video):
    code, data = video.GetImageSample()
    if code != 0:
        return None
    return cv2.imdecode(np.frombuffer(bytes(data), np.uint8), cv2.IMREAD_COLOR)


def detect_tag_simple(detector, frame, map1, map2, K_new):
    """Phase 1 detection: depth + lateral only (full resolution, no downscale)."""
    undistorted = cv2.remap(frame, map1, map2, cv2.INTER_LINEAR)
    gray = cv2.cvtColor(undistorted, cv2.COLOR_BGR2GRAY)

    devnull = os.open(os.devnull, os.O_WRONLY)
    old_out = os.dup(1)
    os.dup2(devnull, 1)
    detections = detector.detect(
        gray, estimate_tag_pose=True,
        camera_params=(K_new[0, 0], K_new[1, 1], K_new[0, 2], K_new[1, 2]),
        tag_size=TAG_SIZE)
    os.dup2(old_out, 1)
    os.close(devnull)
    os.close(old_out)

    for det in detections:
        if det.tag_id == TAG_ID:
            depth   = float(det.pose_t[2])
            lateral = float(det.pose_t[0])

            corners = det.corners.astype(int)
            cv2.polylines(undistorted, [corners], True, (0, 255, 0), 2)
            cx, cy = int(det.center[0]), int(det.center[1])
            cv2.circle(undistorted, (cx, cy), 6, (0, 0, 255), -1)
            yaw_deg = math.degrees(math.atan2(lateral, depth))
            cv2.putText(undistorted,
                        f"ID={det.tag_id}  dist={depth:.3f}m  yaw={yaw_deg:+.1f}deg",
                        (cx + 10, cy - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            return depth, lateral, undistorted

    return None, None, undistorted


def detect_tag_full(detector, frame, map1, map2, K_new):
    """Phase 2 detection: depth + lateral + fronto_yaw (full resolution)."""
    undistorted = cv2.remap(frame, map1, map2, cv2.INTER_LINEAR)
    gray = cv2.cvtColor(undistorted, cv2.COLOR_BGR2GRAY)

    devnull = os.open(os.devnull, os.O_WRONLY)
    old_out = os.dup(1)
    old_err = os.dup(2)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    detections = detector.detect(
        gray, estimate_tag_pose=True,
        camera_params=(K_new[0, 0], K_new[1, 1], K_new[0, 2], K_new[1, 2]),
        tag_size=TAG_SIZE)
    os.dup2(old_out, 1)
    os.dup2(old_err, 2)
    os.close(devnull)
    os.close(old_out)
    os.close(old_err)

    for det in detections:
        if det.tag_id != TAG_ID:
            continue

        depth   = float(det.pose_t[2])
        lateral = float(det.pose_t[0])

        R = np.array(det.pose_R)
        nx, nz = R[0, 2], R[2, 2]
        fronto_yaw = math.atan2(nx, nz)

        corners = det.corners.astype(int)
        center  = (int(det.center[0]), int(det.center[1]))
        cv2.polylines(undistorted, [corners], True, (0, 255, 0), 2)
        cv2.circle(undistorted, center, 6, (0, 0, 255), -1)
        cv2.putText(undistorted,
                    f"z={depth:.2f}m x={lateral:+.2f}m fp={math.degrees(fronto_yaw):+.1f}deg",
                    (center[0] + 10, center[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        return depth, lateral, fronto_yaw, undistorted

    return None, None, None, undistorted


def trapezoidal_vx(vx_current, remaining, dt):
    v_brake = math.sqrt(2.0 * DECEL * max(remaining, 0.0))
    v_accel = vx_current + ACCEL * dt
    v_cruise = min(v_accel, MAX_VX)
    vx_next = min(v_cruise, v_brake)
    return max(vx_next, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 1: Trapezoidal approach
# ══════════════════════════════════════════════════════════════════════════════
def phase1_approach(video, sport, detector, map1, map2, K_new, snapshot_path):
    """Drive to ~1m from tag. Returns True if reached, False if aborted."""
    print(f"\n═══ PHASE 1: Approach (trapezoidal, cruise={MAX_VX} m/s) ═══")
    print("Press Ctrl+C to stop.\n")

    vx_current     = 0.0
    prev_yaw_error = None
    prev_time      = time.time()
    lost_frames    = 0
    distance = lateral = None

    while True:
        frame = get_frame(video)
        if frame is None:
            time.sleep(INTERVAL)
            continue

        distance, lateral, annotated = detect_tag_simple(
            detector, frame, map1, map2, K_new)

        now = time.time()
        dt  = max(now - prev_time, 1e-3)
        prev_time = now

        # Tag lost
        if distance is None:
            lost_frames += 1
            if lost_frames <= COAST_FRAMES:
                sport.Move(vx_current, 0.0, 0.0)
            else:
                vx_current = max(vx_current - DECEL * dt, 0.0)
                if vx_current < 0.01:
                    vx_current = 0.0
                    sport.StopMove()
                    print("\nTag lost — stopped.")
                    return False
                sport.Move(vx_current, 0.0, 0.0)
            time.sleep(INTERVAL)
            continue

        lost_frames = 0
        remaining = distance - (TARGET_DIST + DEPTH_OVERSHOOT_COMP)

        # Reached target
        if remaining <= STOP_THRESHOLD:
            sport.StopMove()
            print(f"\n  Phase 1 done. In-motion depth: {distance:.4f}m")
            cv2.imwrite(snapshot_path, annotated)
            return True

        # Trapezoidal vx
        vx_current = trapezoidal_vx(vx_current, remaining, dt)

        # Yaw PD
        yaw_error = math.atan2(lateral, distance)
        d_yaw = ((yaw_error - prev_yaw_error) / dt
                 if prev_yaw_error is not None else 0.0)
        prev_yaw_error = yaw_error

        vyaw = -(Kp_vyaw_approach * yaw_error + Kd_vyaw_approach * d_yaw)
        vyaw = clamp(vyaw, -MAX_VYAW_APPROACH, MAX_VYAW_APPROACH)

        sport.Move(vx_current, 0.0, vyaw)

        print(f"  P1 | dist={distance:.3f}m  rem={remaining:+.3f}  "
              f"vx={vx_current:.3f}  vyaw={vyaw:+.3f}  "
              f"yaw={math.degrees(yaw_error):+.1f}deg   ",
              end="\r", flush=True)

        time.sleep(INTERVAL)

    return False


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 2: Fine alignment (trapezoidal vx + P vy/vyaw)
# ══════════════════════════════════════════════════════════════════════════════
def phase2_trapezoidal_vx(vx_current, remaining, dt):
    """Bidirectional trapezoidal profile for Phase 2 depth correction."""
    dist = abs(remaining)
    if dist < 0.005:
        return 0.0
    v_brake = math.sqrt(2.0 * P2_DECEL * dist)
    v_accel = abs(vx_current) + P2_ACCEL * dt
    v_cruise = min(v_accel, P2_MAX_VX)
    speed = min(v_cruise, v_brake)
    sign = 1.0 if remaining > 0 else -1.0
    return sign * max(speed, 0.0)


def phase2_align(video, sport, detector, map1, map2, K_new, snapshot_path):
    """
    Fine-tune position: depth=1.0m, lateral=0, fronto-parallel.
    Trapezoidal vx for depth + P controllers for vy/vyaw while gait is active.
    """
    print(f"\n═══ PHASE 2: Fine alignment (trapezoidal) ═══")
    print(f"  Targets: depth={TARGET_DIST}m  lateral=0  fronto=0deg")
    print(f"  Thresholds: ±{P2_THRESH_DEPTH*100:.0f}cm  "
          f"±{P2_THRESH_LAT*100:.0f}cm  "
          f"±{math.degrees(P2_THRESH_FRONTO):.0f}deg")
    print(f"  Timeout: {P2_TIMEOUT:.0f}s  Converge hold: {P2_CONVERGE_TIME:.1f}s")

    print("  Settling 1.5s...")
    time.sleep(1.5)

    # Open log
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOG_DIR, f"fp_align_{ts}.csv")
    log_fh = open(log_path, "w", newline="")
    log_cols = ["t_sec", "depth", "lateral", "fronto_deg",
                "err_depth", "err_lat", "err_fronto_deg",
                "vx", "vy", "vyaw", "converged", "dt_ms"]
    log_w = csv.DictWriter(log_fh, fieldnames=log_cols)
    log_w.writeheader()
    print(f"  Log -> {log_path}\n")

    depth_f = lat_f = fronto_f = None
    vx_current = 0.0
    converge_since = None
    start_time = time.time()
    prev_time = start_time
    lost_count = 0

    while True:
        frame = get_frame(video)
        if frame is None:
            time.sleep(INTERVAL)
            continue

        depth_raw, lat_raw, fronto_raw, annotated = detect_tag_full(
            detector, frame, map1, map2, K_new)

        now = time.time()
        dt = max(now - prev_time, 1e-3)
        prev_time = now
        t_rel = now - start_time

        if t_rel > P2_TIMEOUT:
            sport.StopMove()
            print(f"\n  Phase 2 timeout ({P2_TIMEOUT:.0f}s). Stopping.")
            break

        if depth_raw is None:
            lost_count += 1
            if lost_count > 10:
                sport.StopMove()
                print("\n  Tag lost in Phase 2. Stopping.")
                break
            sport.Move(vx_current, 0.0, 0.0)
            time.sleep(INTERVAL)
            continue

        lost_count = 0

        # Filter
        depth_f  = lpf(depth_f,  depth_raw,  P2_ALPHA_DEPTH)
        lat_f    = lpf(lat_f,    lat_raw,    P2_ALPHA_LAT)
        fronto_f = lpf(fronto_f, fronto_raw, P2_ALPHA_FRONTO)

        # Errors
        err_depth  = depth_f - TARGET_DIST    # + = too far → forward
        err_lat    = lat_f                     # + = tag right
        err_fronto = fronto_f                  # + = tag face rotated right

        # Convergence check
        d_ok = abs(err_depth)  <= P2_THRESH_DEPTH
        l_ok = abs(err_lat)    <= P2_THRESH_LAT
        f_ok = abs(err_fronto) <= P2_THRESH_FRONTO
        all_ok = d_ok and l_ok and f_ok

        if all_ok:
            if converge_since is None:
                converge_since = now
            elif now - converge_since >= P2_CONVERGE_TIME:
                sport.StopMove()
                print(f"\n  [DONE] Fronto-parallel converged!")
                print(f"    depth={depth_f:.4f}m  lat={lat_f:+.4f}m  "
                      f"fronto={math.degrees(fronto_f):+.2f}deg")
                cv2.imwrite(snapshot_path, annotated)
                print(f"    Snapshot -> {snapshot_path}")
                log_fh.flush()
                log_fh.close()
                print(f"    Log -> {log_path}")
                return True
        else:
            converge_since = None

        # ── vx: trapezoidal profile toward TARGET_DIST ──
        vx_current = phase2_trapezoidal_vx(vx_current, err_depth, dt)

        # ── vy: P on lateral (tag right → strafe right → -vy) ──
        vy = clamp(-P2_KP_VY * err_lat, -P2_MAX_VY, P2_MAX_VY)

        # ── vyaw: P on fronto (fronto>0 → turn right → -vyaw) ──
        vyaw = clamp(-P2_KP_VYAW * err_fronto, -P2_MAX_VYAW, P2_MAX_VYAW)

        sport.Move(vx_current, vy, vyaw)

        # Log
        dt_ms = (time.time() - now) * 1000 + INTERVAL * 1000
        log_w.writerow({
            "t_sec": f"{t_rel:.4f}",
            "depth": f"{depth_f:.4f}",
            "lateral": f"{lat_f:+.4f}",
            "fronto_deg": f"{math.degrees(fronto_f):+.3f}",
            "err_depth": f"{err_depth:+.4f}",
            "err_lat": f"{err_lat:+.4f}",
            "err_fronto_deg": f"{math.degrees(err_fronto):+.3f}",
            "vx": f"{vx_current:+.4f}",
            "vy": f"{vy:+.4f}",
            "vyaw": f"{vyaw:+.4f}",
            "converged": 1 if all_ok else 0,
            "dt_ms": f"{dt_ms:.1f}",
        })

        hold_str = ""
        if converge_since is not None:
            hold_str = f" HOLD {now - converge_since:.1f}s"
        print(
            f"  P2 | "
            f"z={depth_f:.3f}({err_depth:+.3f}) "
            f"x={lat_f:+.3f} "
            f"fp={math.degrees(fronto_f):+5.1f}deg | "
            f"vx={vx_current:+.3f} vy={vy:+.3f} vyaw={vyaw:+.3f}"
            f"{hold_str}   ",
            end="\r", flush=True
        )

        time.sleep(INTERVAL)

    log_fh.flush()
    log_fh.close()
    print(f"  Log -> {log_path}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if len(sys.argv) > 1:
        ChannelFactoryInitialize(0, sys.argv[1])
    else:
        ChannelFactoryInitialize(0)

    video = VideoClient()
    video.SetTimeout(5.0)
    video.Init()

    sport = SportClient()
    sport.SetTimeout(10.0)
    sport.Init()

    print("Building undistortion maps...")
    map1, map2, K_new = build_undistort_maps()
    detector = apriltag.Detector(families=TAG_FAMILY)

    snapshot_path = "/home/unitree/go2_sdk_docs/detection_snapshot.jpg"

    # Scan for tag
    print(f"Scanning for {TAG_FAMILY} ID={TAG_ID} ({TAG_SIZE*1000:.0f}mm)...")
    distance = None
    try:
        while distance is None:
            frame = get_frame(video)
            if frame is None:
                time.sleep(INTERVAL)
                continue
            distance, lateral, annotated = detect_tag_simple(
                detector, frame, map1, map2, K_new)
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\nAborted.")
        return

    cv2.imwrite(snapshot_path, annotated)
    print(f"Tag found!  depth={distance:.4f}m  lateral={lateral:+.4f}m\n")

    if distance <= TARGET_DIST + STOP_THRESHOLD:
        print("Already at target — skipping Phase 1.")
    else:
        try:
            ok = phase1_approach(video, sport, detector, map1, map2, K_new, snapshot_path)
            if not ok:
                print("Phase 1 failed.")
                return
        except KeyboardInterrupt:
            sport.StopMove()
            print("\n[STOPPED in Phase 1]")
            return

    try:
        phase2_align(video, sport, detector, map1, map2, K_new, snapshot_path)
    except KeyboardInterrupt:
        sport.StopMove()
        print("\n[STOPPED in Phase 2]")


if __name__ == "__main__":
    main()
