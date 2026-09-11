"""
Interactively control Go2 body pose one axis at a time.

Flow for each axis:
  Press Enter → move to target → hold
  Press Enter → return to start → hold
  → next axis

Precision strategy — sensor-driven:
  The cmd advances at constant speed (5°/s) and keeps going past the nominal
  target until the SENSOR actually reads the desired angle. This compensates for
  the robot's firmware gain (<1) automatically — no calibration needed.
  If the sensor stalls for STALL_T seconds, the robot is at its physical limit
  and we hold there.

Logging:
  Every tick is written to logs/pose_YYYYMMDD_HHMMSS.csv for post-analysis.

Usage:
    python3 control_pose.py [network_interface]
    python3 control_pose.py eth0
"""

import sys
import os
import csv
import time
import math
import datetime
import threading

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
from unitree_sdk2py.go2.sport.sport_client import SportClient

# ── Config ─────────────────────────────────────────────────────────────────────
SPEED      = math.radians(23)   # 15°/s cmd advance rate
SENDER_HZ  = 50                 # background Euler send rate (Hz)
SENDER_DT  = 1.0 / SENDER_HZ
RAMP_DT    = 0.02               # 50 Hz ramp ticks
RAMP_STEP  = SPEED * RAMP_DT   # 0.1° per tick

MAX_ANGLE  = math.radians(43)   # ±43° safety limit on cmd
# Extra cmd range beyond nominal target to allow sensor to catch up
CMD_OVERHEAD = math.radians(30) # cmd can go up to 25° past target to pull sensor

ARRIVE_TOL  = math.radians(0.5) # sensor within 0.5° = arrived
STALL_T     = 2.5               # seconds without sensor movement = physical limit
STALL_DELTA = math.radians(0.3) # minimum sensor movement to not be considered stalled
SETTLE_T    = 1.0               # seconds to wait after declaring arrived

LOG_DIR = "/home/unitree/go2_sdk_docs/logs"
# ──────────────────────────────────────────────────────────────────────────────


class Shared:
    def __init__(self):
        self._lock     = threading.Lock()
        self.cmd       = [0.0, 0.0, 0.0]
        self.rpy       = [0.0, 0.0, 0.0]
        self.spd       = [0.0, 0.0, 0.0]
        self._prev_rpy = None
        self._prev_t   = None
        self.imu_ready = False

    def set_cmd(self, roll, pitch, yaw):
        with self._lock:
            self.cmd = [roll, pitch, yaw]

    def get_cmd(self):
        with self._lock:
            return list(self.cmd)

    def get_sensor(self):
        with self._lock:
            return list(self.rpy), list(self.spd)

    def imu_callback(self, msg: SportModeState_):
        now = time.time()
        rpy = [float(msg.imu_state.rpy[i]) for i in range(3)]
        with self._lock:
            if self._prev_rpy is not None and self._prev_t is not None:
                dt = now - self._prev_t
                if dt > 1e-4:
                    self.spd = [(rpy[i] - self._prev_rpy[i]) / dt for i in range(3)]
            self.rpy       = rpy
            self._prev_rpy = rpy
            self._prev_t   = now
            self.imu_ready = True

    def wait_imu(self, timeout=5.0):
        t0 = time.time()
        while True:
            with self._lock:
                if self.imu_ready:
                    return True
            if time.time() - t0 > timeout:
                return False
            time.sleep(0.05)


def clamp(v, lo, hi=None):
    if hi is None:
        return max(-lo, min(lo, v))
    return max(lo, min(hi, v))


def yaw_delta(rpy, ref):
    """Wrap-aware yaw delta from reference heading."""
    d = rpy[2] - ref
    if d >  math.pi: d -= 2 * math.pi
    if d < -math.pi: d += 2 * math.pi
    return d


def sender_thread(sport, shared, stop_evt):
    while not stop_evt.is_set():
        t0  = time.perf_counter()
        cmd = shared.get_cmd()
        sport.Euler(cmd[0], cmd[1], cmd[2])
        wait = SENDER_DT - (time.perf_counter() - t0)
        if wait > 0:
            time.sleep(wait)


def open_log():
    os.makedirs(LOG_DIR, exist_ok=True)
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(LOG_DIR, f"pose_{ts}.csv")
    fh   = open(path, "w", newline="")
    cols = ["t_s", "phase", "axis",
            "cmd_deg", "sensor_deg", "target_deg",
            "error_deg", "lag_deg", "speed_dps",
            "roll_deg", "pitch_deg", "yaw_deg"]
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    print(f"Log → {path}")
    return fh, w


def write_log(w, t, phase, axis, cmd, sensor, target, speed, rpy):
    w.writerow({
        "t_s"        : f"{t:.4f}",
        "phase"      : phase,
        "axis"       : axis,
        "cmd_deg"    : f"{math.degrees(cmd):+.3f}",
        "sensor_deg" : f"{math.degrees(sensor):+.3f}",
        "target_deg" : f"{math.degrees(target):+.3f}",
        "error_deg"  : f"{math.degrees(target - sensor):+.3f}",
        "lag_deg"    : f"{math.degrees(cmd - sensor):+.3f}",
        "speed_dps"  : f"{math.degrees(speed):+.3f}",
        "roll_deg"   : f"{math.degrees(rpy[0]):+.3f}",
        "pitch_deg"  : f"{math.degrees(rpy[1]):+.3f}",
        "yaw_deg"    : f"{math.degrees(rpy[2]):+.3f}",
    })


def ramp_to(shared, axis_idx, target_rad, label, log_writer, t0_global, phase,
            yaw_ref_override=None):
    """
    Advance cmd at constant SPEED until SENSOR reaches target_rad (±ARRIVE_TOL).
    cmd is allowed to go CMD_OVERHEAD past target to pull the sensor there.
    Stops early if sensor stalls for STALL_T (physical limit reached).
    Returns actual achieved sensor angle.

    yaw_ref_override: if provided, use this as the yaw reference heading instead
    of the current heading. Must be passed for RETURN so the delta is measured
    from the original start heading, not from the post-GO heading.
    """
    cmd       = shared.get_cmd()
    rpy0, _   = shared.get_sensor()
    yaw_ref   = yaw_ref_override if yaw_ref_override is not None else rpy0[2]
    cmd_start = cmd[axis_idx]
    direction = 1 if target_rad > cmd_start else (-1 if target_rad < cmd_start else 0)

    if direction == 0:
        return (yaw_delta(rpy0, yaw_ref) if axis_idx == 2 else rpy0[axis_idx])

    # cmd is allowed up to CMD_OVERHEAD past target
    cmd_limit = clamp(target_rad + direction * CMD_OVERHEAD, -MAX_ANGLE, MAX_ANGLE)
    total_deg = abs(math.degrees(target_rad - cmd_start))
    print(f"\n  {label} | {math.degrees(cmd_start):+.1f}° → sensor target {math.degrees(target_rad):+.1f}°  "
          f"({math.degrees(SPEED):.0f}°/s  ~{total_deg/math.degrees(SPEED):.1f}s + correction)")
    print(f"  {label} | cmd allowed up to {math.degrees(cmd_limit):+.1f}° to pull sensor to target")

    stall_sensor_last = None
    stall_since       = None

    while True:
        t_tick   = time.perf_counter()
        t_rel    = time.time() - t0_global
        cmd      = shared.get_cmd()
        rpy, spd = shared.get_sensor()

        sv = yaw_delta(rpy, yaw_ref) if axis_idx == 2 else rpy[axis_idx]
        ss = spd[axis_idx]

        error  = target_rad - sv
        lag    = cmd[axis_idx] - sv

        # ── Stall detection ────────────────────────────────────────────────────
        if stall_sensor_last is None:
            stall_sensor_last = sv
            stall_since       = time.time()
        elif abs(sv - stall_sensor_last) > STALL_DELTA:
            stall_sensor_last = sv          # sensor moved — reset stall clock
            stall_since       = time.time()
        stall_duration = time.time() - stall_since

        # ── Arrived check ──────────────────────────────────────────────────────
        arrived = abs(error) <= ARRIVE_TOL
        stalled = stall_duration >= STALL_T and abs(error) > ARRIVE_TOL

        # ── Advance cmd if not arrived and cmd hasn't hit its limit ────────────
        cmd_at_limit = (direction > 0 and cmd[axis_idx] >= cmd_limit) or \
                       (direction < 0 and cmd[axis_idx] <= cmd_limit)
        if not arrived and not stalled and not cmd_at_limit:
            remaining = cmd_limit - cmd[axis_idx]
            if abs(remaining) <= RAMP_STEP:
                cmd[axis_idx] = cmd_limit
            else:
                cmd[axis_idx] += direction * RAMP_STEP
            shared.set_cmd(cmd[0], cmd[1], cmd[2])

        # ── Log ────────────────────────────────────────────────────────────────
        write_log(log_writer, t_rel, phase, label,
                  cmd[axis_idx], sv, target_rad, ss, rpy)

        # ── Print ──────────────────────────────────────────────────────────────
        stall_str = f"  STALL {stall_duration:.1f}s" if stall_duration > 0.5 else ""
        print(
            f"  {label:5s} | "
            f"cmd={math.degrees(cmd[axis_idx]):+6.2f}°  "
            f"sensor={math.degrees(sv):+6.2f}°  "
            f"error={math.degrees(error):+5.2f}°  "
            f"lag={math.degrees(lag):+5.2f}°  "
            f"speed={math.degrees(ss):+5.1f}°/s"
            f"{stall_str}",
            end="\r", flush=True
        )

        if arrived:
            print(f"\n  {label:5s} | ARRIVED  "
                  f"sensor={math.degrees(sv):+.2f}°  "
                  f"target={math.degrees(target_rad):+.1f}°  "
                  f"error={math.degrees(error):+.2f}°  "
                  f"cmd={math.degrees(cmd[axis_idx]):+.2f}°")
            break

        if stalled:
            print(f"\n  {label:5s} | STALLED at sensor={math.degrees(sv):+.2f}°  "
                  f"(target={math.degrees(target_rad):+.1f}°  "
                  f"error={math.degrees(error):+.2f}°  "
                  f"physical limit reached)")
            break

        elapsed = time.perf_counter() - t_tick
        wait    = RAMP_DT - elapsed
        if wait > 0:
            time.sleep(wait)

    # Settle
    print(f"  {label:5s} | Settling {SETTLE_T:.1f}s...")
    time.sleep(SETTLE_T)

    rpy, spd = shared.get_sensor()
    sv_final = yaw_delta(rpy, yaw_ref) if axis_idx == 2 else rpy[axis_idx]

    print(
        f"  {label:5s} | SETTLED  "
        f"target={math.degrees(target_rad):+.1f}°  "
        f"sensor={math.degrees(sv_final):+.2f}°  "
        f"error={math.degrees(target_rad - sv_final):+.2f}°  "
        f"speed={math.degrees(spd[axis_idx]):+.2f}°/s"
    )

    # Lock cmd to achieved sensor so hold sends the right angle
    cmd = shared.get_cmd()
    cmd[axis_idx] = sv_final
    shared.set_cmd(cmd[0], cmd[1], cmd[2])
    return sv_final


def hold(shared, label, log_writer, t0_global, axis_idx):
    print(f"\n  [HOLD: {label}]  Press Enter to continue...")
    stop_flag = threading.Event()

    def print_loop():
        while not stop_flag.is_set():
            rpy, spd = shared.get_sensor()
            cmd      = shared.get_cmd()
            t_rel    = time.time() - t0_global
            write_log(log_writer, t_rel, "HOLD", label,
                      cmd[axis_idx], rpy[axis_idx], cmd[axis_idx], spd[axis_idx], rpy)
            print(
                f"  HOLD | "
                f"cmd  r={math.degrees(cmd[0]):+5.1f}°  "
                f"p={math.degrees(cmd[1]):+5.1f}°  "
                f"y={math.degrees(cmd[2]):+5.1f}°  │  "
                f"sensor  r={math.degrees(rpy[0]):+5.1f}°  "
                f"p={math.degrees(rpy[1]):+5.1f}°  "
                f"y={math.degrees(rpy[2]):+5.1f}°  │  "
                f"spd  r={math.degrees(spd[0]):+4.1f}  "
                f"p={math.degrees(spd[1]):+4.1f}  "
                f"y={math.degrees(spd[2]):+4.1f} °/s  ",
                end="\r", flush=True
            )
            time.sleep(0.1)

    pt = threading.Thread(target=print_loop, daemon=True)
    pt.start()
    input()
    stop_flag.set()
    pt.join()
    print()


def run_axis(shared, axis_idx, target_rad, label, log_writer, t0_global):
    rpy0, _ = shared.get_sensor()
    start_sensor = rpy0[axis_idx]       # absolute sensor at start (roll/pitch)
    yaw_start    = rpy0[2]              # absolute yaw at start — used as ref for both GO and RETURN

    input(f"\n[{label}] Press Enter to move to sensor target {math.degrees(target_rad):+.1f}°...")
    achieved = ramp_to(shared, axis_idx, target_rad, label,
                       log_writer, t0_global, "GO",
                       yaw_ref_override=yaw_start if axis_idx == 2 else None)
    hold(shared, f"{label} @ {math.degrees(achieved):+.2f}°",
         log_writer, t0_global, axis_idx)

    input(f"[{label}] Press Enter to return to start ({math.degrees(start_sensor):+.1f}°)...")
    if axis_idx == 2:
        # Pass same yaw_ref so delta is measured from the original heading — target=0 means back to start
        ramp_to(shared, axis_idx, 0.0, label, log_writer, t0_global, "RETURN",
                yaw_ref_override=yaw_start)
    else:
        ramp_to(shared, axis_idx, start_sensor, label, log_writer, t0_global, "RETURN")
    hold(shared, f"{label} returned",
         log_writer, t0_global, axis_idx)


def main():
    if len(sys.argv) > 1:
        ChannelFactoryInitialize(0, sys.argv[1])
    else:
        ChannelFactoryInitialize(0)

    shared = Shared()
    sub    = ChannelSubscriber("rt/sportmodestate", SportModeState_)
    sub.Init(shared.imu_callback, 10)

    print("Waiting for IMU...")
    if not shared.wait_imu():
        print("ERROR: no data on rt/sportmodestate")
        return
    rpy, _ = shared.get_sensor()
    print(f"IMU ready  roll={math.degrees(rpy[0]):+.1f}°  "
          f"pitch={math.degrees(rpy[1]):+.1f}°  "
          f"yaw={math.degrees(rpy[2]):+.1f}° (absolute)\n")

    sport = SportClient()
    sport.SetTimeout(10.0)
    sport.Init()

    code = sport.BalanceStand()
    print(f"BalanceStand  code={code}")
    time.sleep(1.0)

    code = sport.Pose(True)
    print(f"Pose(True)    code={code}")
    time.sleep(0.5)

    rpy, _ = shared.get_sensor()
    shared.set_cmd(rpy[0], rpy[1], 0.0)

    stop_sender = threading.Event()
    st = threading.Thread(target=sender_thread,
                          args=(sport, shared, stop_sender), daemon=True)
    st.start()

    log_fh, log_writer = open_log()
    t0_global = time.time()

    print(f"\nConfig: speed={math.degrees(SPEED):.0f}°/s  "
          f"arrive_tol=±{math.degrees(ARRIVE_TOL):.1f}°  "
          f"stall={STALL_T:.1f}s  "
          f"cmd_overhead=±{math.degrees(CMD_OVERHEAD):.0f}°\n")

    print(f"Enter sensor target angles (degrees, ±{math.degrees(MAX_ANGLE):.0f}° max):\n")

    def ask(name):
        while True:
            try:
                v = math.radians(float(input(f"  {name}: ")))
                v = clamp(v, MAX_ANGLE)
                print(f"  → {math.degrees(v):+.1f}°\n")
                return v
            except ValueError:
                print("  Enter a number.")

    target_roll  = ask("roll  (+ lean right)")
    target_pitch = ask("pitch (+ nose down) ")
    target_yaw   = ask("yaw   (+ body twist, relative)")

    print("── ROLL → PITCH → YAW ──────────────────────────────────────────────")

    try:
        run_axis(shared, 0, target_roll,  "ROLL",  log_writer, t0_global)
        run_axis(shared, 1, target_pitch, "PITCH", log_writer, t0_global)
        run_axis(shared, 2, target_yaw,   "YAW",   log_writer, t0_global)
    except KeyboardInterrupt:
        print("\n[Interrupted]")

    rpy, spd = shared.get_sensor()
    cmd      = shared.get_cmd()
    print(f"\n── Final ────────────────────────────────────────────────────────────")
    print(f"  roll  cmd={math.degrees(cmd[0]):+.2f}°  sensor={math.degrees(rpy[0]):+.2f}°  "
          f"speed={math.degrees(spd[0]):+.2f}°/s")
    print(f"  pitch cmd={math.degrees(cmd[1]):+.2f}°  sensor={math.degrees(rpy[1]):+.2f}°  "
          f"speed={math.degrees(spd[1]):+.2f}°/s")
    print(f"  yaw   sensor={math.degrees(rpy[2]):+.2f}° (absolute)")
    print(f"────────────────────────────────────────────────────────────────────")

    stop_sender.set()
    st.join()
    log_fh.flush()
    log_fh.close()
    sport.Pose(False)
    sport.StopMove()
    print("Done.")


if __name__ == "__main__":
    main()
