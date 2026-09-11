# Go2 Body Pose Control — Technical Reference

This document captures every issue encountered, root cause, fix applied, and
design decision made while implementing smooth, precise body pose control on the
Unitree Go2 EDU via `unitree_sdk2py`. Written as a reference for future
implementations.

---

## API Overview

### What is available

```python
from unitree_sdk2py.go2.sport.sport_client import SportClient

sport = SportClient()
sport.SetTimeout(10.0)
sport.Init()

sport.BalanceStand()          # enter balance-stand mode (prerequisite)
sport.Pose(True)              # enable free pose control (prerequisite)
sport.Euler(roll, pitch, yaw) # set body orientation (radians)
sport.Pose(False)             # exit pose mode
sport.StopMove()              # stop all motion
```

### What is NOT available on Go2

`BodyHeight(height)` — this method exists only on the **B2** robot.
The Go2 SDK does not expose direct height control. The only pose control
available at the high level is `Euler()`.

---

## Coordinate Conventions

### Euler angles
| Axis | Positive direction | Unit |
|------|--------------------|------|
| roll | lean right | radians |
| pitch | nose down | radians |
| yaw | body twist (relative, not absolute heading) | radians |

### IMU sensor (rt/sportmodestate → imu_state.rpy)
| Index | Axis | Meaning |
|-------|------|---------|
| rpy[0] | roll | absolute body tilt left/right in world frame |
| rpy[1] | pitch | absolute body tilt forward/back in world frame |
| rpy[2] | yaw | **absolute compass heading** — NOT relative twist |

### Critical: Yaw frame mismatch

`Euler(0, 0, yaw_cmd)` — `yaw_cmd` is a **relative body twist** from the
robot's default standing orientation.

`imu_state.rpy[2]` — **absolute compass heading** (e.g. -153.7° when the
robot faces roughly south-southwest).

These two are in completely different frames. Comparing them directly will give
nonsensical results. Always track yaw as a **delta from the heading at the
start of each move**:

```python
yaw_ref = rpy[2]  # capture absolute heading before move starts

# During move:
delta = rpy_now[2] - yaw_ref
if delta >  math.pi: delta -= 2 * math.pi   # wrap correction
if delta < -math.pi: delta += 2 * math.pi
# delta is now the actual rotation from start in radians
```

Use the **same yaw_ref** for both GO and RETURN phases. If yaw_ref is
recomputed at the start of RETURN (using the post-GO heading), the delta
measurement is wrong: error grows instead of shrinks and the robot never
converges back.

---

## Prerequisites — Order Matters

```python
sport.BalanceStand()   # must come first
time.sleep(1.0)        # wait for mode transition
sport.Pose(True)       # must come before any Euler() call
time.sleep(0.5)
```

Without `BalanceStand()`: Euler commands are silently ignored.  
Without `Pose(True)`: Euler commands are also silently ignored (return code 0
but robot doesn't move).

---

## Issue Log

### Issue 1 — Euler must be sent continuously

**Symptom:** Robot holds pose briefly then snaps back to default.

**Root cause:** The firmware has an internal watchdog. If no Euler command
arrives within ~200 ms, it abandons the setpoint and returns to default
balance pose.

**Fix:** Run a dedicated background thread that sends `Euler()` at 50 Hz
continuously for the entire session — during ramp, hold, and return. The main
thread only updates the shared command values; the sender thread handles
transmission.

```python
def sender_thread(sport, shared, stop_evt):
    while not stop_evt.is_set():
        t0 = time.perf_counter()
        cmd = shared.get_cmd()
        sport.Euler(cmd[0], cmd[1], cmd[2])
        wait = SENDER_DT - (time.perf_counter() - t0)
        if wait > 0:
            time.sleep(wait)
```

**Why not just call Euler in the main loop?**  
`sport.Euler()` is a blocking DDS request-reply RPC call. Each call takes
30–80 ms waiting for acknowledgment. If you also sleep in the same loop, the
actual send rate drops to 10–15 Hz. Combined with variable timing, the robot
receives commands unevenly — producing the discrete "stepping" motion.

The background thread sends at exactly 50 Hz regardless of what the main
thread is doing.

---

### Issue 2 — Movement feels discrete / not smooth

**Symptom:** Instead of smooth continuous motion, the robot visibly steps
through discrete poses.

**Root causes:**
1. `Euler()` RPC blocks for 30–80 ms. Sleeping on top of this gives ~10 Hz
   actual send rate → 2–5° per step at any reasonable speed. Clearly visible.
2. The robot's balance controller has its own update rate. Commands arriving
   too infrequently cause chunky tracking.

**Fix:** Separate the ramp logic from the send loop (see Issue 1). The ramp
updates the target angle at 50 Hz with 0.4° steps; the sender sends at 50 Hz
independently. The robot receives a smooth stream of small increments.

**Remaining limitation:** The robot's internal pose controller has a bandwidth
of roughly 5–15 °/s. Above this rate, the body lags behind the command. The
lag is visible as `lag=` in the terminal output.

---

### Issue 3 — Commanded angle ≠ achieved sensor angle

**Symptom:** Commanding roll=30° → sensor reads 19°. Commanding 28° → sensor
reads 17°. Lower commands achieve proportionally less; not a hard clamp.

**Root cause:** The BalanceStand firmware applies Euler setpoints through its
own balance PID with an effective gain of ~0.65. The firmware is trading pose
accuracy for stability margin. This is not a bug — it is intentional behavior.

**Measured approximate gains (this robot, default firmware):**
| Axis | Commanded | Achieved | Effective gain |
|------|-----------|----------|----------------|
| Roll | 30° | ~19° | ~0.63 |
| Roll | 43° | ~32° | ~0.74 |
| Pitch | 25° | ~18° | ~0.72 |

**Physical limits observed (actual sensor values):**
- Roll: ~19–20° maximum achievable
- Pitch: ~17–18° maximum achievable
- Yaw: ~23° (with ~100% gain — yaw is more direct)

**Fix:** Sensor-driven ramp. Instead of stopping when `cmd == target`, continue
advancing `cmd` past the target (up to `CMD_OVERHEAD = 30°` beyond) until the
**sensor** reads the desired angle. The cmd automatically self-adjusts to
whatever value pulls the sensor to the target — no gain calibration needed.

```
while abs(sensor - desired) > ARRIVE_TOL:
    if sensor_stalled_for(STALL_T):
        break   # physical limit
    cmd += RAMP_STEP * direction   # keep pushing cmd past target
```

---

### Issue 4 — Sensor-gated ramp causes deadlock

**Symptom:** Robot doesn't move at all. `cmd` gets stuck at ~1° and never
advances.

**Root cause:** An attempted approach gated cmd advancement on sensor position
(`advance cmd only if sensor is within GATE=2° of cmd`). The robot has a
dead-band: it doesn't respond to Euler commands smaller than ~2–3°. So the
sensor never moved, the gate never opened, and cmd was permanently frozen.

**Fix:** Abandoned sensor gating. The sensor-driven ramp (Issue 3 fix) handles
this correctly: cmd advances at a fixed rate and goes past the target until the
sensor arrives. No gating needed.

---

### Issue 5 — Return to neutral is not precise

**Symptom:** After moving to a pose and returning "to 0°", the robot stops
several degrees short of the starting position.

**Root cause:** Same as Issue 3. The return ramp also has the 0.65× gain
problem. Commanding cmd back to 0° only moves the robot 65% of the way back.

**Additional cause:** The robot's natural balance pose is NOT at IMU 0°. At
startup the sensor might read roll=-1.2°, pitch=+0.7°. Commanding "return to
0°" would return to the wrong position.

**Fix:**
1. Capture `start_sensor = rpy[axis]` before moving (the robot's natural pose
   for that axis).
2. Use that as the RETURN target instead of 0°.
3. The sensor-driven ramp (Issue 3 fix) handles the gain — cmd overshoots
   until sensor actually reads start_sensor.

---

### Issue 6 — Yaw return causes large rotation / spinning

**Symptom:** When returning from a yaw pose, the robot spins wildly (~154°
rotation) instead of returning to its original heading.

**Root cause:** Two combined bugs:
1. yaw_ref was recomputed at the start of RETURN (using post-GO heading).
   This made the delta measurement wrong — error grew as robot returned,
   causing cmd to spiral in the wrong direction.
2. Returning "to yaw=0°" was interpreted as absolute world heading 0° (north),
   not "back to start heading."

**Fix:** Capture `yaw_start = rpy[2]` (absolute heading) before any movement
on this axis. Pass it to both the GO and RETURN `ramp_to` calls as
`yaw_ref_override`. Both phases measure delta from the same reference:
- GO target: +25° delta → robot twists 25° from original heading
- RETURN target: 0° delta → robot returns to original heading

---

### Issue 7 — Movement speed cannot be directly commanded

**Symptom:** No API to set body rotation speed. "Move at 10°/s" doesn't work
as expected.

**Root cause:** `Euler()` is a position setpoint command, not a velocity
command. The firmware decides how fast to reach the setpoint using its own
internal controller. You cannot specify speed directly.

**Workaround:** Ramp the position setpoint at the desired rate. If the robot's
bandwidth exceeds the ramp rate, the sensor roughly tracks the ramp, giving
approximately uniform speed.

**Practical bandwidth:** ~5–15 °/s for roll/pitch. Above ~15°/s, the body lags
significantly behind the cmd. At 5°/s, tracking is near-perfect but slow.

**Current implementation:** `SPEED = 23°/s` cmd ramp. Sensor moves at
~15°/s due to 0.65× gain. This is approximately uniform.

**Actual sensor speed is not directly controllable.** To make it more precise,
a speed controller would be needed:
```
measured_speed = (sensor_now - sensor_prev) / dt
cmd_advance = Kp * (desired_speed - measured_speed)
```
This adds complexity and the robot's bandwidth still sets the ceiling.

---

## Architecture — Background Sender

```
┌─────────────────────────────────────────────────────────────┐
│ Main Thread                                                 │
│                                                             │
│  ramp_to() — updates shared.cmd[] at RAMP_DT intervals     │
│  hold()    — blocks on input(), does not touch shared.cmd   │
│  run_axis()— sequences GO → hold → RETURN → hold           │
└──────────────────────────┬──────────────────────────────────┘
                           │ shared.cmd [roll, pitch, yaw]
                           │ (thread-safe lock)
┌──────────────────────────▼──────────────────────────────────┐
│ Sender Thread (daemon)                                      │
│                                                             │
│  loop at 50 Hz:                                             │
│    cmd = shared.get_cmd()                                   │
│    sport.Euler(cmd[0], cmd[1], cmd[2])                      │
│                                                             │
│  Runs for entire session — during ramp, hold, return.       │
│  No gaps. Robot never times out.                            │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ IMU Subscriber (DDS callback thread)                        │
│                                                             │
│  rt/sportmodestate → imu_state.rpy[0,1,2]                  │
│  Computes speed = (rpy_now - rpy_prev) / dt                 │
│  Stores in shared.rpy, shared.spd                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `SPEED` | 23°/s | cmd ramp rate (tune for desired motion speed) |
| `SENDER_HZ` | 50 | Euler send frequency (do not go below 20) |
| `MAX_ANGLE` | ±43° | Safety limit on cmd (3° inside ±46° firmware range) |
| `CMD_OVERHEAD` | 30° | How far cmd can go past target to pull sensor |
| `ARRIVE_TOL` | ±0.5° | Sensor within this of target = arrived |
| `STALL_T` | 2.5 s | Time without sensor movement = physical limit |
| `STALL_DELTA` | 0.3° | Minimum sensor change to reset stall clock |
| `SETTLE_T` | 1.0 s | Wait after arriving before reporting |

---

## IMU Sensor Access

```python
from unitree_sdk2py.core.channel import ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

def callback(msg: SportModeState_):
    roll  = float(msg.imu_state.rpy[0])   # radians
    pitch = float(msg.imu_state.rpy[1])   # radians
    yaw   = float(msg.imu_state.rpy[2])   # radians — ABSOLUTE HEADING

sub = ChannelSubscriber("rt/sportmodestate", SportModeState_)
sub.Init(callback, 10)   # 10 = queue depth
```

Speed from consecutive readings:
```python
speed[i] = (rpy_now[i] - rpy_prev[i]) / dt   # rad/s
```

---

## Logging

Each run writes `logs/pose_YYYYMMDD_HHMMSS.csv` with columns:

| Column | Description |
|--------|-------------|
| `t_s` | seconds from session start |
| `phase` | GO / RETURN / HOLD |
| `axis` | ROLL / PITCH / YAW |
| `cmd_deg` | commanded Euler angle (degrees) |
| `sensor_deg` | IMU sensor reading or delta (degrees) |
| `target_deg` | desired sensor angle (degrees) |
| `error_deg` | target - sensor (positive = still needs to move) |
| `lag_deg` | cmd - sensor (how far cmd is ahead of body) |
| `speed_dps` | sensor angular speed (degrees/s) |
| `roll_deg` | absolute IMU roll |
| `pitch_deg` | absolute IMU pitch |
| `yaw_deg` | absolute IMU yaw (compass heading) |

---

## Known Firmware Limits

| Axis | Max achievable sensor angle |
|------|-----------------------------|
| Roll | ~19–20° |
| Pitch | ~17–18° |
| Yaw | ~23° |

These limits are enforced by the BalanceStand controller's stability margin,
not by hard angle stops. They may vary with surface, battery level, and payload.
The stall detector catches these limits automatically.

---

## Usage

```bash
python3 control_pose.py eth0
```

Prompts for target roll, pitch, yaw in degrees (clamped to ±43°).  
Each axis: **Enter** to move → holds at achieved pose → **Enter** to return.

```
ROLL  | cmd=+28.40°  sensor=+18.82°  error=+0.18°  lag=+9.58°  speed=+12.1°/s
ROLL  | ARRIVED  sensor=+19.02°  target=+19.0°  error=+0.02°  cmd=+28.70°
ROLL  | Settling 1.0s...
ROLL  | SETTLED  target=+19.0°  sensor=+18.97°  error=-0.03°  speed=+0.01°/s
[HOLD: ROLL @ +18.97°]  Press Enter to continue...
```

The `lag` column shows how far the cmd had to overshoot to pull the sensor to
the target. Typical lag for roll: 8–12°.
