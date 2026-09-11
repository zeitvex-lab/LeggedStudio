#!/usr/bin/env python3
"""
main.py (short, commented)
==========================
This is the single entry point you run.

Pipeline in each control cycle
------------------------------
  (A) Read odom (SportModeState_): x, y, yaw
  (B) Read latest camera frame (BGR)
  (C) vision_pose.py:
        - undistort image
        - detect AprilTag
        - output raw pose T_cam_tag
  (D) Convert pose to base frame using known extrinsic:
        T_base_tag_meas = T_base_cam @ T_cam_tag
  (E) pose_filter.py:
        - outlier rejection + smoothing in odom frame
        - maintain T_odom_tag_est
        - predict relative pose: T_base_tag_pred
  (F) dock_control.py:
        - compute errors from T_base_tag_pred
        - compute (vx, vy, vyaw) command
  (G) Send command: SportClient.Move(vx, vy, vyaw)
  (H) Log CSV + readable INFO lines

By design, the three algorithm modules stay independent:
  - vision_pose.py
  - pose_filter.py
  - dock_control.py

All Unitree init / threads / shutdown are in go2_io.py.
"""

import argparse
import math
import signal
import sys
import time

import numpy as np
import cv2

from go2_io import Go2IO, setup_logger_and_paths, open_trace_csv
from vision_pose import VisionPoseEstimator
from pose_filter import TagFusionFilter
from dock_control import DockingController, compute_planar_errors_from_T_base_tag


# =============================================================================
# CLI / tuning parameters
# =============================================================================

def parse_args():
    """
    All tuning knobs live here so you can iterate without editing code:
      - loop rate: --hz
      - gains: --k_dist, --k_lat, --k_yaw
      - limits: --max_vx, --max_vy, --max_vyaw
      - tag settings: --tag_id, --tag_size, --tag_family
      - fusion: --alpha_tag, jump thresholds
      - dropout/search: short/long loss timings, search yaw speed
      - stuck recovery parameters
    """
    ap = argparse.ArgumentParser()

    # --- Unitree / DDS ---
    ap.add_argument("--iface", type=str, default="eth0", help="Network interface to Go2 DDS (default: eth0)")
    ap.add_argument("--state_topic", type=str, default="rt/sportmodestate", help="DDS topic for SportModeState_")

    # --- Logging / debugging ---
    ap.add_argument("--log_dir", type=str, default="./logs")
    ap.add_argument("--show", action="store_true", help="Show undistorted image with tag overlay (needs GUI)")

    # --- Camera pull thread ---
    ap.add_argument("--cam_fps", type=float, default=20.0, help="Camera GetImageSample pull rate")

    # --- Sport mode settings ---
    ap.add_argument("--speed_level", type=int, choices=[0, 1, 2], default=2)
    ap.add_argument("--avoid_control", type=str, choices=["off", "on", "keep"], default="off",
                    help="Obstacle avoid switch at startup (wall docking usually off)")

    # --- Tag selection (startup-only) ---
    ap.add_argument("--tag_family", type=str, default="tag36h11")
    ap.add_argument("--tag_id", type=int, default=0)
    ap.add_argument("--tag_size", type=float, default=0.18)

    # --- Goal ---
    ap.add_argument("--target_dist", type=float, default=1.0, help="Desired distance in front of the tag (m)")

    # --- Controller tuning ---
    ap.add_argument("--hz", type=float, default=30.0, help="Main control loop rate (Hz)")
    ap.add_argument("--k_dist", type=float, default=1.4)
    ap.add_argument("--k_lat", type=float, default=1.0)
    ap.add_argument("--k_yaw", type=float, default=1.6)

    ap.add_argument("--max_vx", type=float, default=0.55)
    ap.add_argument("--max_vy", type=float, default=0.30)
    ap.add_argument("--max_vyaw", type=float, default=0.6)

    ap.add_argument("--min_vyaw", type=float, default=0.13)
    ap.add_argument("--min_vx_cmd", type=float, default=0.20)
    ap.add_argument("--min_vy_cmd", type=float, default=0.13)

    ap.add_argument("--yaw_first_deg", type=float, default=15.0, help="Rotate in place if |yaw_err| exceeds this")
    ap.add_argument("--tol_dist", type=float, default=0.03)
    ap.add_argument("--tol_lat", type=float, default=0.03)
    ap.add_argument("--tol_yaw_deg", type=float, default=2.5)

    ap.add_argument("--min_cmd_dist_margin", type=float, default=0.0)
    ap.add_argument("--min_cmd_lat_margin", type=float, default=0.0)
    ap.add_argument("--lat_vx_assist", type=float, default=0.0,
                    help="Min vx applied as locomotion assist when lateral deadband fires (m/s)")

    # --- Fusion + dropout behavior ---
    ap.add_argument("--alpha_tag", type=float, default=0.25, help="EMA blend factor for T_odom_tag_est")
    ap.add_argument("--short_loss_s", type=float, default=0.7, help="Short dropout window (keep predicting)")
    ap.add_argument("--long_loss_s", type=float, default=2.5, help="After this -> SEARCH mode")

    ap.add_argument("--dropout_scale", type=float, default=0.4, help="Scale vx/vy during short losses")
    ap.add_argument("--dropout_yaw_scale", type=float, default=1.0, help="Scale vyaw during short losses")
    ap.add_argument("--search_vyaw", type=float, default=0.25, help="Yaw rate during SEARCH")

    ap.add_argument("--allow_backward", type=lambda x: x.lower() != "false", default=True,
                    help="Allow negative vx when too close (default: True). Pass --allow_backward false to disable.")
    ap.add_argument("--max_meas_yaw_jump_deg", type=float, default=70.0)
    ap.add_argument("--max_meas_dist_jump", type=float, default=0.35)

    # --- Stuck detection / recovery ---
    ap.add_argument("--stuck_warn_s", type=float, default=1.0)
    ap.add_argument("--stuck_cmd_min", type=float, default=0.05)
    ap.add_argument("--stuck_odom_step", type=float, default=0.002)
    ap.add_argument("--stuck_recover_s", type=float, default=1.5)
    ap.add_argument("--stuck_recover_vx", type=float, default=0.24)

    return ap.parse_args()


# =============================================================================
# Main program
# =============================================================================

def main():
    args = parse_args()

    # ----------------------------- logging / trace -----------------------------
    logger, _, csv_path = setup_logger_and_paths(args.log_dir)
    csv_f, csv_w = open_trace_csv(csv_path)

    # ----------------------------- camera calibration -----------------------------
    # These are your fisheye intrinsics calibrated at 1920x1080.
    # vision_pose.py will scale them if incoming frames are different size.
    K0 = np.array([
        [1248.95099, 0.0,        957.862066],
        [0.0,        1247.94633, 530.821641],
        [0.0,        0.0,        1.0       ]
    ], dtype=np.float64)
    D0 = np.array([-0.04634571, -0.21551315, 0.45541731, -0.37792435], dtype=np.float64)

    # Fixed extrinsic from robot base -> camera frame (your provided matrix).
    # Used to convert camera->tag pose into base->tag pose for control/fusion.
    T_base_cam = np.array([
        [ 0.0,  0.0,  1.0,  0.31 ],
        [-1.0,  0.0,  0.0,  0.0  ],
        [ 0.0, -1.0,  0.0,  0.055],
        [ 0.0,  0.0,  0.0,  1.0  ]
    ], dtype=np.float64)

    # ----------------------------- IO startup (DDS + clients + threads) -----------------------------
    # This does exactly what your original monolithic script did:
    #   - ChannelFactoryInitialize
    #   - SportClient, VideoClient, MotionSwitcherClient
    #   - mode = normal
    #   - StandUp + BalanceStand
    #   - start subscriber + camera thread
    io = Go2IO(args.iface, args.state_topic, args.cam_fps, logger)
    io.startup(speed_level=args.speed_level, avoid_control=args.avoid_control)

    # ----------------------------- stage objects -----------------------------
    # Stage 1: vision (undistort + apriltag + T_cam_tag)
    vision = VisionPoseEstimator(
        K0=K0, D0=D0, calib_wh=(1920, 1080),
        tag_family=args.tag_family, tag_id=args.tag_id, tag_size=args.tag_size
    )
    logger.info(f"AprilTag backend: {vision.backend_name()}")

    # Stage 2: fusion / filtering in odom frame
    fusion = TagFusionFilter(
        alpha_tag=args.alpha_tag,
        max_meas_yaw_jump_deg=args.max_meas_yaw_jump_deg,
        max_meas_dist_jump=args.max_meas_dist_jump
    )

    # Stage 3: controller (error -> vx/vy/vyaw)
    controller = DockingController(
        target_dist=args.target_dist,
        hz=args.hz,
        k_dist=args.k_dist, k_lat=args.k_lat, k_yaw=args.k_yaw,
        max_vx=args.max_vx, max_vy=args.max_vy, max_vyaw=args.max_vyaw,
        min_vyaw=args.min_vyaw, min_vx_cmd=args.min_vx_cmd, min_vy_cmd=args.min_vy_cmd,
        yaw_first_deg=args.yaw_first_deg,
        tol_dist=args.tol_dist, tol_lat=args.tol_lat, tol_yaw_deg=args.tol_yaw_deg,
        min_cmd_dist_margin=args.min_cmd_dist_margin,
        min_cmd_lat_margin=args.min_cmd_lat_margin,
        lat_vx_assist=args.lat_vx_assist,
        short_loss_s=args.short_loss_s, long_loss_s=args.long_loss_s,
        dropout_scale=args.dropout_scale, dropout_yaw_scale=args.dropout_yaw_scale,
        search_vyaw=args.search_vyaw, allow_backward=args.allow_backward,
        stuck_warn_s=args.stuck_warn_s, stuck_cmd_min=args.stuck_cmd_min,
        stuck_odom_step=args.stuck_odom_step, stuck_recover_s=args.stuck_recover_s,
        stuck_recover_vx=args.stuck_recover_vx
    )

    # ----------------------------- clean shutdown handler -----------------------------
    def shutdown_now(*_):
        """
        Ensures:
          - background camera thread stops
          - robot receives StopMove and returns to BalanceStand
          - CSV closes cleanly
          - OpenCV window closes
        """
        logger.info("Stopping...")
        io.shutdown()
        try:
            csv_f.flush()
            csv_f.close()
        except Exception:
            pass
        if args.show:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_now)

    # ----------------------------- control loop timing -----------------------------
    # We keep the same "t_next scheduling" pattern as your original code.
    hz = float(args.hz)
    dt = 1.0 / max(1e-6, hz)
    t_next = time.time()

    # Used to compute odom_step_xy each cycle for stuck detection
    prev_x, prev_y = None, None

    logger.info("Starting control loop...")

    try:
        while True:
            now = time.time()

            # rate limit
            if now < t_next:
                time.sleep(min(0.005, t_next - now))
                continue
            t_next = now + dt

            # (A) Read odom-like state
            od = io.get_odom()

            # Freshness gate: if odom stale/missing -> do not move
            if (not od.valid) or (now - od.t > 0.25):
                # If you want bit-for-bit same behavior as your old script,
                # replace this with io.sc.StopMove() (StopMove only).
                io.stop_and_stand()
                logger.warning("SportModeState stale or missing -> StopMove()")
                continue

            # Compute odom step size (for stuck detection in controller)
            odom_step_xy = 0.0
            if prev_x is not None and prev_y is not None:
                odom_step_xy = math.hypot(float(od.x) - float(prev_x), float(od.y) - float(prev_y))
            prev_x, prev_y = float(od.x), float(od.y)

            # Convert to transform T_odom_base (used by fusion)
            T_odom_base = io.odom_to_T_odom_base(od)

            # (B) Read latest camera frame
            img_bgr, img_t = io.get_frame()

            # (C) Vision stage: undistort + tag detection + pose
            tag_visible, T_base_tag_meas, dbg = False, None, None
            if img_bgr is not None and (now - img_t) < 0.5:
                obs, _ = vision.process(img_bgr, t_now=now, want_debug=bool(args.show))
                dbg = obs.debug_img

                if obs.visible and obs.T_cam_tag is not None:
                    tag_visible = True
                    # (D) Convert camera->tag into base->tag
                    T_base_tag_meas = T_base_cam @ obs.T_cam_tag

            # Optional debug view
            if args.show and dbg is not None:
                cv2.imshow("go2_front_undistorted", dbg)
                cv2.waitKey(1)

            # (E) Fusion/filter stage: update estimate + produce prediction
            fres = fusion.update(T_odom_base, tag_visible, T_base_tag_meas, now)

            # If we have never seen the tag yet, do not move
            if (not fres.has_estimate) or (fres.T_base_tag_pred is None):
                io.sc.StopMove()
                logger.info("No tag estimate yet -> StopMove()")
                continue

            loss_dt = fusion.loss_dt(now)

            # (F) Control stage: compute command from predicted pose
            out = controller.step(
                T_base_tag_pred=fres.T_base_tag_pred,
                tag_visible=fres.tag_visible_used,
                loss_dt=loss_dt,
                odom_step_xy=odom_step_xy,
                now=now
            )

            # (G) Apply command
            io.move(out.vx, out.vy, out.vyaw)

            # (H) Log trace: errors + command + visibility + loss time
            dist_along, lateral, yaw_err, e_dist, e_lat = compute_planar_errors_from_T_base_tag(
                fres.T_base_tag_pred, float(args.target_dist)
            )
            csv_w.writerow([
                now, od.x, od.y, od.yaw,
                1 if fres.tag_visible_used else 0,
                dist_along, lateral, yaw_err,
                e_dist, e_lat,
                out.vx, out.vy, out.vyaw,
                loss_dt
            ])
            csv_f.flush()

            # Human-friendly console line ~5 Hz
            if int(now * 5) != int((now - dt) * 5):
                rej = " rej=1" if fres.meas_rejected else ""
                rec = " rec=1" if out.recovering else ""
                logger.info(
                    f"vis={int(fres.tag_visible_used)} loss={loss_dt:.2f}s | "
                    f"dist={dist_along:.3f} (e={e_dist:+.3f}) lat={lateral:+.3f} yaw={math.degrees(yaw_err):+.1f}deg | "
                    f"cmd vx={out.vx:+.2f} vy={out.vy:+.2f} vyaw={out.vyaw:+.2f}{rej}{rec}"
                )

            # Optional extra line to clearly indicate SEARCH
            if out.mode == "SEARCH":
                logger.info(f"SEARCH: tag lost for {loss_dt:.2f}s -> vyaw={out.vyaw:.2f}")

            # Completion condition (controller decides)
            if out.done:
                logger.info("DONE: reached target pose. StopMove() and BalanceStand().")
                io.stop_and_stand()
                break

    finally:
        shutdown_now()


if __name__ == "__main__":
    main()