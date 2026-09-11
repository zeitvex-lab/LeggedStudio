#!/usr/bin/env python3
"""
main_state_machine.py
=====================
Central brain of the autonomous mobile manipulation pipeline.

State transitions
-----------------
  SEARCH  →  APPROACH  →  ARM_SEARCH  →  GRASP  →  DONE

SEARCH
    Burst-scan: rotate → settle → observe (fresh stopped frames).
    Transitions to APPROACH on the first confirmed detection.

APPROACH
    Dog-camera YOLO via async detector.  base_ctrl drives the robot
    toward the ball at 15 Hz with EMA smoothing.
    → GRASP  when base_ctrl.is_arrived() (≤ 10 cm)
    → ARM_SEARCH  when ball is lost close to the robot

ARM_SEARCH
    Arm moves to POSITION_2 (camera-viewing pose), gripper opens.
    Per-frame arm-camera YOLO drives the base directly (yaw then fwd)
    until the ball is ≤ ARM_STOP_DIST_M in arm-base-frame forward.

GRASP
    Stop → balance stand → pitch body forward → confirm ball with arm
    camera → grasp_after_pitch() → un-pitch → DONE.

Parallelism
-----------
  go2_io           dog-camera background thread + network comms
  camera_streamer  arm-camera background thread
  dog_detector     dog-camera YOLO background thread
  base_controller  15 Hz motor loop + pitch ramp thread
  main loop (here) state machine + arm-camera YOLO + debug streaming
"""

import os
import sys
import signal
import time
import logging
import queue
import threading

import cv2
import numpy as np

# go2_io lives one level up in mobile_manipulation/
_HERE   = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.append(_PARENT)

from go2_io             import Go2IO, setup_logger_and_paths
from camera_streamer    import LiveCameraStreamer
from dog_detection_worker import AsyncDogDetector
from vision_core        import VisionCore, TargetCoordinates, set_ball_color
from base_controller    import BaseController, APPROACH_STOP_DIST_M
from arm_controller     import ArmController


# ── Tuneable parameters ───────────────────────────────────────────────────────

# ARM_SEARCH
ARM_VX              = 0.25       # forward speed (m/s)
ARM_STOP_DIST_M     = 0.66       # halt at this arm-base-frame forward distance
ARM_YAW_KP          = 1.8        # P-gain (rad/s per metre lateral error)
ARM_YAW_MAX         = 0.35       # max yaw (rad/s)
ARM_MIN_VYAW        = 0.10       # minimum yaw for arm-camera phase
ARM_YAW_TOLERANCE_M = 0.12       # lateral tolerance before switching to fwd

# APPROACH → ARM_SEARCH handoff
ARM_SEARCH_TRIGGER_DIST_M = 0.35  # only trigger if ball was last seen this close
ARM_SEARCH_LOSS_TIMEOUT_S = 0.70  # seconds ball must be gone before trigger

# GRASP
GRASP_CONFIRM_FRAMES   = 3
GRASP_HOVER_Z_M        = 0.07
GRASP_Z_CORRECTION_M   = 0.02    # tune manually: positive shifts grasp point up


# ── Debug overlay ─────────────────────────────────────────────────────────────

def _overlay_state(frame: np.ndarray, state: str) -> None:
    h = frame.shape[0]
    cv2.putText(frame, f"STATE: {state}",
                (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (255, 255, 255), 2, cv2.LINE_AA)


# ── Background display thread (keeps X11/waitKey off the main loop) ───────────

_display_q    = queue.Queue(maxsize=1)  # drop-oldest: never blocks main loop
_display_quit = threading.Event()

def _display_thread() -> None:
    """Render frames on a background thread so X11 never blocks the main loop."""
    cv2.namedWindow("Go2 Vision", cv2.WINDOW_NORMAL)
    while not _display_quit.is_set():
        try:
            frame = _display_q.get(timeout=0.3)
        except queue.Empty:
            cv2.waitKey(1)
            continue
        cv2.imshow("Go2 Vision", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            _display_quit.set()
    cv2.destroyAllWindows()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log_dir = "./logs_auto_yolo_v2"
    logger, _, _ = setup_logger_and_paths(log_dir)

    # Propagate ALL module loggers (vision_core, dog_detection_worker, etc.)
    # to the same file/console handlers by attaching them to the root logger.
    root_log = logging.getLogger()
    root_log.handlers = list(logger.handlers)
    root_log.setLevel(logging.DEBUG)
    logger.propagate = False   # avoid double-printing on the named logger

    logger.info("=== auto_yolo_v2 starting ===")

    # Start the background display thread (decouples X11 from the main loop)
    _disp_thread = threading.Thread(target=_display_thread, daemon=True, name="display")
    _disp_thread.start()

    # ── Subsystem init ────────────────────────────────────────────────────────
    io       = Go2IO("eth0", "rt/sportmodestate", 20.0, logger)
    io.startup(speed_level=2, avoid_control="off")

    yolo_model = os.getenv("GO2_YOLO_MODEL", "yolo11n.pt")

    streamer     = LiveCameraStreamer(dog_frame_provider=io.get_frame)
    vision       = VisionCore(yolo_model_path=yolo_model)
    dog_detector = AsyncDogDetector(vision.process_dog_frame)
    arm          = ArmController()
    base_ctrl    = BaseController(
        move_cmd_callback=io.move,
        euler_cmd_callback=io.euler,
    )
    # Enable DEBUG so [LAG] lines appear in the log file
    logger.setLevel(logging.DEBUG)
    logging.getLogger("dog_detection_worker").setLevel(logging.DEBUG)
    logging.getLogger("base_controller").setLevel(logging.DEBUG)

    logger.info(f"YOLO model: {yolo_model}")
    dog_detector.start()
    base_ctrl.start()

    def _shutdown(*_):
        logger.info("Shutting down…")
        _display_quit.set()
        dog_detector.stop()
        base_ctrl.stop()
        streamer.stop()
        io.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)

    # ── Arm init ──────────────────────────────────────────────────────────────
    logger.info("Arm: home → open gripper → sleep")
    arm.go_home()
    arm.open_gripper()
    arm.go_sleep()
    logger.info("Arm stowed — starting state machine")

    # ── State machine ─────────────────────────────────────────────────────────
    state                = "APPROACH"
    arm_search_init_done = False

    # APPROACH tracking
    last_seen_dist      = 999.0
    last_seen_time      = 0.0
    approach_loss_count = 0
    approach_last_det   = False
    approach_log_t      = time.time()

    base_ctrl.set_mode("approach")
    logger.info("State machine started → APPROACH")

    try:
        while state != "DONE":
            debug_frame = None
            dog_result_ts = 0.0
            target_data   = TargetCoordinates(detected=False)

            # ── 1. Grab frame and run vision ──────────────────────────────────
            if state == "ARM_SEARCH":
                frame, _ = streamer.get_arm_frame()
                if frame is None:
                    io.move(0.0, 0.0, 0.0)
                    time.sleep(0.01)
                    continue
                target_data, debug_frame, p_cam = vision.process_arm_frame(frame)

            else:
                frame, _ = streamer.get_dog_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue

                # Submit every new frame to the background YOLO thread
                submit_t = time.time()
                dog_detector.submit(frame, submit_t)

                # Read the latest completed YOLO result
                _, dog_result, dog_debug, dog_done_t = dog_detector.get_latest()

                # Staleness gate: discard results older than 120ms.
                # With a single-tile 60ms YOLO cycle, valid results arrive within
                # ~80ms. Anything older means the robot has already moved/rotated
                # too much for that detection to be trustworthy — treat as no ball.
                RESULT_MAX_AGE_S = 0.200
                result_age_ms = 0.0
                if dog_done_t > 0.0:
                    result_age_ms = (time.time() - dog_done_t) * 1000.0
                    if result_age_ms > RESULT_MAX_AGE_S * 1000.0:
                        target_data = TargetCoordinates(detected=False)
                    else:
                        target_data = dog_result
                else:
                    target_data = dog_result

                debug_frame = dog_debug.copy() if dog_debug is not None else frame.copy()

                logger.debug(
                    f"[LAG] result_age={result_age_ms:.0f}ms  "
                    f"detected={target_data.detected}  dist={target_data.dist_m:.2f}m"
                )

                if state == "APPROACH":
                    base_ctrl.update_target(
                        detected=target_data.detected,
                        dist_m=target_data.dist_m,
                        dx_norm=target_data.dx_norm,
                    )

            # ── 2. State transitions ──────────────────────────────────────────
            if state == "APPROACH":
                now = time.time()

                if target_data.detected:
                    last_seen_dist = target_data.dist_m
                    last_seen_time = now

                if approach_last_det and not target_data.detected:
                    approach_loss_count += 1
                    logger.info(
                        f"APPROACH: lost #{approach_loss_count}  "
                        f"last_dist={last_seen_dist:.2f}m  "
                        f"arm_trigger={'YES' if last_seen_dist < ARM_SEARCH_TRIGGER_DIST_M else 'NO'}"
                    )
                elif not approach_last_det and target_data.detected:
                    logger.info(
                        f"APPROACH: recovered  dist={target_data.dist_m:.2f}m  "
                        f"losses={approach_loss_count}"
                    )
                approach_last_det = target_data.detected

                if now - approach_log_t >= 2.0:
                    logger.info(
                        f"APPROACH: dist={last_seen_dist:.2f}m  "
                        f"detected={target_data.detected}  losses={approach_loss_count}"
                    )
                    approach_log_t = now

                if base_ctrl.is_arrived():
                    logger.info("APPROACH: arrived (≤10 cm) → GRASP")
                    base_ctrl.set_mode("idle")
                    base_ctrl.stop()
                    state = "GRASP"

                elif (not target_data.detected
                      and last_seen_dist < ARM_SEARCH_TRIGGER_DIST_M
                      and now - last_seen_time > ARM_SEARCH_LOSS_TIMEOUT_S):
                    base_ctrl.set_mode("idle")
                    base_ctrl.stop()
                    if last_seen_dist <= APPROACH_STOP_DIST_M:
                        # Already within stop distance — ball dropped out of ROI
                        # at close range. Skip ARM_SEARCH, go straight to GRASP.
                        logger.info(
                            f"APPROACH: ball lost at {last_seen_dist:.2f} m "
                            f"(≤ stop dist {APPROACH_STOP_DIST_M:.2f} m) → GRASP directly"
                        )
                        state = "GRASP"
                    else:
                        logger.info(
                            f"APPROACH: ball lost at {last_seen_dist:.2f} m → ARM_SEARCH"
                        )
                        arm_search_init_done = False
                        state = "ARM_SEARCH"

            elif state == "ARM_SEARCH":
                # One-time arm init
                if not arm_search_init_done:
                    logger.info("ARM_SEARCH: home → position_2 → open gripper")
                    arm.go_home()
                    arm.go_position_2()
                    arm.open_gripper()
                    arm_search_init_done = True
                    logger.info("ARM_SEARCH: ready — per-frame direct control")

                if not target_data.detected or p_cam is None:
                    io.move(0.0, 0.0, 0.0)
                else:
                    p_base  = arm.ball_cam_to_base(p_cam)
                    fwd_err = float(p_base[0])
                    lat_err = float(p_base[1])
                    logger.debug(f"ARM_SEARCH: fwd={fwd_err:.3f}m  lat={lat_err:.3f}m")

                    if fwd_err <= ARM_STOP_DIST_M:
                        io.move(0.0, 0.0, 0.0)
                        logger.info(f"ARM_SEARCH: arrived fwd={fwd_err:.3f}m → GRASP")
                        state = "GRASP"
                    elif abs(lat_err) > ARM_YAW_TOLERANCE_M:
                        vyaw = float(np.clip(ARM_YAW_KP * lat_err, -ARM_YAW_MAX, ARM_YAW_MAX))
                        if 1e-6 < abs(vyaw) < ARM_MIN_VYAW:
                            vyaw = ARM_MIN_VYAW if vyaw > 0 else -ARM_MIN_VYAW
                        io.move(0.0, 0.0, vyaw)
                    else:
                        io.move(ARM_VX, 0.0, 0.0)

            elif state == "GRASP":
                io.move(0.0, 0.0, 0.0)
                io.balance_stand()
                time.sleep(0.3)
                logger.info("GRASP: moving arm to observation pose")
                arm.go_position_2()
                arm.open_gripper()
                logger.info("GRASP: confirming ball with arm camera")

                # Confirm ball with consecutive arm-camera detections
                grasp_p_cam = None
                confirm     = 0
                for attempt in range(80):     # ~8 s at ~10 fps
                    fresh_frame, _ = streamer.get_arm_frame()
                    if fresh_frame is None:
                        time.sleep(0.05)
                        continue
                    td, arm_debug, p_fresh = vision.process_arm_frame(fresh_frame)
                    _overlay_state(arm_debug, "GRASP")
                    try:
                        _display_q.put_nowait(arm_debug)
                    except queue.Full:
                        pass
                    if td.detected and p_fresh is not None:
                        confirm += 1
                        logger.info(
                            f"GRASP: confirm {confirm}/{GRASP_CONFIRM_FRAMES} (attempt {attempt+1})"
                        )
                        if confirm >= GRASP_CONFIRM_FRAMES:
                            grasp_p_cam = p_fresh
                            break
                    else:
                        confirm = 0
                    time.sleep(0.05)

                # Wrist scan fallback
                if grasp_p_cam is None:
                    logger.info("GRASP: not confirmed — scanning wrist")
                    grasp_p_cam = arm.scan_wrist(vision, streamer)

                if grasp_p_cam is None:
                    logger.error("GRASP: no ball found — aborting")
                else:
                    grasp_p = arm.ball_cam_to_base(grasp_p_cam)
                    gx = float(grasp_p[0])
                    gy = float(grasp_p[1])
                    gz = float(grasp_p[2]) + GRASP_Z_CORRECTION_M
                    logger.info(
                        f"GRASP: target fwd={gx:.3f}  lat={gy:.3f}  "
                        f"z={gz:.3f} (corr={GRASP_Z_CORRECTION_M:+.3f})"
                    )
                    success = arm.grasp_flat(gx, gy, gz, hover_z_offset=GRASP_HOVER_Z_M)
                    logger.info(f"GRASP: {'success' if success else 'FAILED'}")

                state = "DONE"

            # ── 3. Visualize (non-blocking — display thread handles X11) ─────────
            if _display_quit.is_set():
                logger.info("User quit via 'q'")
                break
            if debug_frame is not None:
                _overlay_state(debug_frame, state)
                try:
                    _display_q.put_nowait(debug_frame)
                except queue.Full:
                    pass   # display thread is behind — drop frame, never block

    finally:
        _shutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous ball approach and grasp")
    parser.add_argument(
        "--ball-color", choices=["red", "green"], default="red",
        help="Ball color to track (default: red)"
    )
    args = parser.parse_args()
    set_ball_color(args.ball_color)
    main()
