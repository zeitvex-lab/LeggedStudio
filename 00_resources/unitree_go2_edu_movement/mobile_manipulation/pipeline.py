#!/usr/bin/env python3
"""
pipeline.py
===========
Mobile manipulation pipeline: Unitree Go2 EDU+ + WidowX-250

Full sequence
-------------
  INIT            arm: open → home → sleep; robot: stand + balance
  DOCK_WALL_TAG   search wall AprilTag (ID 0), approach to COARSE_STOP_DIST
  APPROACH_OBJECT arm moves to observation pose; visual servo toward pink object
                  using arm camera; stop when estimated_dist ≤ GRASP_DIST_M
  GRASP           arm executes horizontal grasp on the upright pink object
  RETREAT         reverse straight back by RETREAT_DIST_M (1 m)
  DOCK_DEST_TAG   search destination AprilTag (ID 1), approach to DEST_STOP_DIST
  DONE            mission complete

Module reuse
------------
  go2_io.py       — robot I/O, odometry, dog-camera thread, SportClient
  vision_pose.py  — fisheye undistort + AprilTag → T_cam_tag
  pose_filter.py  — EMA fusion filter in odometry frame
  dock_control.py — proportional velocity controller from tag-pose errors
  camera_subsystem.py — arm camera background thread  (new)
  pink_detector.py    — HSV-based pink object detector  (new)
  arm_control.py      — WidowX-250 wrapper             (new)

Usage
-----
  python3 pipeline.py
  python3 pipeline.py --show         # show arm-camera debug window
  python3 pipeline.py --skip_arm     # skip all arm operations (navigation only)
  python3 pipeline.py --iface eth0
"""

import argparse
from collections import deque
import math
import signal
import sys
import time

import cv2
import numpy as np

from go2_io      import Go2IO, setup_logger_and_paths
from vision_pose import VisionPoseEstimator
from pose_filter import TagFusionFilter
from dock_control import DockingController

from camera_subsystem import ArmCameraThread
from pink_detector    import PinkObjectDetector
from arm_control      import ArmControl


# ==============================================================================
#  CONFIGURATION  — adjust these constants to tune the system
# ==============================================================================

# ── Network ────────────────────────────────────────────────────────────────
DDS_IFACE   = "eth0"
STATE_TOPIC = "rt/sportmodestate"

# ── Control loop rate ───────────────────────────────────────────────────────
CONTROL_HZ  = 30.0

# ── Dog camera (1920×1080 fisheye) ─────────────────────────────────────────
DOG_K = np.array([
    [1248.95099, 0.0,        957.862066],
    [0.0,        1247.94633, 530.821641],
    [0.0,        0.0,        1.0       ],
], dtype=np.float64)
DOG_D        = np.array([-0.04634571, -0.21551315, 0.45541731, -0.37792435],
                        dtype=np.float64)
DOG_CALIB_WH = (1920, 1080)
DOG_CAM_FPS  = 20.0

# ── Dog body → front camera extrinsic ──────────────────────────────────────
T_BASE_CAM = np.array([
    [ 0.0,  0.0,  1.0,  0.31 ],
    [-1.0,  0.0,  0.0,  0.0  ],
    [ 0.0, -1.0,  0.0,  0.055],
    [ 0.0,  0.0,  0.0,  1.0  ],
], dtype=np.float64)

# ── AprilTags ───────────────────────────────────────────────────────────────
WALL_TAG_FAMILY = "tag36h11"
WALL_TAG_ID     = 0
WALL_TAG_SIZE   = 0.180    # metres (physical side length)
DEST_TAG_ID     = 1
DEST_TAG_SIZE   = 0.180    # metres

# ── Docking distances ───────────────────────────────────────────────────────
# Stop the coarse approach here — arm camera must be able to see the object.
# Arm camera is set back from the dog camera, so needs to be closer than you
# might expect.  At 0.2 m the dog-camera tag may overflow the frame; the
# proximity fallback (COARSE_PROXIMITY_FALLBACK_M below) handles that case.
COARSE_STOP_DIST = 0.45    # metres from wall tag

# The EMA filter (alpha=0.25) lags behind a fast approach.  When the tag
# last disappears (camera overflow at close range) the filter typically
# reads 0.15–0.30 m ABOVE the physical distance.  This constant compensates:
#   fallback fires when  pred_dist <= COARSE_STOP_DIST + COARSE_FILTER_LAG_M
#                      = 0.30 + 0.35 = 0.65 m
# From logs: pred showed ~0.47–0.50 m when physically at the wall, so 0.65 m
# gives reliable clearance.
COARSE_FILTER_LAG_M = 0.35   # metres

# Stop at the destination tag here for the place operation.
DEST_STOP_DIST   = 1.00    # metres from destination tag

# ── Docking controller gains (shared by both approach phases) ───────────────
K_DIST          = 1.4
K_LAT           = 1.0
K_YAW           = 1.6
MAX_VX          = 0.55
MAX_VY          = 0.30
MAX_VYAW        = 0.60
MIN_VYAW        = 0.13
MIN_VX_CMD      = 0.20
MIN_VY_CMD      = 0.13
YAW_FIRST_DEG   = 15.0
TOL_DIST        = 0.03
TOL_LAT         = 0.03
TOL_YAW_DEG     = 2.5
ALPHA_TAG       = 0.25
SHORT_LOSS_S    = 0.7
LONG_LOSS_S     = 2.5
SEARCH_VYAW     = 0.25
DROPOUT_SCALE   = 0.4
STUCK_WARN_S    = 1.0
STUCK_ODOM_STEP = 0.002
STUCK_RECOVER_S = 1.5
STUCK_RECOVER_VX = 0.24

# ── Arm camera ──────────────────────────────────────────────────────────────
ARM_CAM_DEVICE = "/dev/video0"
ARM_CAM_W      = 1280
ARM_CAM_H      = 720

# Arm camera intrinsics at 1280×720 (from old_pipeline.py calibration)
ARM_K = np.array([
    [1020.78,    0.00,  569.61],
    [   0.00, 1027.20,  310.38],
    [   0.00,    0.00,    1.00],
], dtype=np.float64)
ARM_D = np.array([-0.216370, 0.076488, 0.000587, -0.000633, -0.024798],
                 dtype=np.float64)

# ── Visual servo (APPROACH_OBJECT state) ────────────────────────────────────
# The robot drives toward the pink object using arm-camera feedback.

# Expected object distance once the wall-tag docking is complete. Keep this as a
# tuning reference when reviewing logs or adjusting the coarse stop distance.
GRASP_DIST_M   = 0.30     # metres

# How many consecutive frames must confirm a stable, centred object pose before
# the robot stops and enters GRASP. Prevents false triggers from a noisy frame.
GRASP_CONFIRM_FRAMES = 5

# Timeout: warn if the object has not been seen for this long.
OBJ_LOST_TIMEOUT_S = 3.0

# Visual servo gains and speed limits
K_VIS_DIST   = 0.60    # gain: distance error → vx
K_VIS_YAW    = 0.80    # gain: horizontal offset → vyaw
MAX_VX_VIS   = 0.20    # m/s — slow during visual approach
MAX_VYAW_VIS = 0.40    # rad/s
MIN_VX_VIS   = 0.05    # minimum forward nudge when error is small but non-zero

# Recent object-pose window used to reject outliers and wait for a stable grasp.
OBJ_POSE_WINDOW       = 7
OBJ_POSE_MIN_SAMPLES  = 5
OBJ_POSE_MAX_JUMP_M   = 0.10
OBJ_POSE_STABLE_X_M   = 0.03
OBJ_POSE_STABLE_Y_M   = 0.02
OBJ_POSE_STABLE_Z_M   = 0.04
GRASP_MEASURE_TIMEOUT_S = 1.2

# Arm-only grasp gating during APPROACH_OBJECT.
ARM_GRASP_MIN_R_XY_M  = 0.15
ARM_GRASP_MAX_R_XY_M  = 0.75
ARM_GRASP_MAX_ABS_Y_M = 0.22
ARM_GRASP_MIN_Z_M     = -0.40

# ── Grasp ───────────────────────────────────────────────────────────────────
#
# The grasp target is computed from a filtered 3D centre estimate in the arm
# camera.  Depth comes from the known physical object height; X/Y come from the
# centroid ray.  This is more stable than bbox-based PnP for a 20.5 mm-wide
# object, whose apparent width jitters by several pixels frame to frame.
#
# GRASP_DEPTH_M: how far PAST the object face the IK target is placed.
# The arm slides into the object by this amount before closing the gripper.
# Combined with PRE_GRASP_RETRACT_M = 0.06 in arm_control.py:
#   pre-grasp position : face_X − (0.06 − 0.04) = face_X − 0.02  (2 cm in front)
#   grasp position     : face_X + 0.04  (4 cm inside the object)
#
GRASP_DEPTH_M = 0.04    # metres to penetrate past the object face

# Fallback fixed coordinates — used if a filtered object measurement is unavailable.
# GRASP_Z:
#   box height (0.53) + obj half-height (0.151) − arm base height (~0.40) ≈ 0.28
# Calibrate all three values for your physical setup.
GRASP_X_FALLBACK = 0.35
GRASP_Y_FALLBACK = 0.00
GRASP_Z_FALLBACK = 0.28

# ── Retreat ──────────────────────────────────────────────────────────────────
RETREAT_DIST_M = 0.3     # metres to reverse
RETREAT_VX     = 0.20    # speed (positive; negated when sent to robot)


# ==============================================================================
#  HELPERS
# ==============================================================================

def _make_vision(tag_id: int, tag_size: float) -> VisionPoseEstimator:
    return VisionPoseEstimator(
        K0=DOG_K, D0=DOG_D, calib_wh=DOG_CALIB_WH,
        tag_family=WALL_TAG_FAMILY,
        tag_id=tag_id,
        tag_size=tag_size,
    )


def _make_fusion() -> TagFusionFilter:
    return TagFusionFilter(
        alpha_tag=ALPHA_TAG,
        max_meas_yaw_jump_deg=70.0,
        max_meas_dist_jump=0.35,
    )


def _make_dock_ctrl(target_dist: float) -> DockingController:
    return DockingController(
        target_dist=target_dist,
        hz=CONTROL_HZ,
        k_dist=K_DIST,  k_lat=K_LAT,  k_yaw=K_YAW,
        max_vx=MAX_VX,  max_vy=MAX_VY, max_vyaw=MAX_VYAW,
        min_vyaw=MIN_VYAW, min_vx_cmd=MIN_VX_CMD, min_vy_cmd=MIN_VY_CMD,
        yaw_first_deg=YAW_FIRST_DEG,
        tol_dist=TOL_DIST, tol_lat=TOL_LAT, tol_yaw_deg=TOL_YAW_DEG,
        short_loss_s=SHORT_LOSS_S,  long_loss_s=LONG_LOSS_S,
        dropout_scale=DROPOUT_SCALE, dropout_yaw_scale=1.0,
        search_vyaw=SEARCH_VYAW,  allow_backward=True,
        stuck_warn_s=STUCK_WARN_S,   stuck_cmd_min=0.05,
        stuck_odom_step=STUCK_ODOM_STEP,
        stuck_recover_s=STUCK_RECOVER_S, stuck_recover_vx=STUCK_RECOVER_VX,
    )


class ObjectPoseWindow:
    """Rolling median filter for the object centre in the arm base frame."""

    def __init__(self, maxlen: int = OBJ_POSE_WINDOW):
        self._samples = deque(maxlen=maxlen)

    def clear(self) -> None:
        self._samples.clear()

    def count(self) -> int:
        return len(self._samples)

    def filtered(self):
        if not self._samples:
            return None
        arr = np.stack(tuple(self._samples), axis=0)
        return np.median(arr, axis=0)

    def spread(self):
        ref = self.filtered()
        if ref is None:
            return None
        arr = np.stack(tuple(self._samples), axis=0)
        return np.max(np.abs(arr - ref), axis=0)

    def stable(self, min_samples: int = OBJ_POSE_MIN_SAMPLES) -> bool:
        if len(self._samples) < min_samples:
            return False
        spread = self.spread()
        if spread is None:
            return False
        return bool(
            spread[0] <= OBJ_POSE_STABLE_X_M and
            spread[1] <= OBJ_POSE_STABLE_Y_M and
            spread[2] <= OBJ_POSE_STABLE_Z_M
        )

    def add(self, pos_arm) -> bool:
        """
        Add one pose sample unless it jumps too far from the running median.
        """
        pos = np.asarray(pos_arm, dtype=np.float64).reshape(3)
        ref = self.filtered()
        if ref is not None and float(np.linalg.norm(pos - ref)) > OBJ_POSE_MAX_JUMP_M:
            return False
        self._samples.append(pos)
        return True


def _estimate_object_pose_arm(frame_bgr, pink_det, arm, want_debug=False):
    """
    Detect the pink object and estimate its centre in camera and arm frames.
    """
    det = pink_det.detect(frame_bgr, want_debug=want_debug)
    pos_cam = pink_det.estimate_pos_cam(det) if det.detected else None
    pos_arm = None
    if pos_cam is not None and arm is not None:
        pos_arm = arm.cam_to_arm_frame(pos_cam)
    return det, pos_cam, pos_arm


def _measure_object_pose_pnp(arm_cam, pink_det, arm):
    """
    Collect a short burst of stationary PnP measurements and return the median pose.
    """
    window = ObjectPoseWindow()
    deadline = time.time() + GRASP_MEASURE_TIMEOUT_S
    last_frame_t = -1.0

    while time.time() < deadline:
        frame_bgr, frame_t = arm_cam.get_frame()
        now = time.time()
        if frame_bgr is None or frame_t <= 0.0 or (now - frame_t) > 0.5:
            time.sleep(0.02)
            continue
        if frame_t == last_frame_t:
            time.sleep(0.02)
            continue
        last_frame_t = frame_t

        det = pink_det.detect_pnp(frame_bgr, want_debug=False)
        pos_arm = None
        if det.detected and det.pnp_ok and det.pos_cam is not None and arm is not None:
            pos_arm = arm.cam_to_arm_frame(det.pos_cam)
            window.add(pos_arm)
            if window.stable():
                break

        time.sleep(0.02)

    return window.filtered(), window.count(), window.stable()


def _arm_pose_reachable(pos_arm) -> bool:
    """
    Conservative reachability gate for arm-only grasping.
    """
    if pos_arm is None:
        return False
    x, y, z = [float(v) for v in np.asarray(pos_arm, dtype=np.float64).reshape(3)]
    r_xy = math.hypot(x + GRASP_DEPTH_M, y)
    return bool(
        r_xy >= ARM_GRASP_MIN_R_XY_M and
        r_xy <= ARM_GRASP_MAX_R_XY_M and
        abs(y) <= ARM_GRASP_MAX_ABS_Y_M and
        z >= ARM_GRASP_MIN_Z_M
    )


def _dock_step(vision, fusion, ctrl, io, odom_step_xy, T_odom_base, now):
    """
    One control-loop iteration of the tag-approach pipeline.

    Detects the target tag in the dog camera, updates the fusion filter,
    and runs the docking controller.

    Returns (out, fres) where out is ControlOutput (or None if no estimate yet)
    and fres is FusionResult.
    """
    img_bgr, img_t = io.get_frame()
    tag_visible     = False
    T_base_tag_meas = None

    if img_bgr is not None and (now - img_t) < 0.5:
        obs, _ = vision.process(img_bgr, t_now=now, want_debug=False)
        if obs.visible and obs.T_cam_tag is not None:
            tag_visible     = True
            T_base_tag_meas = T_BASE_CAM @ obs.T_cam_tag

    fres = fusion.update(T_odom_base, tag_visible, T_base_tag_meas, now)

    if not fres.has_estimate or fres.T_base_tag_pred is None:
        io.sc.StopMove()
        return None, fres

    loss_dt = fusion.loss_dt(now)
    out = ctrl.step(
        T_base_tag_pred=fres.T_base_tag_pred,
        tag_visible=fres.tag_visible_used,
        loss_dt=loss_dt,
        odom_step_xy=odom_step_xy,
        now=now,
    )
    return out, fres


# ==============================================================================
#  ENTRY POINT
# ==============================================================================

def parse_args():
    ap = argparse.ArgumentParser(description="Go2 + wx250 mobile manipulation pipeline")
    ap.add_argument("--iface",    default=DDS_IFACE,
                    help="Network interface for DDS (default: eth0)")
    ap.add_argument("--show",     action="store_true",
                    help="Show arm-camera debug window")
    ap.add_argument("--skip_arm", action="store_true",
                    help="Skip all arm operations (navigation + vision only)")
    ap.add_argument("--log_dir",  default="./logs_pipeline")
    return ap.parse_args()


def main():
    args   = parse_args()
    logger, _, _ = setup_logger_and_paths(args.log_dir)

    # ── Robot I/O ──────────────────────────────────────────────────────────
    io = Go2IO(args.iface, STATE_TOPIC, DOG_CAM_FPS, logger)
    io.startup(speed_level=2, avoid_control="off")

    # ── Arm camera (always running; frames used only during APPROACH_OBJECT) ─
    arm_cam = ArmCameraThread(
        device=ARM_CAM_DEVICE, width=ARM_CAM_W, height=ARM_CAM_H, fps=30
    )
    arm_cam.start()

    # ── Pink object detector ────────────────────────────────────────────────
    pink_det = PinkObjectDetector(
        K=ARM_K, D=ARM_D,
        img_w=ARM_CAM_W, img_h=ARM_CAM_H,
    )

    # ── Arm (optional) ──────────────────────────────────────────────────────
    arm = None
    if not args.skip_arm:
        arm = ArmControl()

    # ── Shutdown handler ────────────────────────────────────────────────────
    def shutdown_now(*_):
        logger.info("Shutdown requested.")
        arm_cam.stop()
        io.shutdown()
        if args.show:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_now)

    # ── Loop timing ─────────────────────────────────────────────────────────
    dt     = 1.0 / CONTROL_HZ
    t_next = time.time()

    # ── Odometry step tracking (for stuck detection) ────────────────────────
    prev_x, prev_y = None, None

    # ── Tag approach objects — created fresh per phase ──────────────────────
    wall_vision = _make_vision(WALL_TAG_ID,  WALL_TAG_SIZE)
    wall_fusion = _make_fusion()
    wall_ctrl   = _make_dock_ctrl(COARSE_STOP_DIST)

    dest_vision = None
    dest_fusion = None
    dest_ctrl   = None

    # ── Visual approach state ────────────────────────────────────────────────
    grasp_confirm_count = 0
    obj_last_seen_t     = time.time()
    obj_pose_window     = ObjectPoseWindow()
    obj_pose_arm        = None

    # ── Retreat state ────────────────────────────────────────────────────────
    retreat_start_x: float = 0.0
    retreat_start_y: float = 0.0

    # ── State machine ────────────────────────────────────────────────────────
    state = "INIT"
    logger.info("Pipeline starting.")

    try:
        while True:
            now = time.time()

            # Rate limit
            if now < t_next:
                time.sleep(min(0.005, t_next - now))
                continue
            t_next = now + dt

            # Read odometry
            od = io.get_odom()
            if (not od.valid) or (now - od.t > 0.25):
                io.stop_and_stand()
                logger.warning("Odom stale → StopMove")
                continue

            odom_step_xy = 0.0
            if prev_x is not None and prev_y is not None:
                odom_step_xy = math.hypot(
                    float(od.x) - prev_x, float(od.y) - prev_y
                )
            prev_x, prev_y = float(od.x), float(od.y)

            T_odom_base = io.odom_to_T_odom_base(od)

            # ==================================================================
            #  INIT
            # ==================================================================
            if state == "INIT":
                logger.info("── INIT: arm initialisation ──")
                if arm is not None:
                    arm.open_gripper()
                    arm.go_home()
                    arm.go_sleep()
                    logger.info("Arm ready: sleep pose, gripper open.")
                state = "DOCK_WALL_TAG"
                logger.info("State → DOCK_WALL_TAG  (searching for tag ID %d)", WALL_TAG_ID)
                continue

            # ==================================================================
            #  DOCK_WALL_TAG  — search + approach to COARSE_STOP_DIST
            # ==================================================================
            elif state == "DOCK_WALL_TAG":
                out, fres = _dock_step(
                    wall_vision, wall_fusion, wall_ctrl,
                    io, odom_step_xy, T_odom_base, now,
                )
                if out is None:
                    continue   # no estimate yet, robot already stopped

                loss_dt  = wall_fusion.loss_dt(now)
                pred_dist = float(
                    np.linalg.norm(fres.T_base_tag_pred[:2, 3])
                ) if fres.T_base_tag_pred is not None else 999.0

                # Arrival check — two ways to declare "close enough":
                #  1. Normal done:  controller satisfied all tolerances with a
                #     fresh tag measurement.
                #  2. Filter-lag fallback:  tag has been gone ≥ 0.3 s AND the
                #     filter (despite its lag) already reads ≤ 0.65 m.
                #     Removes the loss_dt < LONG_LOSS_S gate so it works even
                #     after SEARCH mode has started spinning.
                wall_arrived = out.done

                if not wall_arrived and fres.T_base_tag_pred is not None:
                    fallback_dist = COARSE_STOP_DIST + COARSE_FILTER_LAG_M  # 0.65 m
                    if loss_dt > 0.3 and pred_dist <= fallback_dist:
                        logger.info(
                            "Filter-lag fallback: tag lost %.1f s, "
                            "pred_dist=%.2f m (threshold %.2f m) → proceeding.",
                            loss_dt, pred_dist, fallback_dist,
                        )
                        wall_arrived = True

                if not wall_arrived:
                    io.move(out.vx, out.vy, out.vyaw)

                # Log at ~5 Hz
                if int(now * 5) != int((now - dt) * 5):
                    logger.info(
                        "DOCK_WALL_TAG [%s] vis=%d loss=%.2fs pred=%.2fm "
                        "vx=%+.2f vy=%+.2f vyaw=%+.2f",
                        out.mode, int(fres.tag_visible_used), loss_dt, pred_dist,
                        out.vx, out.vy, out.vyaw,
                    )

                if wall_arrived:
                    io.stop_and_stand()
                    logger.info(
                        "Wall tag reached (~%.2f m).  Moving arm to observation pose.",
                        COARSE_STOP_DIST,
                    )
                    if arm is not None:
                        arm.go_observation()   # blocking
                    obj_last_seen_t     = time.time()
                    grasp_confirm_count = 0
                    obj_pose_window.clear()
                    obj_pose_arm = None
                    state = "APPROACH_OBJECT"
                    logger.info("State → APPROACH_OBJECT")

            # ==================================================================
            #  APPROACH_OBJECT  — base stationary, filter object pose then GRASP
            #
            #  The dog base stays still here. We only estimate the object's 3-D
            #  centre in the arm base frame and wait until that pose is stable
            #  and inside a conservative arm-reach window before grasping.
            # ==================================================================
            elif state == "APPROACH_OBJECT":
                arm_frame, arm_t = arm_cam.get_frame()

                if arm_frame is None or (now - arm_t) > 0.5:
                    io.sc.StopMove()
                    continue

                det, pos_cam, pos_arm_raw = _estimate_object_pose_arm(
                    arm_frame, pink_det, arm, want_debug=args.show
                )

                if args.show and det.debug_img is not None:
                    cv2.imshow("arm_cam_pink", det.debug_img)
                    cv2.waitKey(1)

                if det.detected:
                    obj_last_seen_t = now

                    pose_sample_used = False
                    if pos_arm_raw is not None:
                        pose_sample_used = obj_pose_window.add(pos_arm_raw)
                        if not pose_sample_used:
                            logger.warning(
                                "APPROACH_OBJECT: rejected object-pose outlier "
                                "raw=(%+.3f, %+.3f, %+.3f)",
                                pos_arm_raw[0], pos_arm_raw[1], pos_arm_raw[2],
                            )

                    filt_pose = obj_pose_window.filtered()
                    if filt_pose is not None:
                        obj_pose_arm = filt_pose.copy()
                    pose_spread = obj_pose_window.spread()
                    pose_stable = obj_pose_window.stable()
                    pose_reachable = _arm_pose_reachable(obj_pose_arm)

                    # ── Debug print every frame (window is only ~0.17 s) ─────
                    logger.info(
                        "APPROACH_OBJECT frame: d=%.3fm dx=%+.3f samples=%d "
                        "stable=%d reachable=%d confirm=%d/%d",
                        det.estimated_dist_m, det.dx_norm,
                        obj_pose_window.count(), int(pose_stable), int(pose_reachable),
                        grasp_confirm_count, GRASP_CONFIRM_FRAMES,
                    )
                    if pos_cam is not None:
                        logger.info(
                            "  pos_cam (cam frame) : X=%+.4f  Y=%+.4f  Z=%+.4f",
                            pos_cam[0], pos_cam[1], pos_cam[2],
                        )
                    if pos_arm_raw is not None:
                        logger.info(
                            "  pos_arm_raw         : X=%+.4f  Y=%+.4f  Z=%+.4f"
                            "  (X=reach, Y=lateral, Z=height)",
                            pos_arm_raw[0], pos_arm_raw[1], pos_arm_raw[2],
                        )
                    if obj_pose_arm is not None:
                        logger.info(
                            "  pos_arm_filt        : X=%+.4f  Y=%+.4f  Z=%+.4f"
                            "  (X=reach, Y=lateral, Z=height)",
                            obj_pose_arm[0], obj_pose_arm[1], obj_pose_arm[2],
                        )
                    if pose_spread is not None:
                        logger.info(
                            "  pose spread         : dX=%.3f  dY=%.3f  dZ=%.3f",
                            pose_spread[0], pose_spread[1], pose_spread[2],
                        )
                    io.sc.StopMove()

                    ready_for_grasp = bool(
                        pose_sample_used and
                        obj_pose_arm is not None and
                        pose_stable and
                        pose_reachable
                    )
                    if ready_for_grasp:
                        grasp_confirm_count += 1
                    else:
                        grasp_confirm_count = 0

                    if grasp_confirm_count >= GRASP_CONFIRM_FRAMES:
                        io.stop_and_stand()
                        logger.info(
                            "Object confirmed (%d frames) → GRASP  "
                            "pos_arm=%s",
                            GRASP_CONFIRM_FRAMES,
                            (f"X={obj_pose_arm[0]:+.3f} Y={obj_pose_arm[1]:+.3f} "
                             f"Z={obj_pose_arm[2]:+.3f}"
                             if obj_pose_arm is not None else "n/a"),
                        )
                        state = "GRASP"
                else:
                    # Pink object not visible — hold still, reset confirm counter
                    grasp_confirm_count = 0
                    obj_pose_window.clear()
                    io.sc.StopMove()
                    lost_for = now - obj_last_seen_t
                    if lost_for > OBJ_LOST_TIMEOUT_S:
                        if int(now * 1) != int((now - dt) * 1):
                            logger.warning(
                                "APPROACH_OBJECT: pink object not seen for %.1f s",
                                lost_for,
                            )

            # ==================================================================
            #  GRASP
            # ==================================================================
            elif state == "GRASP":
                if arm is not None:
                    grasp_x, grasp_y, grasp_z = (
                        GRASP_X_FALLBACK, GRASP_Y_FALLBACK, GRASP_Z_FALLBACK
                    )
                    measured_pose_arm, sample_count, pose_stable = _measure_object_pose_pnp(
                        arm_cam, pink_det, arm
                    )

                    if measured_pose_arm is not None and sample_count >= OBJ_POSE_MIN_SAMPLES:
                        logger.info(
                            "GRASP PnP burst: samples=%d stable=%d "
                            "pose=(X=%+.4f Y=%+.4f Z=%+.4f)",
                            sample_count, int(pose_stable),
                            measured_pose_arm[0], measured_pose_arm[1], measured_pose_arm[2],
                        )
                        grasp_x = float(measured_pose_arm[0]) + GRASP_DEPTH_M
                        grasp_y = float(measured_pose_arm[1])
                        grasp_z = float(measured_pose_arm[2])
                    elif measured_pose_arm is not None:
                        logger.warning(
                            "GRASP PnP burst collected only %d sample(s); "
                            "using fixed fallback grasp instead.",
                            sample_count,
                        )
                    else:
                        logger.warning(
                            "GRASP PnP burst unavailable — using fallback "
                            "grasp coords (x=%.3f y=%.3f z=%.3f)",
                            grasp_x, grasp_y, grasp_z,
                        )

                    logger.info(
                        "  grasp target (arm frame): x=%+.4f  y=%+.4f  z=%+.4f",
                        grasp_x, grasp_y, grasp_z,
                    )

                    ok = arm.grasp_upright(grasp_x, grasp_y, grasp_z)
                    if ok:
                        logger.info("Grasp succeeded.")
                    else:
                        logger.warning("Grasp FAILED — retreating anyway.")
                else:
                    logger.info("GRASP skipped (--skip_arm).")

                retreat_start_x = float(od.x)
                retreat_start_y = float(od.y)
                state = "RETREAT"
                logger.info(
                    "State → RETREAT  (target: %.1f m back)", RETREAT_DIST_M
                )

            # ==================================================================
            #  RETREAT  — reverse straight back by RETREAT_DIST_M
            # ==================================================================
            elif state == "RETREAT":
                dist_traveled = math.hypot(
                    float(od.x) - retreat_start_x,
                    float(od.y) - retreat_start_y,
                )

                if dist_traveled >= RETREAT_DIST_M:
                    io.stop_and_stand()
                    logger.info(
                        "Retreat complete (%.2f m).  Building dest-tag approach.",
                        dist_traveled,
                    )
                    dest_vision = _make_vision(DEST_TAG_ID, DEST_TAG_SIZE)
                    dest_fusion = _make_fusion()
                    dest_ctrl   = _make_dock_ctrl(DEST_STOP_DIST)
                    state = "DOCK_DEST_TAG"
                    logger.info(
                        "State → DOCK_DEST_TAG  (searching for tag ID %d)", DEST_TAG_ID
                    )
                else:
                    io.move(-RETREAT_VX, 0.0, 0.0)
                    if int(now * 2) != int((now - dt) * 2):
                        logger.info(
                            "RETREAT: %.2f / %.2f m",
                            dist_traveled, RETREAT_DIST_M,
                        )

            # ==================================================================
            #  DOCK_DEST_TAG  — search + approach to DEST_STOP_DIST
            # ==================================================================
            elif state == "DOCK_DEST_TAG":
                out, fres = _dock_step(
                    dest_vision, dest_fusion, dest_ctrl,
                    io, odom_step_xy, T_odom_base, now,
                )
                if out is None:
                    continue

                io.move(out.vx, out.vy, out.vyaw)

                if int(now * 5) != int((now - dt) * 5):
                    loss_dt = dest_fusion.loss_dt(now)
                    logger.info(
                        "DOCK_DEST_TAG [%s] vis=%d loss=%.2fs "
                        "vx=%+.2f vy=%+.2f vyaw=%+.2f",
                        out.mode, int(fres.tag_visible_used), loss_dt,
                        out.vx, out.vy, out.vyaw,
                    )

                if out.done:
                    io.stop_and_stand()
                    logger.info("Destination tag reached. State → DONE")
                    state = "DONE"

            # ==================================================================
            #  DONE
            # ==================================================================
            elif state == "DONE":
                logger.info("Mission complete.")
                break

    finally:
        shutdown_now()


if __name__ == "__main__":
    main()
