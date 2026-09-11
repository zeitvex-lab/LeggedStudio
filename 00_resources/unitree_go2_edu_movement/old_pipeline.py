#!/usr/bin/env python3
"""
Go2 + wx250 Arm — Autonomous Dock, Grasp & Deliver
====================================================

Full sequence:
  1.  ARM INIT      — open gripper → home → sleep (tucked for walking)
  2.  DOCK TAG 0    — search wall AprilTag ID 0, approach to 1.0 m
  3.  PITCH DOWN    — Pose(true) + continuous Euler at 4 Hz
  4.  ARM PRESET    — sleep → home → preset 2
  5.  GRASP         — arm camera detects ground tag, grasps object
  6.  ARM RETURN    — arm back to preset 2 (holding object)
  7.  PITCH UP      — stop pitch, Pose(false), BalanceStand
  8.  DOCK TAG 1    — search AprilTag ID 1 (180 mm), approach to 1.0 m
  9.  DELIVER       — home → open gripper → sleep → done

Usage:
    python3 go2_dock_grasp.py
    python3 go2_dock_grasp.py --iface eth0 --pitch-deg 17
    python3 go2_dock_grasp.py --skip-dock   # test arm phases only
"""

import argparse
import json
import math
import os
import signal
import sys
import threading
import time

import numpy as np
import cv2
try:
    import cv2.aruco as aruco
except ImportError:
    from cv2 import aruco

# ==============================================================================
#  CONFIGURATION
# ==============================================================================

# ── DDS ──
DDS_IFACE = "eth0"

# ── Dog camera (1920×1080 fisheye) ──
DOG_K_FISHEYE = np.array([
    [1248.95099, 0.0,        957.862066],
    [0.0,        1247.94633, 530.821641],
    [0.0,        0.0,        1.0       ]
], dtype=np.float64)
DOG_D_FISHEYE = np.array([-0.04634571, -0.21551315, 0.45541731, -0.37792435],
                          dtype=np.float64)
DOG_IMG_W, DOG_IMG_H = 1920, 1080

# ── Dog body→camera transform (hand-measured) ──
T_BASE_CAM = np.array([
    [ 0.0,  0.0,  1.0,  0.31 ],
    [-1.0,  0.0,  0.0,  0.0  ],
    [ 0.0, -1.0,  0.0,  0.055],
    [ 0.0,  0.0,  0.0,  1.0  ]
], dtype=np.float64)

# ── AprilTags (docking) ──
WALL_TAG_FAMILY   = "tag36h11"
PICKUP_TAG_ID     = 0       # tag near object to pick up
PICKUP_TAG_SIZE   = 0.180   # meters
DELIVERY_TAG_ID   = 1       # tag at delivery location
DELIVERY_TAG_SIZE = 0.180   # meters

# ── Docking target ──
TARGET_DIST_M    = 1.0
TOL_DIST_M       = 0.05
TOL_LAT_M        = 0.05
TOL_YAW_DEG      = 4.0
CONVERGE_TIME_S  = 1.5

# ── Docking controller ──
CONTROL_HZ    = 4
MAX_VX, MAX_VY, MAX_VYAW = 0.35, 0.20, 0.5
MIN_VX, MIN_VY, MIN_VYAW = 0.20, 0.15, 0.10
K_DIST, K_LAT, K_YAW     = 0.6,  0.8,  1.0
YAW_FIRST_DEG = 20.0

# ── Fusion ──
ALPHA_TAG    = 0.3
SHORT_LOSS_S = 0.8
LONG_LOSS_S  = 3.0

# ── Search ──
SEARCH_VYAW      = 0.45
SEARCH_TIMEOUT_S = 25.0
DOG_CAM_FPS      = 10.0

# ── Pitch control ──
PITCH_DEG  = 17.0
PITCH_RAD  = math.radians(PITCH_DEG)
PITCH_HZ   = 4
PITCH_SETTLE_S = 2.0

# ── Arm: robot settings ──
ARM_ROBOT_MODEL = "wx250"
MOVING_TIME     = 2.0
ACCEL_TIME      = 0.6
SETTLE_S        = 0.15

HOVER_DISTANCE_M = 0.08
FIXED_ROLL       = 0.0
FIXED_PITCH      = np.pi / 2   # 90° downward

# ── Arm joint presets (degrees) ──
POSITION_1 = [0.0,  -90.0,  15.0,  69.0,  0.0]
POSITION_2 = [0.0,  -15.0,  48.0,  -6.0,  0.0]
POSITION_3 = [0.0, -78.0, 72.0, 7.0, 0.0 ]
POSITION_4 = [0.0, 35.0, -10.0, 65.0, 0.0 ]
PRESETS_DEG = {1: POSITION_1, 2: POSITION_2, 3: POSITION_3, 4: POSITION_4}

RETURN_PRESET_AFTER_GRASP = 2

# ── Arm camera (/dev/video0, 1280×720) ──
CAM_DEVICE = "/dev/video0"
CAM_W, CAM_H = 1280, 720

# ── Arm camera intrinsics (MUST match 1280×720) ──
K = np.array([
    [1020.78,    0.00,  569.61],
    [   0.00, 1027.20,  310.38],
    [   0.00,    0.00,    1.00]
], dtype=np.float64)
DIST = np.array([-0.216370, 0.076488, 0.000587, -0.000633, -0.024798],
                 dtype=np.float64)

# ── Hand-eye: EE → camera (from calibration) ──
T_ee_cam = np.array([
    [-0.01829869, -0.71656913,  0.69727601, -0.04152233],
    [-0.99937559, -0.00797410, -0.03442146,  0.00367226],
    [ 0.03022550, -0.69747049, -0.71597579,  0.07381512],
    [ 0.00000000,  0.00000000,  0.00000000,  1.00000000],
], dtype=np.float64)

# ── Ground AprilTag (grasping) ──
TAG_ID      = 0
TAG_SIZE_M  = 0.075   # 75 mm

# ── Cup offsets from tag center ──
CUP_OFFSET_X = -0.10
CUP_OFFSET_Y =  0.00
CUP_OFFSET_Z =  0.07

# ── Grasp safety ──
GRASP_DETECT_TRIES   = 15
GRASP_DETECT_SLEEP_S = 0.03
MIN_CUP_Z_M  = -0.40
MAX_R_XY_M   =  0.75
MIN_R_XY_M   =  0.15

# ── Debug ──
DEBUG_SAVE_IMAGES = True
DEBUG_DIR = "/tmp/dock_grasp_debug"


# ==============================================================================
#  SE(3) UTILITIES
# ==============================================================================

def wrap_pi(a):
    while a <= -math.pi: a += 2.0 * math.pi
    while a >  math.pi:  a -= 2.0 * math.pi
    return a

def build_T(R, t):
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = np.asarray(t, dtype=np.float64).flatten()
    return T

def inv_T(T):
    R = T[:3, :3]; t = T[:3, 3]
    Ti = np.eye(4, dtype=np.float64)
    Ti[:3, :3] = R.T
    Ti[:3, 3] = -R.T @ t
    return Ti

def T_from_xyyaw(x, y, yaw, z=0.0):
    c, s = math.cos(yaw), math.sin(yaw)
    T = np.eye(4, dtype=np.float64)
    T[0, 0] = c; T[0, 1] = -s
    T[1, 0] = s; T[1, 1] = c
    T[0, 3] = x; T[1, 3] = y; T[2, 3] = z
    return T

def rvec_tvec_to_T(rvec, tvec):
    R, _ = cv2.Rodrigues(rvec)
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = tvec.reshape(3)
    return T

def rpy_to_R(roll, pitch, yaw):
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]], dtype=np.float64)
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]], dtype=np.float64)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]], dtype=np.float64)
    return Rz @ Ry @ Rx

def pose6_to_T(x, y, z, roll, pitch, yaw):
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = rpy_to_R(roll, pitch, yaw)
    T[:3, 3] = np.array([x, y, z], dtype=np.float64)
    return T

def R_to_quat(R):
    tr = np.trace(R)
    if tr > 0:
        S = math.sqrt(tr + 1.0) * 2
        w = 0.25 * S; x = (R[2,1]-R[1,2])/S; y = (R[0,2]-R[2,0])/S; z = (R[1,0]-R[0,1])/S
    elif R[0,0] > R[1,1] and R[0,0] > R[2,2]:
        S = math.sqrt(1+R[0,0]-R[1,1]-R[2,2])*2
        w = (R[2,1]-R[1,2])/S; x = 0.25*S; y = (R[0,1]+R[1,0])/S; z = (R[0,2]+R[2,0])/S
    elif R[1,1] > R[2,2]:
        S = math.sqrt(1+R[1,1]-R[0,0]-R[2,2])*2
        w = (R[0,2]-R[2,0])/S; x = (R[0,1]+R[1,0])/S; y = 0.25*S; z = (R[1,2]+R[2,1])/S
    else:
        S = math.sqrt(1+R[2,2]-R[0,0]-R[1,1])*2
        w = (R[1,0]-R[0,1])/S; x = (R[0,2]+R[2,0])/S; y = (R[1,2]+R[2,1])/S; z = 0.25*S
    q = np.array([w,x,y,z], dtype=np.float64)
    return q / (np.linalg.norm(q) + 1e-12)

def quat_to_R(q):
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]
    ], dtype=np.float64)

def slerp(q0, q1, a):
    q0 = q0/(np.linalg.norm(q0)+1e-12); q1 = q1/(np.linalg.norm(q1)+1e-12)
    d = float(np.dot(q0, q1))
    if d < 0: q1 = -q1; d = -d
    d = min(max(d, -1), 1)
    if d > 0.9995:
        q = q0 + a*(q1-q0); return q/(np.linalg.norm(q)+1e-12)
    t0 = math.acos(d); t = t0*a; st = math.sin(t0)
    q = (math.cos(t)-d*math.sin(t)/st)*q0 + (math.sin(t)/st)*q1
    return q/(np.linalg.norm(q)+1e-12)

def blend_T(T0, T1, a):
    q = slerp(R_to_quat(T0[:3,:3]), R_to_quat(T1[:3,:3]), a)
    t = (1-a)*T0[:3,3] + a*T1[:3,3]
    return build_T(quat_to_R(q), t)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def apply_deadzone(v, minimum, maximum):
    if abs(v) < 0.02: return 0.0
    if abs(v) < minimum: return math.copysign(minimum, v)
    return clamp(v, -maximum, maximum)


# ==============================================================================
#  RAW DDS PUBLISHER — sport API commands
# ==============================================================================

class DdsCommander:
    """Publishes raw commands to rt/api/sport/request."""

    def __init__(self):
        from unitree_sdk2py.core.channel import ChannelPublisher
        from unitree_sdk2py.idl.unitree_api.msg.dds_ import (
            Request_, RequestHeader_, RequestIdentity_,
            RequestLease_, RequestPolicy_,
        )
        self._pub = ChannelPublisher("rt/api/sport/request", Request_)
        self._pub.Init()
        self._msg_id = 0
        self._Request = Request_
        self._RequestHeader = RequestHeader_
        self._RequestIdentity = RequestIdentity_
        self._RequestLease = RequestLease_
        self._RequestPolicy = RequestPolicy_

    def send(self, api_id, params=None):
        self._msg_id += 1
        identity = self._RequestIdentity(id=self._msg_id, api_id=api_id)
        lease = self._RequestLease(id=0)
        policy = self._RequestPolicy(priority=0, noreply=True)
        header = self._RequestHeader(identity=identity, lease=lease, policy=policy)
        param_str = json.dumps(params) if params else "{}"
        req = self._Request(header=header, parameter=param_str, binary=[])
        self._pub.Write(req)

    def euler(self, roll, pitch, yaw):
        self.send(1007, {"x": roll, "y": pitch, "z": yaw})

    def move(self, vx, vy, vyaw):
        self.send(1008, {"x": vx, "y": vy, "z": vyaw})

    def pose_on(self):
        self.send(1028, {"data": True})

    def pose_off(self):
        self.send(1028, {"data": False})

    def stop_move(self):
        self.send(1003)

    def balance_stand(self):
        self.send(1002)


# ==============================================================================
#  DOG CAMERA — fisheye undistort + AprilTag detection (for docking)
# ==============================================================================

class DogUndistorter:
    def __init__(self):
        self.new_K = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
            DOG_K_FISHEYE, DOG_D_FISHEYE.reshape(4, 1),
            (DOG_IMG_W, DOG_IMG_H), np.eye(3), balance=0.0)
        self.map1, self.map2 = cv2.fisheye.initUndistortRectifyMap(
            DOG_K_FISHEYE, DOG_D_FISHEYE.reshape(4, 1), np.eye(3),
            self.new_K, (DOG_IMG_W, DOG_IMG_H), cv2.CV_16SC2)

    def undistort(self, img):
        return cv2.remap(img, self.map1, self.map2, cv2.INTER_LINEAR)

    def get_K(self):
        return self.new_K


class DogTagDetector:
    """Detects wall AprilTags. Parameterized by tag_id and tag_size."""

    def __init__(self, K_undist, tag_id, tag_size):
        from dt_apriltags import Detector
        self.detector = Detector(
            families=WALL_TAG_FAMILY, nthreads=4,
            quad_decimate=2.0, quad_sigma=0.0,
            decode_sharpening=0.25)
        self.cam_params = (K_undist[0,0], K_undist[1,1],
                           K_undist[0,2], K_undist[1,2])
        self.tag_id = tag_id
        self.tag_size = tag_size

    def detect(self, gray):
        results = self.detector.detect(
            gray, estimate_tag_pose=True,
            camera_params=self.cam_params, tag_size=self.tag_size)
        for r in results:
            if r.tag_id == self.tag_id:
                return {
                    "T_cam_tag": build_T(r.pose_R, r.pose_t.flatten()),
                    "distance": float(np.linalg.norm(r.pose_t)),
                }
        return None


# ==============================================================================
#  SHARED STATE (thread-safe, for docking)
# ==============================================================================

class SharedState:
    def __init__(self):
        self._lock = threading.Lock()
        self.odom_x = 0.0; self.odom_y = 0.0; self.odom_z = 0.0
        self.odom_yaw = 0.0; self.odom_t = 0.0; self.odom_valid = False
        self.tag_det = None; self.tag_t = 0.0

    def set_odom(self, x, y, z, yaw, t):
        with self._lock:
            self.odom_x = float(x); self.odom_y = float(y)
            self.odom_z = float(z); self.odom_yaw = wrap_pi(float(yaw))
            self.odom_t = t; self.odom_valid = True

    def get_odom(self):
        with self._lock:
            return (self.odom_x, self.odom_y, self.odom_z,
                    self.odom_yaw, self.odom_t, self.odom_valid)

    def get_T_odom_base(self):
        with self._lock:
            if not self.odom_valid: return None
            return T_from_xyyaw(self.odom_x, self.odom_y,
                                self.odom_yaw, self.odom_z)

    def set_tag(self, det, t):
        with self._lock:
            self.tag_det = det; self.tag_t = t

    def get_tag(self):
        with self._lock:
            return self.tag_det, self.tag_t

    def reset_tag(self):
        """Clear tag state for a fresh docking run."""
        with self._lock:
            self.tag_det = None; self.tag_t = 0.0


# ==============================================================================
#  DOG THREADS — odometry + vision
# ==============================================================================

def start_odom_subscriber(shared):
    from unitree_sdk2py.core.channel import ChannelSubscriber
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

    def cb(msg):
        try:
            shared.set_odom(
                float(msg.position[0]), float(msg.position[1]),
                float(msg.position[2]), float(msg.imu_state.rpy[2]),
                time.time())
        except Exception:
            pass

    sub = ChannelSubscriber("rt/sportmodestate", SportModeState_)
    sub.Init(cb, 10)
    return sub


def start_dog_vision_thread(shared, undistorter, detector, stop_event):
    from unitree_sdk2py.go2.video.video_client import VideoClient
    video = VideoClient(); video.SetTimeout(3.0); video.Init()

    def run():
        dt_min = 1.0 / DOG_CAM_FPS
        while not stop_event.is_set():
            t0 = time.time()
            try:
                code, data = video.GetImageSample()
                if code != 0 or data is None:
                    time.sleep(0.05); continue
                raw = cv2.imdecode(np.frombuffer(bytes(data), dtype=np.uint8),
                                   cv2.IMREAD_COLOR)
                if raw is None: continue
                gray = cv2.cvtColor(undistorter.undistort(raw), cv2.COLOR_BGR2GRAY)
                shared.set_tag(detector.detect(gray), time.time())
            except Exception as e:
                print(f"  [dog-vision] {e}"); time.sleep(0.1)
            sl = dt_min - (time.time() - t0)
            if sl > 0: time.sleep(sl)

    th = threading.Thread(target=run, daemon=True, name="dog-vision")
    th.start()
    return th


# ==============================================================================
#  DOCKING
# ==============================================================================

def compute_dock_errors(T_base_tag, target_dist):
    p = T_base_tag[:3, 3]; R = T_base_tag[:3, :3]
    px, py = p[0], p[1]
    pn = math.sqrt(px*px + py*py)
    if pn < 1e-6: return 0., 0., 0., -target_dist, 0.

    tz = R @ np.array([0., 0., 1.])
    nx, ny = tz[0], tz[1]; nn = math.sqrt(nx*nx + ny*ny)
    if nn < 1e-6:
        fwd = np.array([px, py]) / pn
    else:
        fwd = np.array([nx, ny]) / nn
        if np.dot(fwd, [px, py]) < 0: fwd = -fwd

    left = np.array([-fwd[1], fwd[0]])
    da = float(np.dot([px, py], fwd))
    la = float(np.dot([px, py], left))
    ye = wrap_pi(math.atan2(fwd[1], fwd[0]))
    return da, la, ye, da - target_dist, la


def run_docking(sport, shared, stop_event, label="dock"):
    """SEARCH → APPROACH → DONE. Returns True on success."""
    T_odom_tag_est = None; last_seen = -1e9
    conv_start = None; search_t0 = None; search_yaw0 = None
    state = "SEARCH"; dt = 1.0 / CONTROL_HZ

    print(f"\n  [{label}] State: SEARCH\n")

    while not stop_event.is_set():
        now = time.time()
        T_ob = shared.get_T_odom_base()
        ox, oy, oz, oyaw, ot, ov = shared.get_odom()
        td, tt = shared.get_tag()
        fresh = td is not None and (now - tt) < 0.5

        if fresh and T_ob is not None:
            Tbt_m = T_BASE_CAM @ td["T_cam_tag"]
            Tot_m = T_ob @ Tbt_m
            if T_odom_tag_est is None:
                T_odom_tag_est = Tot_m
                print(f"  [{label}][fusion] Tag estimate initialized.")
            else:
                T_odom_tag_est = blend_T(T_odom_tag_est, Tot_m, ALPHA_TAG)
            last_seen = now

        Tbt_pred = None; loss = now - last_seen
        if T_odom_tag_est is not None and T_ob is not None:
            Tbt_pred = inv_T(T_ob) @ T_odom_tag_est

        if state == "SEARCH":
            if search_t0 is None:
                search_t0 = now; search_yaw0 = oyaw if ov else 0.
            if Tbt_pred is not None and loss < 0.5:
                d = float(np.linalg.norm(Tbt_pred[:3, 3]))
                print(f"\n  [{label}] TAG FOUND! dist={d:.2f} m")
                sport.StopMove(); time.sleep(0.5)
                state = "APPROACH"; print(f"  [{label}] State: APPROACH\n")
            else:
                el = now - search_t0
                if el > SEARCH_TIMEOUT_S:
                    print(f"\n  [{label}] FAILED: timeout {SEARCH_TIMEOUT_S:.0f}s")
                    return False
                sport.Move(0., 0., SEARCH_VYAW)
                if ov:
                    r = abs(wrap_pi(oyaw - search_yaw0))
                    print(f"\r  [{label}] Search: {math.degrees(r):5.1f}° "
                          f"{el:.1f}s", end="", flush=True)

        elif state == "APPROACH":
            if loss > LONG_LOSS_S:
                print(f"\n  [{label}] Lost {loss:.1f}s → SEARCH")
                state = "SEARCH"; search_t0 = now
                search_yaw0 = oyaw if ov else 0.
                sport.StopMove(); time.sleep(0.3); continue
            if Tbt_pred is None:
                sport.StopMove(); time.sleep(dt); continue

            da, la, ye, ed, el2 = compute_dock_errors(Tbt_pred, TARGET_DIST_M)
            sc = 1.0
            if loss > SHORT_LOSS_S:   sc = 0.3
            elif loss > 0.3:          sc = 0.6

            yf = math.radians(YAW_FIRST_DEG)
            if abs(ye) > yf:
                vx = 0.; vy = 0.
                vyaw = apply_deadzone(K_YAW*ye, MIN_VYAW, MAX_VYAW)*sc
            else:
                vx = apply_deadzone(K_DIST*ed, MIN_VX, MAX_VX)*sc
                vy = apply_deadzone(K_LAT*el2, MIN_VY, MAX_VY)*sc
                vyaw = apply_deadzone(K_YAW*ye, MIN_VYAW, MAX_VYAW)*sc

            sport.Move(vx, vy, vyaw)

            tr = math.radians(TOL_YAW_DEG)
            ok = (abs(ed) < TOL_DIST_M and abs(el2) < TOL_LAT_M
                  and abs(ye) < tr and loss < 0.5)
            if ok:
                if conv_start is None: conv_start = now
                elif now - conv_start >= CONVERGE_TIME_S:
                    sport.StopMove(); time.sleep(0.5)
                    print(f"\n\n{'='*60}")
                    print(f"  [{label}] DOCKING COMPLETE!")
                    print(f"{'='*60}")
                    print(f"  Dist: {da:.3f} m (err {ed:+.3f})")
                    print(f"  Lat:  {la:+.3f} m")
                    print(f"  Yaw:  {math.degrees(ye):+.2f}°")
                    print(f"{'='*60}")
                    return True
            else:
                conv_start = None

            step = int(now * CONTROL_HZ)
            if step % CONTROL_HZ == 0:
                vs = "VIS" if loss < 0.3 else f"P{loss:.1f}s"
                print(f"  [{label}] [{vs:>7s}] d={da:.2f}(e={ed:+.03f}) "
                      f"l={la:+.03f} y={math.degrees(ye):+.1f}° "
                      f"vx={vx:+.2f} vy={vy:+.2f} vyaw={vyaw:+.2f}"
                      f"{'  CONV' if ok else ''}")

        sl = dt - (time.time() - now)
        if sl > 0: time.sleep(sl)

    return False


# ==============================================================================
#  PITCH CONTROL THREAD
# ==============================================================================

def start_pitch_thread(dds_cmd, stop_event):
    dt = 1.0 / PITCH_HZ

    def run():
        print(f"  [pitch] Sending Pose(true) ...")
        dds_cmd.pose_on()
        time.sleep(0.5)

        print(f"  [pitch] Continuous Euler: {PITCH_DEG:.1f}° ({PITCH_RAD:.4f} rad) @ {PITCH_HZ} Hz")
        while not stop_event.is_set():
            t0 = time.time()
            try:
                dds_cmd.euler(0.0, PITCH_RAD, 0.0)
            except Exception as e:
                print(f"  [pitch] Euler error: {e}")
            sl = dt - (time.time() - t0)
            if sl > 0: time.sleep(sl)
        print("  [pitch] Thread stopped.")

    th = threading.Thread(target=run, daemon=True, name="pitch-ctrl")
    th.start()
    return th


# ==============================================================================
#  ARM VISION: AprilTag detection — from dock_robot_server.py
# ==============================================================================

def _aruco_make_detector():
    dict_id = cv2.aruco.DICT_APRILTAG_36h11

    if hasattr(cv2.aruco, "getPredefinedDictionary"):
        aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
    else:
        aruco_dict = cv2.aruco.Dictionary_get(dict_id)

    if hasattr(cv2.aruco, "DetectorParameters"):
        params = cv2.aruco.DetectorParameters()
    else:
        params = cv2.aruco.DetectorParameters_create()

    if hasattr(params, "cornerRefinementMethod"):
        try:
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        except Exception:
            pass

    detector = None
    if hasattr(cv2.aruco, "ArucoDetector"):
        detector = cv2.aruco.ArucoDetector(aruco_dict, params)

    return aruco_dict, params, detector

ARUCO_DICT, ARUCO_PARAMS, ARUCO_DETECTOR = _aruco_make_detector()


def detect_apriltag(gray, K_use, D_use):
    """Returns (ok, corners, rvec, tvec). solvePnP gives tag→camera."""
    if ARUCO_DETECTOR is not None:
        corners_list, ids, _ = ARUCO_DETECTOR.detectMarkers(gray)
    else:
        corners_list, ids, _ = cv2.aruco.detectMarkers(
            gray, ARUCO_DICT, parameters=ARUCO_PARAMS)

    if ids is None:
        return False, None, None, None

    ids = ids.flatten()
    if TAG_ID not in ids:
        return False, None, None, None

    idx = int(np.where(ids == TAG_ID)[0][0])
    corners = corners_list[idx].reshape(4, 2).astype(np.float64)

    s = TAG_SIZE_M / 2.0
    obj_pts = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]],
                        dtype=np.float64)

    ok, rvec, tvec = cv2.solvePnP(
        obj_pts, corners, K_use, D_use, flags=cv2.SOLVEPNP_IPPE_SQUARE)
    if not ok:
        return False, corners, None, None

    tz = float(tvec.reshape(-1)[2])
    if tz <= 0:
        return False, corners, None, None

    return True, corners, rvec, tvec


def draw_debug(frame_bgr, corners, rvec, tvec, K_use, D_use, out_path):
    try:
        vis = frame_bgr.copy()
        if corners is not None:
            cv2.polylines(vis, [corners.astype(np.int32)], True, (0, 255, 0), 2)
        if rvec is not None and tvec is not None:
            cv2.drawFrameAxes(vis, K_use, D_use, rvec, tvec, 0.05)
        cv2.imwrite(out_path, vis)
        print(f"  [debug] Saved: {out_path}")
    except Exception as e:
        print(f"  [debug] Save error: {e}")


# ==============================================================================
#  ARM CAMERA
# ==============================================================================

class ArmCamera:
    def __init__(self):
        pipeline = (
            f"v4l2src device={CAM_DEVICE} ! "
            f"image/jpeg,width={CAM_W},height={CAM_H},framerate=30/1 ! "
            f"jpegdec ! videoconvert ! "
            f"video/x-raw,format=BGR ! appsink"
        )
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self.cap.isOpened():
            print("  [arm-cam] GStreamer failed, trying V4L2 ...")
            self.cap = cv2.VideoCapture(CAM_DEVICE)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open arm camera {CAM_DEVICE}")
        for _ in range(5):
            self.cap.read(); time.sleep(0.05)
        print(f"  [arm-cam] Opened {CAM_DEVICE} @ {CAM_W}×{CAM_H}")

    def grab(self):
        ret, frame = self.cap.read()
        return frame if ret else None

    def wait_for_frame(self, timeout_s=2.0):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            f = self.grab()
            if f is not None: return f
            time.sleep(0.01)
        return None

    def release(self):
        self.cap.release()


# ==============================================================================
#  ROBOT CONTROLLER — from dock_robot_server.py
# ==============================================================================

class RobotController:
    def __init__(self):
        from interbotix_xs_modules.arm import InterbotixManipulatorXS
        self.bot = InterbotixManipulatorXS(
            robot_model=ARM_ROBOT_MODEL,
            group_name="arm",
            gripper_name="gripper",
        )
        self.bot.arm.set_trajectory_time(
            moving_time=MOVING_TIME, accel_time=ACCEL_TIME)
        try:
            self.bot.gripper.set_pressure(0.5)
        except Exception:
            pass
        self.grip_is_open = None
        self.lock = threading.Lock()
        print(f"  [arm] Initialized {ARM_ROBOT_MODEL}")

    # ── Gripper ──

    def grip_open(self):
        print("  [arm] Gripper OPEN")
        g = self.bot.gripper
        if hasattr(g, "release"):
            try: g.release(2.0)
            except TypeError: g.release()
        elif hasattr(g, "open"):
            try: g.open()
            except TypeError: g.open(2.0)
        else:
            raise AttributeError("Gripper has no release() or open()")
        self.grip_is_open = True

    def grip_close(self):
        print("  [arm] Gripper CLOSE")
        g = self.bot.gripper
        if hasattr(g, "grasp"):
            try: g.grasp(2.0)
            except TypeError: g.grasp()
        elif hasattr(g, "close"):
            try: g.close()
            except TypeError: g.close(2.0)
        else:
            raise AttributeError("Gripper has no grasp() or close()")
        self.grip_is_open = False

    # ── EE pose ──

    def get_T_base_ee(self):
        pose = self.bot.arm.get_ee_pose()
        arr = np.array(pose, dtype=np.float64)
        if arr.shape == (4, 4):
            return arr
        if arr.size == 6:
            x, y, z, r, p, yw = arr.reshape(-1).tolist()
            return pose6_to_T(x, y, z, r, p, yw)
        raise RuntimeError(f"Unexpected get_ee_pose() shape: {arr.shape}")

    def _get_joints(self):
        q = self.bot.arm.get_joint_commands()
        if q is None or len(q) == 0:
            q = self.bot.arm.get_joint_positions()
        return np.array(q, dtype=float)

    # ── Motion ──

    def home(self):
        with self.lock:
            print("  [arm] → HOME")
            self.bot.arm.go_to_home_pose()
            time.sleep(SETTLE_S)

    def sleep(self):
        with self.lock:
            print("  [arm] → SLEEP")
            self.bot.arm.go_to_sleep_pose()
            time.sleep(SETTLE_S)

    def preset(self, idx):
        if idx not in PRESETS_DEG:
            print(f"  [arm] ERROR: unknown preset {idx}")
            return
        with self.lock:
            q = np.deg2rad(np.array(PRESETS_DEG[idx], dtype=float))
            print(f"  [arm] → PRESET {idx}: {PRESETS_DEG[idx]} deg")
            self.bot.arm.set_joint_positions(q.tolist(), blocking=True)
            time.sleep(SETTLE_S)

    # ── IK ──

    def set_ee_pose_checked(self, x, y, z, roll, pitch, label=""):
        ret = self.bot.arm.set_ee_pose_components(
            x=x, y=y, z=z, roll=roll, pitch=pitch)
        ok = True
        if isinstance(ret, bool):
            ok = ret
        elif isinstance(ret, (list, tuple)) and len(ret) > 0 and isinstance(ret[0], bool):
            ok = ret[0]
        if not ok:
            print(f"  [arm] IK FAIL at {label}: x={x:+.3f} y={y:+.3f} "
                  f"z={z:+.3f} roll={roll:+.3f} pitch={pitch:+.3f}")
        return ok


# ==============================================================================
#  GRASP — from dock_robot_server._grasp_worker
# ==============================================================================

def run_grasp(robot, cam):
    """
    Detect ground tag → compute pose → hover → descend → close → lift.
    Returns True if grasp succeeded.
    """
    os.makedirs(DEBUG_DIR, exist_ok=True)

    print("\n  [grasp] ====== GRASP START ======")
    print(f"  [grasp] Looking for tag ID {TAG_ID}, size {TAG_SIZE_M*1000:.0f} mm")

    # ── Detect ──
    ok = False
    corners = rvec = tvec = None
    frame = None

    for i in range(GRASP_DETECT_TRIES):
        frame = cam.wait_for_frame(timeout_s=0.5)
        if frame is None:
            continue
        if frame.shape[1] != CAM_W or frame.shape[0] != CAM_H:
            print(f"  [grasp] ERROR: frame {frame.shape[1]}x{frame.shape[0]} "
                  f"but expected {CAM_W}x{CAM_H}")
            return False

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        ok, corners, rvec, tvec = detect_apriltag(gray, K, DIST)
        if ok:
            print(f"  [grasp] Tag detected on attempt {i+1}!")
            break
        time.sleep(GRASP_DETECT_SLEEP_S)

    if not ok:
        print("  [grasp] ERROR: Tag not detected after retries.")
        if DEBUG_SAVE_IMAGES and frame is not None:
            outp = os.path.join(DEBUG_DIR, f"no_tag_{int(time.time())}.jpg")
            cv2.imwrite(outp, frame)
        return False

    dist = float(np.linalg.norm(tvec))
    print(f"  [grasp] Camera distance ~ {dist:.3f} m")

    if DEBUG_SAVE_IMAGES:
        outp = os.path.join(DEBUG_DIR, f"tag_detect_{int(time.time())}.jpg")
        draw_debug(frame, corners, rvec, tvec, K, DIST, outp)

    # ── Compute grasp pose ──

    T_base_ee = robot.get_T_base_ee()
    T_cam_tag = rvec_tvec_to_T(rvec, tvec)

    # T_base_tag = T_base_ee * T_ee_cam * T_cam_tag
    T_base_tag = T_base_ee @ T_ee_cam @ T_cam_tag

    tag_x = float(T_base_tag[0, 3])
    tag_y = float(T_base_tag[1, 3])
    tag_z = float(T_base_tag[2, 3])
    print(f"  [grasp] Tag in base: X={tag_x:+.4f} Y={tag_y:+.4f} Z={tag_z:+.4f}")

    # Cup offset in tag frame
    T_tag_cup = np.eye(4, dtype=np.float64)
    T_tag_cup[0, 3] = CUP_OFFSET_X
    T_tag_cup[1, 3] = CUP_OFFSET_Y
    T_tag_cup[2, 3] = CUP_OFFSET_Z

    T_base_cup = T_base_tag @ T_tag_cup
    cup_x = float(T_base_cup[0, 3])
    cup_y = float(T_base_cup[1, 3])
    cup_z = float(T_base_cup[2, 3])
    print(f"  [grasp] Cup in base: X={cup_x:+.4f} Y={cup_y:+.4f} Z={cup_z:+.4f}")

    # ── Sanity gates ──
    r_xy = float(np.hypot(cup_x, cup_y))
    if r_xy > MAX_R_XY_M or r_xy < MIN_R_XY_M:
        print(f"  [grasp] ERROR: Cup out of reach (r={r_xy:.2f} m). Aborting.")
        return False
    if cup_z < MIN_CUP_Z_M:
        print(f"  [grasp] ERROR: cup_z too low ({cup_z:.3f} m). Aborting.")
        return False
    print(f"  [grasp] Sanity OK: r_xy={r_xy:.3f}, z={cup_z:.3f}")

    # ── Hover & grasp ──
    hover_x, hover_y, hover_z = cup_x, cup_y, cup_z + HOVER_DISTANCE_M

    with robot.lock:
        print("  [grasp] Opening gripper ...")
        robot.grip_open()
        time.sleep(0.3)

        print(f"  [grasp] Move to hover ({hover_x:+.3f}, {hover_y:+.3f}, {hover_z:+.3f}) ...")
        if not robot.set_ee_pose_checked(hover_x, hover_y, hover_z,
                                          FIXED_ROLL, FIXED_PITCH, "HOVER"):
            print("  [grasp] Aborting: IK failed at hover.")
            return False
        time.sleep(MOVING_TIME + 0.2)

        print(f"  [grasp] Descend to cup ({cup_x:+.3f}, {cup_y:+.3f}, {cup_z:+.3f}) ...")
        if not robot.set_ee_pose_checked(cup_x, cup_y, cup_z,
                                          FIXED_ROLL, FIXED_PITCH, "DESCEND"):
            print("  [grasp] Aborting: IK failed at descend.")
            return False
        time.sleep(MOVING_TIME + 0.2)

        print("  [grasp] Close gripper ...")
        robot.grip_close()
        time.sleep(0.6)

        print(f"  [grasp] Lift to ({hover_x:+.3f}, {hover_y:+.3f}, {hover_z:+.3f}) ...")
        if not robot.set_ee_pose_checked(hover_x, hover_y, hover_z,
                                          FIXED_ROLL, FIXED_PITCH, "LIFT"):
            print("  [grasp] Warning: IK failure during lift.")
        time.sleep(MOVING_TIME + 0.2)

        # Return to preset (holding object)
        if RETURN_PRESET_AFTER_GRASP is not None:
            if RETURN_PRESET_AFTER_GRASP in PRESETS_DEG:
                print(f"  [grasp] Return to PRESET {RETURN_PRESET_AFTER_GRASP} (holding object) ...")
                q = np.deg2rad(np.array(PRESETS_DEG[RETURN_PRESET_AFTER_GRASP], dtype=float))
                robot.bot.arm.set_joint_positions(q.tolist(), blocking=True)
                time.sleep(SETTLE_S)

    print("  [grasp] ====== GRASP DONE ======\n")
    return True


# ==============================================================================
#  MAIN
# ==============================================================================

def main():
    global PITCH_DEG, PITCH_RAD

    parser = argparse.ArgumentParser(description="Go2 + wx250 Dock, Grasp & Deliver")
    parser.add_argument("--iface", default=DDS_IFACE)
    parser.add_argument("--pitch-deg", type=float, default=PITCH_DEG)
    parser.add_argument("--skip-dock", action="store_true")
    args = parser.parse_args()

    PITCH_DEG = args.pitch_deg
    PITCH_RAD = math.radians(PITCH_DEG)

    print("=" * 60)
    print("  Go2 + wx250 — Autonomous Dock, Grasp & Deliver")
    print("=" * 60)
    print(f"  DDS iface     : {args.iface}")
    print(f"  Pickup tag    : {WALL_TAG_FAMILY} ID {PICKUP_TAG_ID}, "
          f"{PICKUP_TAG_SIZE*1000:.0f} mm")
    print(f"  Delivery tag  : {WALL_TAG_FAMILY} ID {DELIVERY_TAG_ID}, "
          f"{DELIVERY_TAG_SIZE*1000:.0f} mm")
    print(f"  Ground tag    : ID {TAG_ID}, {TAG_SIZE_M*1000:.0f} mm")
    print(f"  Target dist   : {TARGET_DIST_M} m")
    print(f"  Pitch         : {PITCH_DEG:.1f}° ({PITCH_RAD:.4f} rad)")
    print(f"  Debug dir     : {DEBUG_DIR}")
    print()

    # ── Init DDS ──
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.go2.sport.sport_client import SportClient

    ChannelFactoryInitialize(0, args.iface)

    sport = SportClient()
    sport.SetTimeout(10.0)
    sport.Init()

    dds_cmd = DdsCommander()

    # Motion switcher
    try:
        from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import (
            MotionSwitcherClient)
        msc = MotionSwitcherClient()
        msc.SetTimeout(5.0); msc.Init()
        c, _ = msc.SelectMode("normal")
        print(f"  Sport mode: {'active' if c in (0, 7004) else f'code={c}'}")
    except Exception:
        print("  MotionSwitcher unavailable — assuming sport mode.")
    time.sleep(1)

    try: sport.BalanceStand()
    except: pass
    time.sleep(1)

    global_stop = threading.Event()

    def safe_stop():
        try:
            sport.StopMove(); time.sleep(0.3)
            sport.BalanceStand()
        except: pass

    def on_sigint(sig, frame):
        print("\n  SIGINT — emergency stop.")
        global_stop.set(); safe_stop(); sys.exit(0)
    signal.signal(signal.SIGINT, on_sigint)

    # ================================================================
    #  PHASE 1: ARM INIT
    # ================================================================
    print("\n" + "=" * 60)
    print("  PHASE 1: ARM INIT")
    print("=" * 60)

    try:
        robot = RobotController()
    except Exception as e:
        print(f"  [arm] FAILED to initialize: {e}")
        safe_stop(); return

    robot.grip_open()
    robot.home()
    robot.sleep()
    print("  [arm] Ready (sleep position, gripper open).\n")

    # ── Shared state + odom (used for both docking phases) ──
    shared = SharedState()
    _odom_sub = start_odom_subscriber(shared)

    waited = 0.0
    while waited < 5.0:
        if shared.get_odom()[5]: break
        time.sleep(0.1); waited += 0.1

    x, y, z, yaw, _, v = shared.get_odom()
    if v:
        print(f"  Odom: ({x:.3f},{y:.3f},{z:.3f}) yaw={math.degrees(yaw):.1f}°")

    undistorter = DogUndistorter()
    print(f"  Dog camera K: fx={undistorter.get_K()[0,0]:.1f} "
          f"fy={undistorter.get_K()[1,1]:.1f}")

    # ================================================================
    #  PHASE 2: DOCK TAG 0 (pickup location)
    # ================================================================
    if not args.skip_dock:
        print("\n" + "=" * 60)
        print(f"  PHASE 2: DOCK — search & approach tag ID {PICKUP_TAG_ID}")
        print("=" * 60)

        detector_0 = DogTagDetector(undistorter.get_K(),
                                     PICKUP_TAG_ID, PICKUP_TAG_SIZE)
        shared.reset_tag()

        vision_stop = threading.Event()
        _vis_th = start_dog_vision_thread(shared, undistorter, detector_0,
                                          vision_stop)
        time.sleep(1.0)

        dock_ok = run_docking(sport, shared, global_stop, label="dock-0")
        vision_stop.set()

        if not dock_ok:
            print("\n  DOCKING FAILED — aborting.")
            safe_stop(); return
    else:
        print("  [dock] SKIPPED (--skip-dock)\n")

    # ================================================================
    #  PHASE 3: PITCH DOWN
    # ================================================================
    print("\n" + "=" * 60)
    print("  PHASE 3: PITCH DOWN — continuous Euler control")
    print("=" * 60)

    sport.StopMove()
    time.sleep(0.5)

    pitch_stop = threading.Event()
    _pitch_th = start_pitch_thread(dds_cmd, pitch_stop)

    print(f"  [pitch] Waiting {PITCH_SETTLE_S:.1f}s to stabilize ...")
    time.sleep(PITCH_SETTLE_S)
    print("  [pitch] Robot pitched. Proceeding with arm.\n")

    # ================================================================
    #  PHASE 4: ARM → HOME → PRESET 2
    # ================================================================
    print("=" * 60)
    print("  PHASE 4: ARM TO PRESET 2 (looking-down position)")
    print("=" * 60)

    robot.home()
    robot.preset(2)
    # time.sleep(1.0)
    print("  [arm] At preset 2.\n")

    # ================================================================
    #  PHASE 5: GRASP
    # ================================================================
    print("=" * 60)
    print("  PHASE 5: GRASP")
    print("=" * 60)

    try:
        arm_cam = ArmCamera()
    except Exception as e:
        print(f"  [arm-cam] FAILED: {e}")
        robot.preset(2)
        pitch_stop.set(); time.sleep(2.0)
        safe_stop(); return

    time.sleep(1.0)

    grasp_ok = run_grasp(robot, arm_cam)
    arm_cam.release()

    if not grasp_ok:
        print("\n  [grasp] FAILED — returning arm to preset 2.")
        robot.preset(RETURN_PRESET_AFTER_GRASP)

    # ================================================================
    #  PHASE 6: ARM RETURN (already done inside run_grasp if successful)
    # ================================================================
    print("\n" + "=" * 60)
    print("  PHASE 6: ARM RETURN")
    print("=" * 60)
    print(f"  [arm] At preset {RETURN_PRESET_AFTER_GRASP}.\n")

    # ================================================================
    #  PHASE 7: PITCH UP
    # ================================================================
    print("=" * 60)
    print("  PHASE 7: PITCH UP — return to normal stance")
    print("=" * 60)

    pitch_stop.set()
    time.sleep(1.0)

    dds_cmd.euler(0.0, 0.0, 0.0)
    time.sleep(0.5)
    dds_cmd.pose_off()
    time.sleep(0.5)
    dds_cmd.balance_stand()
    time.sleep(0.5)
    # Move(0,0,0) forces the sport state machine back into locomotion mode
    sport.Move(0.0, 0.0, 0.0)
    time.sleep(0.5)
    sport.StopMove()
    time.sleep(0.5)

    print("  [pitch] Robot upright — locomotion mode restored.\n")

    if not grasp_ok:
        print("=" * 60)
        print("  MISSION ENDED — grasp failed, skipping delivery.")
        print("=" * 60)
        safe_stop(); return

    # ================================================================
    #  PHASE 8: DOCK TAG 1 (delivery location)
    # ================================================================
    print("=" * 60)
    print(f"  PHASE 8: DOCK — search & approach tag ID {DELIVERY_TAG_ID}")
    print("=" * 60)

    # new arm position
    robot.preset(3)

    # Need locomotion mode for walking — already restored in Phase 7
    detector_1 = DogTagDetector(undistorter.get_K(),
                                 DELIVERY_TAG_ID, DELIVERY_TAG_SIZE)
    shared.reset_tag()

    vision_stop_2 = threading.Event()
    _vis_th_2 = start_dog_vision_thread(shared, undistorter, detector_1,
                                         vision_stop_2)
    time.sleep(1.0)

    dock2_ok = run_docking(sport, shared, global_stop, label="dock-1")
    vision_stop_2.set()

    if not dock2_ok:
        print("\n  DELIVERY DOCK FAILED.")
        safe_stop(); return

    # ================================================================
    #  PHASE 9: DELIVER — home → open gripper → sleep
    # ================================================================
    print("\n" + "=" * 60)
    print("  PHASE 9: DELIVER — release object")
    print("=" * 60)

    sport.StopMove()
    time.sleep(0.5)

    robot.home()
    robot.preset(4)
    time.sleep(0.2)
    robot.grip_open()
    time.sleep(0.2)
    robot.sleep()
    time.sleep(0.2)

    print("  [arm] Object released. Arm in sleep.\n")

    # ================================================================
    #  DONE
    # ================================================================
    print("=" * 60)
    print("  MISSION COMPLETE — object picked up and delivered!")
    print("=" * 60)


if __name__ == "__main__":
    print("WARNING: Ensure area around robot is clear.")
    print("         Arm will move. Keep hands away.")
    input("Press Enter to start ...")
    main()