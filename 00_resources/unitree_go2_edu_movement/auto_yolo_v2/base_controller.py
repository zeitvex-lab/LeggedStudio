#!/usr/bin/env python3
"""
base_controller.py
==================
Runs motor commands in its own thread at a strict 15 Hz, completely
decoupled from YOLO latency.  Applies EMA smoothing to reduce jitter,
has a detection debounce so single-frame YOLO drops don't interrupt
approach, and has a blind-follow mode so the robot doesn't spin when
the ball briefly disappears near the goal (occluded by the robot body).

Also owns the body-pitch ramp thread so all locomotion/body control
lives here rather than in the state machine.

Modes (set via set_mode())
--------------------------
  idle           — send zero velocity
  search_rotate  — rotate in place at search_vyaw rad/s
  search_hold    — hold still (same as idle but explicit)
  approach       — P-controller toward ball using update_target() data
"""

import math
import threading
import time
from typing import Callable, Optional


# ── Control rate ──────────────────────────────────────────────────────────────
CONTROL_HZ = 15.0

# ── Approach P-controller ─────────────────────────────────────────────────────
APPROACH_STOP_DIST_M = 0.45
APPROACH_VX_CONST    = 0.45
K_APPROACH_YAW       = 0.8
MAX_VYAW             = 0.30
MIN_VYAW             = 0.06
ARRIVAL_YAW_NORM     = 0.04
YAW_DEADBAND_NORM    = 0.015
DX_BIAS              = 0.04    # tune to fix systematic left/right offset at stop
                               # negative = shift reference left (ball drifts right → use negative)

# ── Search ────────────────────────────────────────────────────────────────────
SEARCH_VYAW = 0.4

# ── EMA smoothing (alpha=1 → no smoothing) ────────────────────────────────────
DX_ALPHA   = 0.35
DIST_ALPHA = 0.35

# ── Detection debounce ────────────────────────────────────────────────────────
# Distance-adaptive coast window.  At 15 Hz: 10→667ms, 2→133ms, 0→stop immediately.
def _coast_frames(dist_m: float) -> int:
    if dist_m >= 2.0:  return 10
    if dist_m >= 1.0:  return 4
    if dist_m >= 0.5:  return 3
    return 1           # < 0.5m — single miss stops immediately



# ── Pitch ramp ────────────────────────────────────────────────────────────────
PITCH_RATE_HZ = 50


class BaseController:
    """
    Decoupled 15 Hz motor controller.

    The main loop writes target data via update_target(); this thread
    reads it, applies smoothing + blind-follow logic, and sends velocity
    commands to the robot at a fixed rate.

    Also manages body pitch via start_pitch_ramp() / stop_pitch().
    Pass euler_cmd_callback=io.euler to enable pitch control.
    """

    def __init__(
        self,
        move_cmd_callback: Callable[[float, float, float], None],
        euler_cmd_callback: Optional[Callable[[float, float, float], None]] = None,
    ):
        self._move  = move_cmd_callback
        self._euler = euler_cmd_callback
        self._lock  = threading.Lock()

        # Shared state (written by update_target / set_mode, read by loop)
        self._detected    = False
        self._dist_m      = 999.0
        self._dx_norm     = 0.0
        self._mode        = "idle"
        self._search_vyaw = SEARCH_VYAW
        self._is_arrived  = False

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # ── Pitch ramp ────────────────────────────────────────────────────────
        self._pitch_lock    = threading.Lock()
        self._pitch_target  = 0.0
        self._pitch_step_ps = 0.0
        self._pitch_running = False
        self._pitch_thread: Optional[threading.Thread] = None
        self._pitch_done    = threading.Event()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="base-ctrl")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self._move(0.0, 0.0, 0.0)

    def update_target(self, detected: bool, dist_m: float, dx_norm: float) -> None:
        """Thread-safe write from the vision/main loop."""
        import logging, time as _time
        _log = logging.getLogger(__name__)
        _log.debug(
            f"[LAG] update_target @ {_time.time():.3f}  "
            f"detected={detected}  dist={dist_m:.2f}m  dx={dx_norm:+.3f}"
        )
        with self._lock:
            self._detected = detected
            self._dist_m   = dist_m
            self._dx_norm  = dx_norm

    def set_mode(self, mode: str, search_vyaw: Optional[float] = None) -> None:
        """Set controller mode: idle, approach, search_rotate, or search_hold."""
        with self._lock:
            self._mode = str(mode)
            if search_vyaw is not None:
                self._search_vyaw = float(search_vyaw)
            self._is_arrived = False

    def is_arrived(self) -> bool:
        """Thread-safe read for the state machine."""
        with self._lock:
            return self._is_arrived

    # ── Pitch ramp API ────────────────────────────────────────────────────────

    def start_pitch_ramp(self, target_deg: float, step_deg_per_s: float = 6.0) -> None:
        """
        Begin ramping body pitch from 0 → target_deg at step_deg_per_s deg/s,
        then hold continuously.  Requires euler_cmd_callback at construction.
        Call wait_pitch_done() to block until the ramp finishes.
        """
        if self._euler is None:
            raise RuntimeError(
                "euler_cmd_callback is None — pass euler_cmd_callback=io.euler "
                "to BaseController to enable pitch control."
            )
        with self._pitch_lock:
            self._pitch_target  = math.radians(target_deg)
            self._pitch_step_ps = math.radians(step_deg_per_s)
            self._pitch_done.clear()
            if not self._pitch_running:
                self._pitch_running = True
                self._pitch_thread = threading.Thread(
                    target=self._pitch_loop, daemon=True, name="pitch-ramp"
                )
                self._pitch_thread.start()

    def wait_pitch_done(self, timeout: float = 5.0) -> bool:
        """Block until the pitch ramp reaches its target.  Returns False on timeout."""
        return self._pitch_done.wait(timeout=timeout)

    def stop_pitch(self) -> None:
        """
        Ramp body pitch back to 0°, wait until complete, then stop the pitch thread.
        Blocks until pitch is back at zero (or 5 s timeout).
        """
        with self._pitch_lock:
            self._pitch_target = 0.0
            self._pitch_done.clear()
        self._pitch_done.wait(timeout=5.0)
        self._pitch_running = False
        if self._pitch_thread:
            self._pitch_thread.join(timeout=2.0)
        if self._euler is not None:
            self._euler(0.0, 0.0, 0.0)

    # ── Pitch loop (private) ──────────────────────────────────────────────────

    def _pitch_loop(self) -> None:
        dt      = 1.0 / PITCH_RATE_HZ
        current = 0.0

        while self._pitch_running:
            t0 = time.time()

            with self._pitch_lock:
                target = self._pitch_target
                step   = self._pitch_step_ps * dt

            if abs(current - target) > 1e-5:
                if current < target:
                    current = min(current + step, target)
                else:
                    current = max(current - step, target)
                if abs(current - target) <= 1e-5:
                    self._pitch_done.set()

            if self._euler is not None:
                self._euler(0.0, current, 0.0)

            elapsed = time.time() - t0
            time.sleep(max(0.0, dt - elapsed))

    # ── Motor control loop (private) ──────────────────────────────────────────

    def _loop(self) -> None:
        dt = 1.0 / CONTROL_HZ

        # Loop-local state (only this thread touches these — no lock needed)
        smooth_dx   = 0.0
        smooth_dist = 999.0
        last_mode   = None
        miss_streak   = 0
        last_vyaw     = 0.0
        ever_detected = False

        while self._running:
            t0 = time.time()

            with self._lock:
                mode        = self._mode
                detected    = self._detected
                dist_m      = self._dist_m
                dx_norm     = self._dx_norm
                search_vyaw = self._search_vyaw

            # Reset EMA / counters on mode change
            if mode != last_mode:
                smooth_dx     = 0.0
                smooth_dist   = 999.0
                miss_streak   = 0
                last_vyaw     = 0.0
                ever_detected = False
                with self._lock:
                    self._is_arrived = False
                last_mode = mode

            # ── Non-approach modes ────────────────────────────────────────────
            if mode == "search_rotate":
                self._move(0.0, 0.0, search_vyaw)
                with self._lock:
                    self._is_arrived = False
                time.sleep(max(0.001, dt - (time.time() - t0)))
                continue

            if mode in ("search_hold", "idle"):
                self._move(0.0, 0.0, 0.0)
                with self._lock:
                    self._is_arrived = False
                time.sleep(max(0.001, dt - (time.time() - t0)))
                continue

            if mode != "approach":
                self._move(0.0, 0.0, 0.0)
                with self._lock:
                    self._is_arrived = False
                time.sleep(max(0.001, dt - (time.time() - t0)))
                continue

            # ── Approach mode ─────────────────────────────────────────────────
            if detected:
                ever_detected = True
                miss_streak   = 0
                smooth_dx   = (1.0 - DX_ALPHA)  * smooth_dx   + DX_ALPHA   * (dx_norm + DX_BIAS)
                smooth_dist = (1.0 - DIST_ALPHA) * smooth_dist + DIST_ALPHA * dist_m

                dx      = smooth_dx if abs(smooth_dx) > YAW_DEADBAND_NORM else 0.0
                # Stop purely on distance — no dx centering required
                arrived = dist_m <= APPROACH_STOP_DIST_M

                if arrived:
                    self._move(0.0, 0.0, 0.0)
                    with self._lock:
                        self._is_arrived = True
                else:
                    vyaw = max(-MAX_VYAW, min(MAX_VYAW, -K_APPROACH_YAW * dx))
                    if 1e-6 < abs(vyaw) < MIN_VYAW:
                        vyaw = MIN_VYAW if vyaw > 0 else -MIN_VYAW
                    last_vyaw = vyaw   # save for coasting
                    self._move(APPROACH_VX_CONST, 0.0, vyaw)
                    with self._lock:
                        self._is_arrived = False

            else:
                # Ball not in frame — coast for a distance-adaptive window before
                # stopping.  Far away: long coast (10 frames); close: short (1 frame).
                # smooth_dist is frozen at last known value when ball is lost.
                miss_streak += 1
                if ever_detected and miss_streak < _coast_frames(smooth_dist):
                    self._move(APPROACH_VX_CONST, 0.0, last_vyaw)
                else:
                    self._move(0.0, 0.0, 0.0)
                with self._lock:
                    self._is_arrived = False

            time.sleep(max(0.001, dt - (time.time() - t0)))
