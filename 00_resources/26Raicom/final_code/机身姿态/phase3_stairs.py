#!/usr/bin/env python3
"""
Go2 Phase 3 巡线 + 台阶程序（从 phase1_only1.py 提取）
=====================================================
状态机: CENTER_1 → LINE_TRACK → STAIRS_UP → TURN_LEFT → STAIRS_DOWN → CENTER_2 → DONE
  1. CENTER_1  — 初始居中校准（横向平移对齐黑线）
  2. LINE_TRACK — PID 巡线 + 检测大面积黑色区域触发台阶
  3. STAIRS_UP  — ClassicWalk 直走上台阶（纯延时）
  4. TURN_LEFT  — 台阶上原地左转（IMU 闭环）
  5. STAIRS_DOWN— ClassicWalk 直走下台阶（纯延时）
  6. CENTER_2  — 二次居中：先强制右移搜索黑线，再横向对齐

用法:
  python3 phase3_stairs.py <networkInterface>
  python3 phase3_stairs.py eth0
"""

import sys
import os
import time
import math
import threading
import signal
import subprocess
import re

import cv2
import numpy as np

from unitree_sdk2py.core.channel import (
    ChannelFactoryInitialize,
    ChannelPublisher,
    ChannelSubscriber,
)
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
from unitree_sdk2py.go2.sport.sport_client import SportClient
from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import (
    MotionSwitcherClient,
)


# ============================================================
# 网络接口自动检测
# ============================================================
def auto_detect_interface():
    """自动检测连接 Go2 机器人的网络接口"""
    go2_subnet = "192.168.123."
    candidates = []
    try:
        result = subprocess.run(
            ["ip", "-o", "addr", "show"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            iface = parts[1]
            if iface == "lo" or iface.startswith("docker") or iface == "l4tbr0":
                continue
            inet_match = re.search(r'inet\s+([\d.]+)', line)
            if inet_match:
                ip = inet_match.group(1)
                if ip.startswith(go2_subnet):
                    print(f"[AUTO] Go2 网络接口: {iface} ({ip})")
                    return iface
                candidates.append((iface, ip))
    except Exception:
        pass
    try:
        for iface in sorted(os.listdir("/sys/class/net")):
            if iface == "lo" or iface.startswith("docker"):
                continue
            operstate_file = f"/sys/class/net/{iface}/operstate"
            carrier_file = f"/sys/class/net/{iface}/carrier"
            if os.path.exists(operstate_file):
                with open(operstate_file) as f:
                    if f.read().strip() != "up":
                        continue
            if os.path.exists(carrier_file):
                with open(carrier_file) as f:
                    if f.read().strip() != "1":
                        continue
            addr_path = f"/sys/class/net/{iface}/address"
            if os.path.exists(addr_path):
                print(f"[AUTO] 活动接口: {iface}")
                return iface
    except Exception:
        pass
    if candidates:
        iface, ip = candidates[0]
        print(f"[AUTO] 备选接口: {iface} ({ip})")
        return iface
    return None


# ============================================================
# DDS Topic
# ============================================================
TOPIC_HIGHSTATE = "rt/sportmodestate"


# ============================================================
# 🔧 可调参数汇总 🔧
# ============================================================

# ── 摄像头参数 ──
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FPS = 30
CAMERA_EXPOSURE = 50

# ── 控制参数 ──
CTRL_HZ = 100
CTRL_DT = 1.0 / CTRL_HZ


# ================================================================
#  Phase 3 — 巡线 + 黑区检测 → 直走 + 左转 + 直走 (全部经典模式)
# ================================================================

# --- 黑线检测 ---
P3_BLACK_THRESHOLD = 130    # 黑线二值化阈值
P3_MIN_AREA = 150.0         # 最小轮廓面积

# --- PID 巡线控制 ---
P3_PID_KP = 0.70
P3_PID_KI = 0.04
P3_PID_KD = 0.08
P3_PID_MAX_YAW = 2.0
P3_PID_INTEGRAL_MAX = 1.5

# --- 巡线速度 ---
P3_BASE_SPEED = 0.19        # 基础前进速度 (m/s)

# --- 循线偏移偏置 (正值=黑线偏左, 负值=黑线偏右) ---
P3_TRACK_OFFSET_BIAS = 0.00   # 0=对中循线, 正值=黑线偏左

# --- 初始居中 ---
P3_CENTER_THRESHOLD = 0.12
P3_CENTER_CONFIRM_FRAMES = 6
P3_CENTER_TIMEOUT = 2.0       # 居中超时 (秒), 超时后强制进入下一步
P3_CENTER_LATERAL_KP = 0.50
P3_CENTER_LATERAL_MAX = 0.25
# --- 二次居中 (下台阶后旋转搜索黑线) ---
P3_CENTER2_ROTATE_SPEED = 0.5       # 搜索旋转角速度 (rad/s)
P3_CENTER2_LEFT_MAX_DEG = 8         # 左旋搜索最大角度 (度)
P3_CENTER2_RIGHT_MAX_DEG = 16       # 右旋搜索最大角度 (度, 从左极限向右扫)

# --- 黑区检测 (触发上台阶) ---
P3_BLACK_RATIO_THRESHOLD = 0.80
P3_BLACK_CONFIRM_FRAMES = 3

# --- 偏航角记录 ---
P3_YAW_SAMPLE_COUNT = 30       # 对中后记录偏航角采样数
P3_YAW_SAMPLE_DELAY = 0.1     # 每次采样间隔 (秒)

# --- 台阶动作 (IMU 姿态闭环) ---
P3_STAIRS_FAST_SPEED = 0.42     # 上台阶快速段速度 (m/s)
P3_STAIRS_SLOW_SPEED = 0.15    # 俯仰回零时减速 (m/s)
P3_STAIRS_YAW_KP = 1.5         # 上台阶偏航纠偏 P 系数
P3_STAIRS_YAW_MAX = 1.0        # 偏航纠偏最大角速度 (rad/s)
P3_PITCH_CLIMBING_THRESH = math.radians(24)    # 俯仰偏离阈值 (rad), 超过=正在爬升
P3_PITCH_RETURN_THRESH = math.radians(20)      # 俯仰回零减速阈值 (rad)
P3_PITCH_STOP_THRESH = math.radians(9.9)      # 俯仰归零停止阈值 (rad)
# --- 台阶顶部微调 (左转前) ---
P3_TOP_STRAFE_LEFT_DUR = 0.3    # 左平移时长 (秒)
P3_TOP_STRAFE_LEFT_SPEED = 0.2  # 左平移速度 (m/s, 正=左)
P3_TOP_BACK_DUR = 0.5           # 后退时长 (秒)
P3_TOP_BACK_SPEED = 0.2         # 后退速度 (m/s, 正=前, 负=后)

# --- 左转 ---
P3_TURN_ANGLE_DEG = 82
P3_TURN_SPEED = 1.6
P3_STAIRS_DOWN_DUR = 2.3      # 下台阶时长
P3_STAIRS_DOWN_SPEED = 0.66


# ================================================================
#  Phase 3 状态常量
# ================================================================
P3S_CENTER_1 = 0        # 初始居中
P3S_LINE_TRACK = 1      # PID 巡线 + 偏航角采样 + 黑色占比检测
P3S_STAIRS_UP = 2       # 上台阶 (俯仰闭环 + 偏航纠偏)
P3S_TURN_LEFT = 3       # 左转 (IMU 闭环)
P3S_STAIRS_DOWN = 4     # 下台阶 (纯延时)
P3S_CENTER_2 = 5        # 二次居中
P3S_DONE = 6            # 完成


# ============================================================
# PID 控制器
# ============================================================
class PIDController:
    """离散 PID 控制器，带积分抗饱和与输出限幅"""

    def __init__(self, kp, ki, kd, output_min, output_max,
                 integral_min=-1.0, integral_max=1.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_min = output_min
        self.output_max = output_max
        self.integral_min = integral_min
        self.integral_max = integral_max
        self.reset()

    def reset(self, initial_error=0.0):
        self._prev_error = initial_error
        self._integral = 0.0

    def update(self, error, dt):
        if dt <= 0.0 or dt > 0.5:
            dt = 0.02
        self._integral += 0.5 * (error + self._prev_error) * dt
        if self._integral > self.integral_max:
            self._integral = self.integral_max
        elif self._integral < self.integral_min:
            self._integral = self.integral_min
        derivative = (error - self._prev_error) / dt
        self._prev_error = error
        output = (self.kp * error +
                  self.ki * self._integral +
                  self.kd * derivative)
        if output > self.output_max:
            output = self.output_max
            self._integral -= self.ki * error * dt * 0.5
        elif output < self.output_min:
            output = self.output_min
            self._integral -= self.ki * error * dt * 0.5
        return output


# ============================================================
# 黑线检测器
# ============================================================
class LineDetector:
    """黑线检测 + 黑色占比"""

    def __init__(self, black_threshold=80, min_area=200.0, min_width=0):
        self.black_threshold = black_threshold
        self.min_area = min_area
        self.min_width = min_width
        self.avg_area = 800.0

    def detect(self, gray_frame):
        """检测黑线，返回 (found, offset, cx, cy, area,
           touches_left, touches_right, significant_count)"""
        h, w = gray_frame.shape
        img_center_x = w // 2
        blurred = cv2.GaussianBlur(gray_frame, (5, 5), 0)
        _, binary = cv2.threshold(blurred, self.black_threshold, 255,
                                   cv2.THRESH_BINARY_INV)
        roi_top = h * 2 // 3
        roi = binary[roi_top:h, :]
        contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        found = False
        best_cx = 0
        best_cy = 0
        largest_area = 0.0
        touches_left = False
        touches_right = False
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self.min_width > 0:
                _x, _y, bw, _bh = cv2.boundingRect(cnt)
                if bw < self.min_width:
                    continue
            if area > largest_area and area > self.min_area:
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    largest_area = area
                    best_cx = int(M["m10"] / M["m00"])
                    best_cy = int(M["m01"] / M["m00"]) + roi_top
                    found = True
                    for pt in cnt:
                        if pt[0][0] <= 2:
                            touches_left = True
                        if pt[0][0] >= w - 3:
                            touches_right = True
        significant_count = sum(1 for cnt in contours
                                if cv2.contourArea(cnt) > 300)
        if found:
            offset = float(img_center_x - best_cx) / img_center_x
            self.avg_area = self.avg_area * 0.85 + largest_area * 0.15
        else:
            offset = 0.0
        return (found, offset, best_cx, best_cy, largest_area,
                touches_left, touches_right, significant_count)

    def get_black_ratio(self, gray_frame):
        """计算画面中黑色像素占比"""
        h, w = gray_frame.shape
        _, binary = cv2.threshold(gray_frame, self.black_threshold, 255,
                                   cv2.THRESH_BINARY_INV)
        black_pixels = cv2.countNonZero(binary)
        ratio = black_pixels / binary.size
        return ratio


# ============================================================
# Phase 3 主控类
# ============================================================
class Phase3Mission:
    """Go2 Phase 3: 巡线 + 黑区检测 → 上台阶 → 左转 → 下台阶 → 二次居中"""

    def __init__(self, network_interface=""):
        # ---- 共享命令 ----
        self._cmd_lock = threading.Lock()
        self._target_vx = 0.0
        self._target_vy = 0.0
        self._target_vyaw = 0.0

        # ---- 机器人状态 ----
        self._robot_state = None
        self._robot_state_lock = threading.Lock()

        # ---- 运行标志 ----
        self._running = True
        self._control_running = True
        self._init_done = False

        # ---- 检测器与 PID ----
        self._detector = LineDetector(
            black_threshold=P3_BLACK_THRESHOLD,
            min_area=P3_MIN_AREA,
        )
        self._pid = PIDController(
            kp=P3_PID_KP, ki=P3_PID_KI, kd=P3_PID_KD,
            output_min=-P3_PID_MAX_YAW, output_max=P3_PID_MAX_YAW,
            integral_min=-P3_PID_INTEGRAL_MAX, integral_max=P3_PID_INTEGRAL_MAX,
        )

        # ---- 摄像头 ----
        self._cap = None
        self._camera_on = False

        # ---- DDS 初始化 ----
        print("[INIT] 初始化 ChannelFactory...")
        if network_interface:
            ChannelFactoryInitialize(0, network_interface)
        else:
            ChannelFactoryInitialize(0)

        self._msc = MotionSwitcherClient()
        self._msc.SetTimeout(5.0)
        self._msc.Init()

        self._sport = SportClient()
        self._sport.SetTimeout(10.0)
        self._sport.Init()

        print(f"[INIT] 订阅状态主题: {TOPIC_HIGHSTATE}")
        self._state_suber = ChannelSubscriber(TOPIC_HIGHSTATE, SportModeState_)
        self._state_suber.Init(self._on_high_state, 10)

        print("[INIT] 等待首帧机器人状态...")
        waited = 0
        while self._robot_state is None and waited < 30:
            time.sleep(0.1)
            waited += 1
        if self._robot_state is None:
            print("[WARN] 未收到机器人状态，里程计数据将不可用")

    # ================================================================
    # 机器人状态回调
    # ================================================================
    def _on_high_state(self, msg):
        with self._robot_state_lock:
            self._robot_state = msg

    def _get_yaw(self):
        with self._robot_state_lock:
            if self._robot_state is None:
                return 0.0
            return float(self._robot_state.imu_state.rpy[2])

    def _get_pitch(self):
        """获取当前俯仰角 (rad), 正值=抬头, 负值=低头"""
        with self._robot_state_lock:
            if self._robot_state is None:
                return 0.0
            return float(self._robot_state.imu_state.rpy[1])

    @staticmethod
    def _normalize_angle(angle):
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    # ================================================================
    # 命令接口
    # ================================================================
    def set_command(self, vx, vy, vyaw):
        with self._cmd_lock:
            self._target_vx = vx
            self._target_vy = vy
            self._target_vyaw = vyaw

    def _get_command(self):
        with self._cmd_lock:
            return (self._target_vx, self._target_vy, self._target_vyaw)

    # ================================================================
    # 控制线程 (100Hz)
    # ================================================================
    def _control_loop(self):
        print("[CTRL] 控制线程启动 (@~100Hz)")
        time.sleep(0.1)
        period = 1.0 / CTRL_HZ
        while self._control_running:
            if self._init_done:
                vx, vy, vyaw = self._get_command()
                self._sport.Move(vx, vy, vyaw)
            time.sleep(period)
        print("[CTRL] 控制线程退出")

    # ================================================================
    # 机器人初始化
    # ================================================================
    def _init_robot(self):
        print("[INIT] SelectMode('normal')...")
        self._msc.SelectMode("normal")
        time.sleep(2.0)

        print("[INIT] StandUp...")
        self._sport.StandUp()
        time.sleep(4.0)

        print("[INIT] SpeedLevel(2)...")
        self._sport.SpeedLevel(2)
        time.sleep(1.0)

        print("[INIT] ClassicWalk(True)...")
        self._sport.ClassicWalk(True)
        time.sleep(1.0)
        print("[INIT] Move(0,0,0) 锁定位置...")
        self._sport.Move(0.0, 0.0, 0.0)

    # ================================================================
    # 摄像头
    # ================================================================
    def _start_camera(self, retries: int = 5):
        """启动 USB Live camera"""
        for attempt in range(retries):
            if attempt > 0:
                print(f"[CAM] 重试启动摄像头 ({attempt+1}/{retries})...")
                time.sleep(1.0)
            for idx in (0, 1, 2, 8):
                cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
                if cap.isOpened():
                    self._cap = cap
                    print(f"[CAM] 找到 USB Live camera 在 /dev/video{idx}")
                    break
            else:
                continue
            if not self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')):
                print("[CAM] MJPG 不可用，使用默认像素格式")
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            self._cap.set(cv2.CAP_PROP_FPS, FPS)
            self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
            self._cap.set(cv2.CAP_PROP_EXPOSURE, CAMERA_EXPOSURE)
            self._camera_on = True
            print(f"[CAM] USB Live camera 已启动 "
                  f"({int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
                  f"{int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})")
            return
        raise RuntimeError("无法打开 USB Live camera")

    # ================================================================
    # 步态切换
    # ================================================================
    def _switch_to_classic(self):
        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.15)
        self._sport.StopMove()
        time.sleep(0.3)
        self._sport.ClassicWalk(True)
        time.sleep(0.5)
        print("[GAIT] 切换经典步态 ClassicWalk")

    # ================================================================
    # 检测器/PID 重配置
    # ================================================================
    def _configure_detector(self, black_threshold, min_area, min_width=None):
        self._detector.black_threshold = black_threshold
        self._detector.min_area = min_area
        if min_width is not None:
            self._detector.min_width = min_width

    def _configure_pid(self, kp, ki, kd, max_yaw, integral_max):
        self._pid.kp = kp
        self._pid.ki = ki
        self._pid.kd = kd
        self._pid.output_min = -max_yaw
        self._pid.output_max = max_yaw
        self._pid.integral_min = -integral_max
        self._pid.integral_max = integral_max
        self._pid.reset()

    # ================================================================
    # Phase 3: 巡线 + 黑区检测 → 上台阶(俯仰闭环+偏航纠偏) → 左转 → 下台阶
    # ================================================================
    def _phase3_stairs(self):
        """
        Phase 3 流程 (全部 ClassicWalk, IMU 姿态闭环上台阶):
          1. CENTER_1   — 初始居中校准（横向平移对齐黑线）
          2. LINE_TRACK  — PID 巡线 + 边跑边记录 30 个偏航角取均值 + 黑色占比检测
          3. STAIRS_UP   — 上台阶: 0.45速度 + 偏航角实时纠偏 + 俯仰监测
          4. TURN_LEFT   — 台阶上原地左转（IMU 闭环）
          5. STAIRS_DOWN — ClassicWalk 直走下台阶（纯延时）
          6. CENTER_2    — 二次居中：先强制右移搜索黑线，再横向对齐
        """

        print("\n" + "=" * 60)
        print("  Phase 3: 巡线 + 黑区检测 + 台阶 (IMU 姿态闭环)")
        print("=" * 60)

        # ── 配置 Phase 3 专用检测器和 PID 参数 ──
        self._configure_detector(P3_BLACK_THRESHOLD, P3_MIN_AREA)
        self._configure_pid(P3_PID_KP, P3_PID_KI, P3_PID_KD,
                            P3_PID_MAX_YAW, P3_PID_INTEGRAL_MAX)
        self._sport.SpeedLevel(2)  # 台阶需要更高扭矩
        print("[P3] 速度档位 = 2")

        # ── Phase 3 状态变量 ──
        state = P3S_CENTER_1
        state_start_time = time.time()
        state_start_yaw = self._get_yaw()
        black_confirm_count = 0          # 黑区连续确认帧数
        center_confirm = 0               # 居中连续确认帧数
        center2_phase = 0                # CENTER_2 子阶段: 0=左旋搜索, 1=右旋搜索, 2=循线对齐
        center2_start_yaw = 0.0          # CENTER_2 当前旋转阶段起始偏航角
        yaw_samples = []                 # 偏航角采样列表 (LINE_TRACK 边跑边采)
        last_yaw_sample_time = 0.0      # 上次偏航角采样时间
        avg_yaw = 0.0                    # 平均偏航角 (上台阶目标朝向)
        pitch_was_climbing = False       # 俯仰是否曾经偏离零点 (上过台阶)
        self._pid.reset()

        while self._running:
            # ================================================================
            # 无视觉状态 — 不需要摄像头帧
            #   STAIRS_UP:  IMU 姿态闭环上台阶
            #   TURN_LEFT:  IMU 闭环左转
            #   STAIRS_DOWN:直走下台阶
            # ================================================================
            if state in (P3S_STAIRS_UP, P3S_TURN_LEFT, P3S_STAIRS_DOWN):
                if state == P3S_STAIRS_UP:
                    # ── 上台阶：IMU 姿态闭环 ──
                    # 俯仰角快速偏离0(爬升) → 前脚上到第三台阶后俯仰回零 → 减速 → 停
                    pitch = self._get_pitch()
                    current_yaw = self._get_yaw()

                    # 偏航纠偏：以 avg_yaw 为目标，实时修正跑歪
                    yaw_error = self._normalize_angle(avg_yaw - current_yaw)
                    yaw_correction = P3_STAIRS_YAW_KP * yaw_error
                    yaw_correction = max(-P3_STAIRS_YAW_MAX,
                                         min(P3_STAIRS_YAW_MAX, yaw_correction))

                    # 俯仰监测逻辑
                    if abs(pitch) > P3_PITCH_CLIMBING_THRESH:
                        # 俯仰偏离零点 → 正在爬升，标记
                        pitch_was_climbing = True

                    if pitch_was_climbing and abs(pitch) < P3_PITCH_STOP_THRESH:
                        # 曾经爬升过 + 俯仰已归零 → 立刻停
                        self.set_command(0, 0, 0)
                        time.sleep(0.3)
                        self._sport.StopMove()
                        time.sleep(0.2)
                        self._sport.ClassicWalk(True)
                        time.sleep(0.3)
                        print(f"[P3] 俯仰归零 pitch={math.degrees(pitch):.1f}° → 上台阶完成!")
                        # 原地停 1s，然后左平移 0.3s，再左转
                        time.sleep(1.0)
                        print(f"[P3] 左平移 {P3_TOP_STRAFE_LEFT_DUR}s...")
                        self.set_command(0, P3_TOP_STRAFE_LEFT_SPEED, 0)
                        time.sleep(P3_TOP_STRAFE_LEFT_DUR)
                        self.set_command(0, 0, 0)
                        time.sleep(0.15)
                        print(f"[P3] 后退 {P3_TOP_BACK_DUR}s...")
                        self.set_command(-P3_TOP_BACK_SPEED, 0, 0)
                        time.sleep(P3_TOP_BACK_DUR)
                        self.set_command(0, 0, 0)
                        time.sleep(0.2)
                        state = P3S_TURN_LEFT
                        state_start_time = time.time()
                        state_start_yaw = self._get_yaw()
                        print("[P3] -> TURN_LEFT")
                    elif pitch_was_climbing and abs(pitch) < P3_PITCH_RETURN_THRESH:
                        # 俯仰正在回零 → 减速慢走
                        self.set_command(P3_STAIRS_SLOW_SPEED, 0, yaw_correction)
                    else:
                        # 爬升中 → 全速 0.7 + 偏航纠偏
                        self.set_command(P3_STAIRS_FAST_SPEED, 0, yaw_correction)

                    time.sleep(CTRL_DT)
                    continue

                elif state == P3S_TURN_LEFT:
                    # ── 左转：IMU 闭环控制 ──
                    current_yaw = self._get_yaw()
                    diff = abs(self._normalize_angle(current_yaw - state_start_yaw))
                    target = math.radians(P3_TURN_ANGLE_DEG)
                    if diff < target:
                        self.set_command(0, 0, P3_TURN_SPEED)
                    else:
                        self.set_command(0, 0, 0)
                        time.sleep(0.4)
                        state = P3S_STAIRS_DOWN
                        state_start_time = time.time()
                        print(f"[P3] 左转{P3_TURN_ANGLE_DEG}°完成 -> STAIRS_DOWN")

                elif state == P3S_STAIRS_DOWN:
                    # ── 下台阶：ClassicWalk 直走 ──
                    elapsed = time.time() - state_start_time
                    if elapsed < P3_STAIRS_DOWN_DUR:
                        self.set_command(P3_STAIRS_DOWN_SPEED, 0, 0)
                    else:
                        self.set_command(0, 0, 0)
                        time.sleep(0.4)
                        print(f"[P3] 下台阶完成，左旋搜索黑线 (最多{P3_CENTER2_LEFT_MAX_DEG}°)")
                        self._switch_to_classic()
                        state = P3S_CENTER_2
                        center2_phase = 0
                        center2_start_yaw = self._get_yaw()
                        self._pid.reset()

                time.sleep(CTRL_DT)
                continue

            # ================================================================
            # 视觉处理状态 — 需要 USB 摄像头帧
            #   CENTER_1:   初始居中
            #   LINE_TRACK: PID 巡线 + 黑色占比检测
            #   CENTER_2:   二次居中（强制右移搜索 + 横向对齐）
            # ================================================================
            ret, color_img = self._cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
            (found, offset, best_cx, best_cy, largest_area,
             _touches_left, _touches_right, _sig_count) = self._detector.detect(gray)

            # ---- Phase 3 状态机 ----
            if state == P3S_CENTER_1:
                # ── 初始居中：横向平移对齐黑线，超时3s强制进入下一步 ──
                elapsed_center = time.time() - state_start_time
                if elapsed_center > P3_CENTER_TIMEOUT:
                    print(f"[P3] 初始居中超时 ({elapsed_center:.1f}s > {P3_CENTER_TIMEOUT}s)，强制进入巡线")
                    self.set_command(0, 0, 0)
                    time.sleep(0.2)
                    state = P3S_LINE_TRACK
                    yaw_samples = []
                    last_yaw_sample_time = 0.0
                    avg_yaw = 0.0
                    self._pid.reset()
                elif found:
                    vy = P3_CENTER_LATERAL_KP * offset
                    vy = np.clip(vy, -P3_CENTER_LATERAL_MAX, P3_CENTER_LATERAL_MAX)
                    self.set_command(0.0, vy, 0.0)
                    if abs(offset) < P3_CENTER_THRESHOLD:
                        center_confirm += 1
                    else:
                        center_confirm = max(0, center_confirm - 1)
                    if center_confirm >= P3_CENTER_CONFIRM_FRAMES:
                        print(f"[P3] 初始居中完成 offset={offset:.3f}，开始巡线+记录偏航角")
                        self.set_command(0, 0, 0)
                        time.sleep(0.3)
                        state = P3S_LINE_TRACK
                        yaw_samples = []
                        last_yaw_sample_time = 0.0
                        avg_yaw = 0.0
                        self._pid.reset()
                else:
                    self.set_command(0, 0, 0)
                    center_confirm = max(0, center_confirm - 1)

            elif state == P3S_LINE_TRACK:
                # ── PID 巡线 + 边跑边记录偏航角 + 黑色占比检测 ──

                # 偏航角采样：边巡线边记录，间隔 P3_YAW_SAMPLE_DELAY 秒
                now = time.time()
                if len(yaw_samples) < P3_YAW_SAMPLE_COUNT:
                    if now - last_yaw_sample_time >= P3_YAW_SAMPLE_DELAY:
                        yaw_samples.append(self._get_yaw())
                        last_yaw_sample_time = now
                        if len(yaw_samples) == 1:
                            print(f"[P3] 开始记录偏航角 (巡线中, {P3_YAW_SAMPLE_COUNT}点 "
                                  f"@{P3_YAW_SAMPLE_DELAY}s)")
                    if len(yaw_samples) >= P3_YAW_SAMPLE_COUNT:
                        avg_yaw = self._normalize_angle(
                            sum(yaw_samples) / len(yaw_samples))
                        print(f"[P3] 偏航角记录完成: avg={math.degrees(avg_yaw):.2f}° "
                              f"(min={math.degrees(min(yaw_samples)):.2f}° "
                              f"max={math.degrees(max(yaw_samples)):.2f}°)")
                elif avg_yaw == 0.0:
                    # 防御：如果采样完成了但 avg_yaw 还是 0，强制重算
                    avg_yaw = self._normalize_angle(
                        sum(yaw_samples) / len(yaw_samples))

                black_ratio = self._detector.get_black_ratio(gray)

                # 检测大面积黑色 → 触发 IMU 姿态闭环上台阶
                if black_ratio > P3_BLACK_RATIO_THRESHOLD:
                    black_confirm_count += 1
                    if black_confirm_count >= P3_BLACK_CONFIRM_FRAMES:
                        print(f"[P3] 检测大面积黑色({black_ratio:.2f}) → IMU姿态闭环上台阶 "
                              f"(目标偏航={math.degrees(avg_yaw):.1f}°)")
                        self.set_command(0, 0, 0)
                        time.sleep(0.4)
                        self._sport.StopMove()
                        time.sleep(0.2)
                        self._sport.ClassicWalk(True)
                        time.sleep(0.3)
                        state = P3S_STAIRS_UP
                        state_start_time = time.time()
                        pitch_was_climbing = False
                        continue
                else:
                    black_confirm_count = max(0, black_confirm_count - 1)

                # 标准 PID 巡线（加偏置修正身体偏移）
                if found:
                    biased_offset = offset - P3_TRACK_OFFSET_BIAS
                    yaw = self._pid.update(biased_offset, CTRL_DT)
                    slow_coeff = 0.6 if abs(biased_offset) > 0.5 else 1.0
                    vx = P3_BASE_SPEED * slow_coeff
                    self.set_command(vx, 0.0, yaw)
                else:
                    # 丢线时缓慢前进尝试找回
                    self._pid.reset()
                    self.set_command(0.03, 0, 0)

            elif state == P3S_CENTER_2:
                # ── 二次居中：左旋搜索 → 右旋搜索 → 循线对齐 ──
                current_yaw = self._get_yaw()
                rotated = abs(self._normalize_angle(current_yaw - center2_start_yaw))

                if center2_phase == 0:
                    # 阶段0: 左旋搜索，最多 P3_CENTER2_LEFT_MAX_DEG 度
                    if rotated < math.radians(P3_CENTER2_LEFT_MAX_DEG):
                        self.set_command(0, 0, P3_CENTER2_ROTATE_SPEED)
                        if found:
                            print(f"[P3] 左旋搜索找到黑线 offset={offset:.3f}，开始循线对齐")
                            center2_phase = 2
                            center_confirm = 0
                    else:
                        # 左旋到底没找到 → 开始右旋搜索
                        print(f"[P3] 左旋{P3_CENTER2_LEFT_MAX_DEG}°未找到，右旋搜索 (最多{P3_CENTER2_RIGHT_MAX_DEG}°)")
                        center2_phase = 1
                        center2_start_yaw = self._get_yaw()

                elif center2_phase == 1:
                    # 阶段1: 右旋搜索，最多 P3_CENTER2_RIGHT_MAX_DEG 度
                    if rotated < math.radians(P3_CENTER2_RIGHT_MAX_DEG):
                        self.set_command(0, 0, -P3_CENTER2_ROTATE_SPEED)
                        if found:
                            print(f"[P3] 右旋搜索找到黑线 offset={offset:.3f}，开始循线对齐")
                            center2_phase = 2
                            center_confirm = 0
                    else:
                        # 右旋到底也没找到 → 放弃
                        print(f"[P3] 右旋{P3_CENTER2_RIGHT_MAX_DEG}°未找到黑线，放弃搜索，Phase 3 结束")
                        self.set_command(0, 0, 0)
                        time.sleep(0.3)
                        state = P3S_DONE

                elif center2_phase == 2:
                    # 阶段2: 循线对齐
                    if found:
                        # PID 偏航 + 横向平移 双通道对齐
                        yaw = self._pid.update(offset, CTRL_DT)
                        vy = P3_CENTER_LATERAL_KP * offset
                        vy = np.clip(vy, -P3_CENTER_LATERAL_MAX, P3_CENTER_LATERAL_MAX)
                        self.set_command(0.03, vy, yaw)
                        if abs(offset) < P3_CENTER_THRESHOLD:
                            center_confirm += 1
                        else:
                            center_confirm = max(0, center_confirm - 1)
                        if center_confirm >= P3_CENTER_CONFIRM_FRAMES:
                            print("[P3] 二次居中完成，Phase 3 结束")
                            self.set_command(0, 0, 0)
                            time.sleep(0.3)
                            state = P3S_DONE
                    else:
                        # 丢线，继续缓慢旋转搜索
                        self._pid.reset()
                        self.set_command(0, 0, 0.3)  # 慢速左旋找线
                        center_confirm = max(0, center_confirm - 1)

            elif state == P3S_DONE:
                self.set_command(0, 0, 0)
                break

            # ---- 可视化 ----
            display = color_img.copy()
            h, w = display.shape[:2]
            cv2.line(display, (w // 2, 0), (w // 2, h), (255, 0, 0), 2)
            cv2.line(display, (0, h * 2 // 3), (w, h * 2 // 3), (0, 255, 255), 2)
            if found:
                cv2.circle(display, (int(best_cx), int(best_cy)), 8, (0, 255, 0), -1)
            state_names = {P3S_CENTER_1: "CENTER_1",
                           P3S_LINE_TRACK: "LINE_TRACK",
                           P3S_STAIRS_UP: "STAIRS_UP", P3S_TURN_LEFT: "TURN_LEFT",
                           P3S_STAIRS_DOWN: "STAIRS_DOWN", P3S_CENTER_2: "CENTER_2",
                           P3S_DONE: "DONE"}
            cv2.putText(display, f"Phase3 {state_names.get(state, '?')}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            if state == P3S_LINE_TRACK:
                br = self._detector.get_black_ratio(gray)
                cv2.putText(display, f"Black:{br:.2f}", (10, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 0, 255) if br > 0.8 else (255, 255, 255), 2)
                if len(yaw_samples) < P3_YAW_SAMPLE_COUNT:
                    cv2.putText(display, f"YawSampling:{len(yaw_samples)}/{P3_YAW_SAMPLE_COUNT}",
                                (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                elif avg_yaw != 0.0:
                    cv2.putText(display, f"AvgYaw:{math.degrees(avg_yaw):.1f}deg",
                                (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            elif state == P3S_CENTER_2:
                phase_names = {0: "ROT_LEFT", 1: "ROT_RIGHT", 2: "TRACK"}
                cv2.putText(display, f"C2:{phase_names.get(center2_phase, '?')} "
                            f"rot={math.degrees(abs(self._normalize_angle(self._get_yaw()-center2_start_yaw))):.1f}deg",
                            (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
            elif state == P3S_STAIRS_UP:
                # 上台阶时显示俯仰角和偏航纠偏信息（在非视觉循环里，这里不会被渲染到）
                pass
            cv2.imshow("Phase3 Stairs", display)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                self._running = False
                return

            time.sleep(CTRL_DT)

    # ================================================================
    # 关闭
    # ================================================================
    def _shutdown(self):
        print("\n[SHUTDOWN] 停止所有系统...")
        self._control_running = False
        time.sleep(0.3)

        try:
            self._sport.StopMove()
            time.sleep(0.4)
        except Exception:
            pass

        try:
            if self._cap and self._camera_on:
                self._cap.release()
                self._camera_on = False
                print("[CAM] 摄像头已关闭")
        except Exception:
            pass

        cv2.destroyAllWindows()
        print("[SHUTDOWN] 程序安全退出")

    # ================================================================
    # 顶层编排
    # ================================================================
    def run(self):
        # 一次性机器人初始化
        self._init_robot()

        # 启动控制线程
        ctrl_thread = threading.Thread(
            target=self._control_loop, daemon=True, name="ctrl")
        ctrl_thread.start()

        # 启动摄像头
        self._start_camera()

        # 初始化完成，允许控制线程发指令
        self._init_done = True

        try:
            if self._running:
                self._phase3_stairs()     # Phase 3: 居中 → 巡线+黑区检测 → 上台阶 → 左转 → 下台阶 → 二次居中
        except KeyboardInterrupt:
            print("\n[INFO] 用户中断")
        except Exception as e:
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._shutdown()


# ============================================================
# 主入口
# ============================================================
def main():
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

    if len(sys.argv) >= 2:
        network_iface = sys.argv[1]
    else:
        print("[INFO] 未指定网络接口，自动检测...")
        network_iface = auto_detect_interface()
        if network_iface is None:
            print("用法: python3 phase3_stairs.py <networkInterface>")
            print("示例: python3 phase3_stairs.py eth0")
            sys.exit(-1)

    print("=" * 60)
    print("  Go2 Phase 3: 巡线 + 黑区检测 + 台阶")
    print(f"  网络接口: {network_iface}")
    print("=" * 60)

    # 信号处理
    def on_signal(sig, frame):
        print("\n[STOP] 收到终止信号")
        sys.exit(0)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    try:
        mission = Phase3Mission(network_interface=network_iface)
    except Exception as e:
        print(f"\n[ERROR] 使用接口 {network_iface} 初始化失败: {e}")
        auto_iface = auto_detect_interface()
        if auto_iface and auto_iface != network_iface:
            print(f"[INFO] 重试接口: {auto_iface}")
            mission = Phase3Mission(network_interface=auto_iface)
        else:
            print("[FATAL] 无法找到可用的网络接口")
            sys.exit(-1)

    mission.run()


if __name__ == "__main__":
    main()
