#!/usr/bin/env python3

# ===== 组合选择 (修改此变量切换 Phase 6+7 行为) =====
# 1=放左边+打招呼  2=放左边+伸懒腰  3=放左边+闪灯三次
# 4=放右边+打招呼  5=放右边+伸懒腰  6=放右边+闪灯三次
COMBO_SELECT = 3

"""
Go2 Phase 1-8 全流程程序
=========================
Phase 1: 黑线循迹 + 白线检测 → 单次前跳
Phase 2: 迷宫定序运动（前进2s + TOF 迷宫导航）
Phase 3: 巡线 + 黑区检测 → 台阶
Phase 4: 机械臂识别 + D435i 红圆检测 → 倒计时 → OCR识别平台标志(1号/2号, 决定 Phase 7 放物方向) → 左平移 → 抓取
Phase 5: 循线 → 丢线放物 → 二次抓取
Phase 6: 循线 + USB 红圆检测(出现→彻底消失后计时2s) → 左转85° → 后退0.8s → OCR识别警示标志(打招呼/伸懒腰/闪灯) → 对应动作
Phase 7: 右转 + 前进1.5s + 循线 + 两侧黑色触发倒计时 → 放物(方向由 Phase 4 OCR 决定) → 放物后前进1.5s
Phase 8: 循线 + 白线检测 → 前跳 → 前进 → 左转 → 蓝色驱动前进

用法:
  python3 phase1_only.py <networkInterface>
  python3 phase1_only.py eth0
"""

import sys
import os
import time
import math
import threading
import signal
import subprocess
import re
import importlib

# === Jetson libgomp TLS 修复 (必须在 cv2/torch 等重型模块之前执行) ===
# torch 的 libgomp 需要大量静态 TLS 空间，cv2 先加载会抢占导致
# "cannot allocate memory in static TLS block"。先预加载 libgomp。
import ctypes
_flags = sys.getdlopenflags()
sys.setdlopenflags(_flags | ctypes.RTLD_GLOBAL)
_loaded = False
for _base in sys.path:
    _dir = os.path.join(_base, "torch.libs")
    if os.path.isdir(_dir):
        for _f in os.listdir(_dir):
            if _f.startswith("libgomp"):
                ctypes.CDLL(os.path.join(_dir, _f)); _loaded = True; break
    if _loaded: break
if not _loaded:
    ctypes.CDLL("libgomp.so.1")
sys.setdlopenflags(_flags)

import json
from dataclasses import dataclass

import cv2
import numpy as np
import pyrealsense2 as rs
import dds_lib_fix  # noqa: E402  (must run before cyclonedds: preload matching libddsc)
import cyclonedds.idl as idl
import cyclonedds.idl.annotations as annotate
import cyclonedds.idl.types as types

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
from unitree_sdk2py.a2.audio.audio_client import AudioClient
from unitree_sdk2py.go2.vui.vui_client import VuiClient

# Phase 2 迷宫 TOF 导航库函数（测距模块/迷宫_tof.py）
from 测距模块.迷宫_tof import run_maze_navigation

# ============================================================
# OCR 标志识别 (Recognition/ocr_recognizer.py, 封装成函数)
# Phase 4 (平台 1号/2号) 与 Phase 6 (警示: 打招呼/伸懒腰/闪灯) 共用同一识别模型,
# 只加载一次, Phase 4 快跑段预加载后两个阶段取用即热。
# ============================================================
RECOGNITION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Recognition")
if RECOGNITION_DIR not in sys.path:
    sys.path.insert(0, RECOGNITION_DIR)

# --- OCR 识别参数 ---
OCR_RECOG_TIMEOUT = 5.0      # 平台标志识别超时 (秒, 兜底摄像头路径用)
OCR_PLATFORM_SIDE_MAP = {    # 平台标志 → Phase 7 放物方向 (1号=左, 2号=右, 按场地可改)
    "1号平台": "左",
    "2号平台": "右",
}

_OCR_RECOGNIZER = None            # 共享单例 (Phase 4 平台 + Phase 6 警示 共用)
_OCR_INIT_LOCK = threading.Lock() # 保护单例初始化 (预加载线程与主线程可能并发)
_OCR_PRELOAD_THREAD = None        # 后台预加载线程

def _get_ocr_recognizer():
    """懒加载共享 OCRRecognizer 单例 (首次调用才 import + init 识别器模型)

    线程安全 (双重检查锁): 预加载后台线程与识别主线程并发调用不会重复初始化。
    实测模型加载约 6s — 由 _preload_ocr 在 Phase 4 快跑段提前加载,
    Phase 4 识别平台标志与 Phase 6 识别警示标志共用此实例, 只加载一次。
    """
    global _OCR_RECOGNIZER
    if _OCR_RECOGNIZER is not None:
        return _OCR_RECOGNIZER
    with _OCR_INIT_LOCK:
        if _OCR_RECOGNIZER is None:
            try:
                from ocr_recognizer import OCRRecognizer
                _OCR_RECOGNIZER = OCRRecognizer()
                _OCR_RECOGNIZER.init()
                if not _OCR_RECOGNIZER._initialized:
                    print("[OCR] [ERROR] 标志识别器初始化失败")
                    _OCR_RECOGNIZER = None
            except Exception as e:
                print(f"[OCR] [ERROR] 标志识别器加载失败: {e}")
                _OCR_RECOGNIZER = None
    return _OCR_RECOGNIZER

def _preload_ocr():
    """Phase 4 快跑段后台预加载共享 OCR 识别器 (模型初始化约 6s, 纯软件不碰硬件)

    与快跑段(6.5s)+循线并行执行; Phase 4 识别平台标志与 Phase 6 识别警示标志
    共用此模型, 两个阶段取用均即热。若倒计时提前到达且预加载未完成,
    _get_ocr_recognizer 会持锁等待其完成。
    """
    global _OCR_PRELOAD_THREAD
    if _OCR_PRELOAD_THREAD is not None:
        return
    _OCR_PRELOAD_THREAD = threading.Thread(
        target=_get_ocr_recognizer, daemon=True, name="ocr_preload")
    _OCR_PRELOAD_THREAD.start()
    print("[OCR] 后台预加载共享识别器已启动 (模型加载约 6s, 与 Phase 4 快跑并行)")

def recognize_marker(frame, save=False):
    """从一帧 BGR 图像识别标志 → 返回 (category, confidence)；
    Phase 6 只保留警示标志(打招呼/伸懒腰/闪烁前灯3次), 忽略 1号平台/2号平台;
    识别失败/未初始化 → (None, 0.0)。"""
    rec = _get_ocr_recognizer()
    if rec is None or frame is None or frame.size == 0:
        return None, 0.0
    markers = rec.recognize_frame(frame, save=save)
    if not markers:
        return None, 0.0
    # 只取能对应 Phase 6 动作的警示标志 (不要 1号平台/2号平台)
    signs = [m for m in markers if marker_to_phase6_action(m.category) is not None]
    if not signs:
        return None, 0.0
    best = max(signs, key=lambda m: m.confidence)
    return best.category, best.confidence

def marker_to_phase6_action(category):
    """识别类别 → Phase 6 动作: 打招呼→'hello' 伸懒腰→'stretch'
    闪烁前灯3次→'flash'；无法对应 → None。"""
    if not category:
        return None
    if "打招呼" in category:
        return "hello"
    if "伸懒腰" in category:
        return "stretch"
    if "闪" in category and "灯" in category:
        return "flash"
    return None

# ============================================================
# 机械臂控制 (来自 Arm.py)
# ============================================================

@dataclass
@annotate.final
@annotate.autoid("sequential")
class ArmString_(idl.IdlStruct, typename="unitree_arm.msg.dds_.ArmString_"):
    data_: str


@dataclass
@annotate.final
@annotate.autoid("sequential")
class PubServoInfo_(idl.IdlStruct, typename="unitree_arm.msg.dds_.PubServoInfo_"):
    servo0_data_: types.float32
    servo1_data_: types.float32
    servo2_data_: types.float32
    servo3_data_: types.float32
    servo4_data_: types.float32
    servo5_data_: types.float32
    servo6_data_: types.float32


ARM_ACTIONS = {
    "夹住走": [-6.9, -87, 89.7, -0.3, 3.8, 0.3, 19],
    "放左抬起1": [-58, 18, 48, -2, -90, 0, 19],
    "放左1": [-58, 33, 48, -2, -90, 0, 19],
    "放左": [-58, 48, 48, -2, -90, 0, 19],
    "放左松开": [-58, 48, 48, -2, -90, 0, 60],
    "放左抬起2": [-58, 18, 48, -2, -90, 0, 60],
    "放右抬起1": [54, 20, 46, 0, -88, 0, 19],
    "放右1": [54, 33, 48, -2, -90, 0, 19],
    "放右": [54, 48, 48, -2, -90, 0, 19],
    "放右松开": [54, 47, 46, 0, -88, 0, 60],
    "放右抬起2": [54, 20, 46, 0, -88, 0, 60],
    "预备放": [82,35,18,-3,-77,1,19],
    "放": [80,57,18,-3,-77,1,19],
    "松": [80,57,18,-3,-77,1,60],
    "抬": [80,35,18,-3,-77,1,60],
    "识别": [-90, -75, 87, -8, 9.8, 1.8, 60],
    "识别物块": [-90, 10, 55, 0, -61, 0, 60],
    "识别物块2": [62.5, 0.2, 69.9, 0.0,-55.9, 0.0, 60.0],
}


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
# 🔧 可调参数汇总 — 所有需要微调的参数都在这里 🔧
# 排列顺序按状态机执行流程: Phase 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
# ============================================================

# ──────────────────────────────────────────────────────────────
# 📷 摄像头参数 (全局共用)
# ──────────────────────────────────────────────────────────────
FRAME_WIDTH = 640          # 图像宽度
FRAME_HEIGHT = 480         # 图像高度
FPS = 30                   # 帧率
CAMERA_EXPOSURE = 40         # 手动曝光值 (范围 3~2047, 越小越暗, 默认166)

# ──────────────────────────────────────────────────────────────
# ⚙️ 控制参数 (全局共用)
# ──────────────────────────────────────────────────────────────
CTRL_HZ = 100              # 控制循环频率
CTRL_DT = 1.0 / CTRL_HZ    # 控制周期 (自动计算)


# ================================================================
#  Phase 1 — 黑线循迹 + 白线检测 → 单次前跳 → 继续循线 → 丢线结束
#  状态机: NORMAL → JUMP(白线检测后直接跳) → NORMAL(跳后循线) → 丢线 → DONE
#  白线检测仅跳前生效(jump_count<1), 跳后不再触发第二次跳跃
#  注意: GO_FORWARD/ROTATING/JUMP_ALIGN 是死代码 — JUMP_ALIGN 已移除, is_sharp_turn 被硬编码为 False
# ================================================================

# --- 黑线检测 ---
P1_THRESHOLD = 120           # 黑线二值化阈值 (越大检测越严格)
P1_MIN_AREA = 500.0         # 最小轮廓面积
P1_MIN_WIDTH = 100           # 最小轮廓外接矩形宽度 (像素, 过滤细线)

# --- PID 巡线控制 ---
P1_PID_KP = 0.80            # 比例系数
P1_PID_KI = 0.04            # 积分系数
P1_PID_KD = 0.08            # 微分系数
P1_PID_MAX_YAW = 2.0        # PID 输出最大偏航角速度
P1_PID_INTEGRAL_MAX = 1.5   # 积分限幅

# --- 巡线速度 ---
P1_BASE_SPEED = 0.3      # 基础前进速度 (m/s)

# --- 急转弯处理 (已禁用: is_sharp_turn 硬编码为 False, GO_FORWARD/ROTATING 为死代码) ---
P1_SHARP_TURN_THRESHOLD = 30 # [未使用] 连续大偏移帧数触发急转弯
P1_FORWARD_DIST = 0.25      # [未使用] 急转弯前冲距离 (m)
P1_ROTATION_ANGLE = math.radians(80)  # [未使用] 急转弯旋转角度 (rad)
P1_COOLDOWN_FRAMES = 15     # 急转弯冷却帧数 (仍用于跳后 cooldown)

# --- 白线检测 ---
P1_WHITE_BRIGHTNESS = 140   # 白色亮度阈值
P1_WHITE_GAP_MIN = 4        # 白线最小行高 (像素)
P1_WHITE_CROSS_CONFIRM = 3  # 白线连续确认帧数
P1_WHITE_BGR_THRESH = 155   # BGR 三通道白色阈值
P1_WHITE_LINE_RATIO = 0.30  # 白线行像素占比阈值

# --- 白线后居中校准 ---
P1_CENTER_THRESHOLD = 0.12  # 居中判定偏移阈值
P1_CENTER_CONFIRM = 8       # 居中连续确认帧数
P1_ALIGN_MAX_YAW = 1.0      # 校准最大偏航角速度
P1_ALIGN_TIMEOUT = 1.0      # 校准超时 (秒)

# --- 前跳 ---
P1_JUMP_FORWARD_DUR = 0.2   # 跳跃前冲时长 (秒)
P1_JUMP_FORWARD_SPEED = 0.16 # 跳跃前冲速度 (m/s)
P1_JUMP_STOP_DUR = 1.0      # 跳跃前停顿 (秒, 确保机器人完全静止)

# --- 跳后循线偏移偏置 (当前未使用, 跳后正常循线无偏置) ---
P1_TRACK_OFFSET_BIAS = 0.1  # [未使用]


# ================================================================
#  Phase 2 — 迷宫定序运动：前进 2s → 调用 测距模块/迷宫_tof 的 TOF 导航
#  （旧盲走微调步进序列已废弃，由 run_maze_navigation() 接管）
# ================================================================
MAZE_FORWARD_SPEED = 0.25     # 迷宫入口前进速度 (m/s)


# ================================================================
#  Phase 3 — 巡线 + 黑区检测 → 上台阶(IMU姿态闭环) + 左转 + 下台阶 (全部经典模式)
#  状态机: CENTER_1 → LINE_TRACK → STAIRS_UP → TURN_LEFT → STAIRS_DOWN → CENTER_2 → DONE
# ================================================================

# --- 黑线检测 ---
P3_BLACK_THRESHOLD = 130    # 黑线二值化阈值
P3_MIN_AREA = 150.0         # 最小轮廓面积

# --- PID 巡线控制 ---
P3_PID_KP = 0.70            # 比例系数
P3_PID_KI = 0.04            # 积分系数
P3_PID_KD = 0.08            # 微分系数
P3_PID_MAX_YAW = 2.0        # PID 输出最大偏航角速度
P3_PID_INTEGRAL_MAX = 1.5   # 积分限幅

# --- 巡线速度 ---
P3_BASE_SPEED = 0.19        # 基础前进速度 (m/s)

# --- 循线偏移偏置 (正值=黑线偏左, 负值=黑线偏右) ---
P3_TRACK_OFFSET_BIAS = 0.00   # 0=对中循线, 正值=黑线偏左

# --- 初始居中 ---
P3_CENTER_THRESHOLD = 0.12          # 居中判定偏移阈值
P3_CENTER_CONFIRM_FRAMES = 6        # 居中连续确认帧数
P3_CENTER_TIMEOUT = 2.0             # 居中超时 (秒), 超时后强制进入下一步
P3_CENTER_LATERAL_KP = 0.50         # 横向居中 P 系数
P3_CENTER_LATERAL_MAX = 0.25        # 横向速度上限 (m/s)

# --- 二次居中 (下台阶后旋转搜索黑线) ---
P3_CENTER2_TIMEOUT = 6          # 二次居中总超时 (秒), 超时直接结束 Phase 3
P3_CENTER2_ROTATE_SPEED = 0.5       # 搜索旋转角速度 (rad/s)
P3_CENTER2_LEFT_MAX_DEG = 8         # 左旋搜索最大角度 (度)
P3_CENTER2_RIGHT_MAX_DEG = 16       # 右旋搜索最大角度 (度, 从左极限向右扫)

# --- 黑区检测 (触发上台阶) ---
P3_BLACK_RATIO_THRESHOLD = 0.80     # 画面黑色占比触发阈值 (>80% 视为进入黑区)
P3_BLACK_CONFIRM_FRAMES = 3         # 黑色区域连续确认帧数 (防抖动)

# --- 偏航角记录 ---
P3_YAW_SAMPLE_COUNT = 30            # 对中后记录偏航角采样数
P3_YAW_SAMPLE_DELAY = 0.1           # 每次采样间隔 (秒)

# --- 台阶动作 (IMU 姿态闭环) ---
P3_STAIRS_FAST_SPEED = 0.42         # 上台阶快速段速度 (m/s)
P3_STAIRS_SLOW_SPEED = 0.15         # 俯仰回零时减速 (m/s)
P3_STAIRS_YAW_KP = 1.50          # 上台阶偏航纠偏 P 系数
P3_STAIRS_YAW_MAX = 0.401      # 偏航纠偏最大角速度 (rad/s)
P3_PITCH_CLIMBING_THRESH = math.radians(24)    # 俯仰偏离阈值 (rad), 超过=正在爬升
P3_PITCH_RETURN_THRESH = math.radians(20)      # 俯仰回零减速阈值 (rad)
P3_PITCH_STOP_THRESH = math.radians(11.0)       # 俯仰归零停止阈值 (rad)

# --- 台阶顶部微调 (左转前) ---
P3_TOP_STRAFE_LEFT_DUR = 0.85        # 左平移时长 (秒)
P3_TOP_STRAFE_LEFT_SPEED = 0.2      # 左平移速度 (m/s, 正=左)
P3_TOP_BACK_DUR = 0.5               # 后退时长 (秒)
P3_TOP_BACK_SPEED = 0.2             # 后退速度 (m/s, 正=前, 负=后)

# --- 左转 ---
P3_TURN_ANGLE_DEG = 76              # 台阶上转向角度 (度)
P3_TURN_SPEED = 1.6                 # 台阶上转向速度 (rad/s)

# --- 下台阶 ---
P3_STAIRS_DOWN_DUR = 2.35        # 下台阶前进时长 (秒)
P3_STAIRS_DOWN_SPEED = 0.66         # 下台阶前进速度 (m/s)


# ================================================================
#  Phase 4 — 机械臂识别 → 巡线 + D435i 红圆检测 → 3s倒计时 → 左平移 → pick_and_place.py 抓取
# ================================================================

# --- 机械臂识别 ---
ARM_IDENTIFY_DELAY = 0.0      # "识别"动作后延时 (秒)

# --- 巡线速度 ---
P4_BASE_SPEED = 0.4          # 快跑段速度 (m/s, 进入循线后前5秒)
P4_FAST_DURATION = 6.5       # 快跑段时长 (秒)
P4_STEADY_SPEED = 0.22        # 快跑段结束后恢复的正常速度 (m/s)

# --- 红圆倒计时 (检测到红圆后继续巡线多久再停车抓取) ---
P4_RED_COUNTDOWN = 2.6        # 倒计时秒数

# --- 倒计时结束后左平移 (平移完成后再启动抓取) ---
P4_LEFT_STRAFE_DUR = 0.24      # 左平移时长 (秒)
P4_LEFT_STRAFE_SPEED = 0.2    # 左平移速度 (m/s, 正=左)


# ================================================================
#  红圆检测 — D435i 参数 (Phase 4/6 共用)
# ================================================================

# --- 红色 HSV 阈值 ---
RED_HSV_LOWER1 = np.array([0, 120, 70])
RED_HSV_UPPER1 = np.array([10, 255, 255])
RED_HSV_LOWER2 = np.array([170, 120, 70])
RED_HSV_UPPER2 = np.array([180, 255, 255])

RED_AREA_MIN = 0.02           # 最小轮廓面积占比
RED_CIRCULARITY_THRESH = 0.6  # 圆形度阈值
RED_MORPH_KERNEL = 5          # 形态学核大小
RED_BLUR_KERNEL = (5, 5)      # 高斯模糊核
RED_CONFIRM_FRAMES = 64       # 连续确认帧数 (D435i ~30fps, 64帧≈2秒)


# ================================================================
#  Phase 5 — 继续循线 → 丢线后放物(预备放/放/松/抬) → 识别物块2+等10s → pick_and_place1抓取 → 左转30°
# ================================================================

# --- 丢线触发阈值 ---
P5_LOST_THRESHOLD = 30         # 连续丢线帧数触发放物序列 (代码内 LOST_THRESHOLD)

# --- 机械臂放物方向 (由 COMBO_SELECT 自动计算, 1-3=左, 4-6=右) ---
def get_arm_drop_side():
    """返回机械臂放物方向: 1-3=左, 4-6=右 (运行时读取 COMBO_SELECT)"""
    return "左" if COMBO_SELECT <= 3 else "右"

# --- Phase 6 动作选择 (由 COMBO_SELECT 自动计算) ---
def get_phase6_action():
    """返回 Phase 6 动作类型: 'hello' | 'stretch' | 'flash'"""
    m = {1: "hello", 2: "stretch", 3: "flash",
         4: "hello", 5: "stretch", 6: "flash"}
    return m.get(COMBO_SELECT, "hello")

# --- 巡线速度 ---
P5_BASE_SPEED = 0.5          # 快跑段速度 (m/s, 进入循线后前8秒)
P5_FAST_DURATION = 9.5        # 快跑段时长 (秒)
P5_STEADY_SPEED = 0.22        # 快跑段结束后恢复的正常速度 (m/s)

# --- 丢线后左转 ---
P5_LOST_TURN_DEG = 30         # 丢线放物完成后左转角度 (度)
P5_LOST_TURN_SPEED = 1.0      # 丢线放物完成后左转角速度 (rad/s)


# ================================================================
#  Phase 6 — 巡线 + 红圆检测(USB摄像头, 出现→彻底消失后计时2s) → 左转85° → 后退0.8s → 识别标志 → 对应动作(打招呼/伸懒腰/闪灯三次)
# ================================================================

# --- 红圆检测 + 计时 (USB摄像头, 非 D435i) ---
# 触发: 红圆出现 → 彻底消失(连续未检出 P6_RED_GONE_CONFIRM 帧)后 才开始计时
P6_RED_TIMER_DURATION = 1.9          # 红圆彻底消失后计时 (秒)
P6_RED_GONE_CONFIRM = 5                 # 连续未检出帧数, 确认红圆"彻底消失" (防闪烁)
P6_RED_TURN_ANGLE = math.radians(85)    # 计时结束后左转角度 85° (rad)
P6_RED_TURN_SPEED = 1.0                 # 左转角速度 (rad/s)
P6_WIDE_WIDTH = 750                     # Phase 6 动作后摄像头宽度 (便于 Phase 7 检测两侧黑色)

# --- 后退后标志识别 (OCR, 封装自 Recognition/ocr_recognizer.py) ---
P6_RECOG_TIMEOUT = 8.0        # 后退后识别标志超时 (秒)
P6_RECOG_MIN_FRAMES = 3       # 同一类别连续确认帧数 (防误识别)

# --- 巡线速度 ---
P6_BASE_SPEED = 0.45          # 快跑段速度 (m/s, 进入循线后前7秒)
P6_FAST_DURATION = 6.5        # 快跑段时长 (秒)
P6_STEADY_SPEED = 0.22        # 快跑段结束后恢复的正常速度 (m/s)


# ================================================================
#  Phase 7 — 右转68° → 前进1.5s → 循线(底部全宽2s→中央带ROI) + 两侧黑色触发倒计时 → 机械臂放物 → 放物后前进1.5s → 继续循线固定时长
# ================================================================

# --- 右转 ---
P7_TURN_ANGLE = math.radians(58)  # 右转角度 68° (rad)
P7_TURN_SPEED = -1.0              # 右转角速度 (rad/s, 负值=右转)

# --- 画面两侧黑色检测触发倒计时 ---
P7_SIDE_BLACK_RATIO = 0.15        # 单侧黑色占比触发阈值
P7_SIDE_BLACK_CONFIRM = 3         # 连续确认帧数 (防抖动)
P7_TIMER_DURATION = 3.0           # 触发后倒计时 (秒)

# --- Phase 7 循线只认画面中央带 (横向 ROI), 排除两侧黑色物块 ---
P7_LINE_ROI_LEFT = 0.25           # 中央带左边界 (占画面宽比例)
P7_LINE_ROI_RIGHT = 0.75          # 中央带右边界 (占画面宽比例)

# --- 巡线速度 ---
P7_BASE_SPEED = 0.45          # 快跑段速度 (m/s, 进入循线后前4秒)
P7_FAST_DURATION = 2.5        # 快跑段时长 (秒)
P7_STEADY_SPEED = 0.22        # 快跑段结束后恢复的正常速度 (m/s)

# --- 倒计时结束后右移 ---
P7_STRAFE_RIGHT_SPEED = -0.27   # 右移速度 (m/s, 负值=右)
P7_STRAFE_RIGHT_DUR = 0.13       # 右移时长 (秒)

# --- 右转后前进 (右转68°完成后先前进, 再开始循线) ---
P7_POST_TURN_FORWARD_DUR = 1.5               # 右转后前进时长 (秒)
P7_POST_TURN_FORWARD_SPEED = P7_STEADY_SPEED # 右转后前进速度 (m/s, 默认同稳态速度)

# --- 放物后: 前进离开放物点 + 继续循线固定时长 (然后进入 Phase 8) ---
P7_POST_PLACE_FORWARD_DUR = 1.5              # 放物后前进时长 (秒)
P7_POST_PLACE_FORWARD_SPEED = P7_STEADY_SPEED # 放物后前进速度 (m/s, 默认同稳态速度)
P7_POST_PLACE_TRACK_DUR = 3.0                # 放物后继续循线时长 (秒), 到时结束 Phase 7

# --- 循线前段: 底部全宽黑线检测 (只要底部有黑线就循线, 防止巡不到线), 之后变回中央带 ROI ---
P7_BOTTOM_TRACK_DUR = 2.0          # 底部全宽循线时长 (秒), 到时切回中央带ROI循线


# ================================================================
#  Phase 8 — 循线 + 白线检测 → 前跳 → 前进 → 左转 → 蓝色驱动前进
#  状态机: TRACK → JUMP → POST_FORWARD → POST_TURN → POST_FORWARD2 → DONE
#  POST_FORWARD 时长由顶部参数 P8_POST_FORWARD_DUR 控制
# ================================================================

# --- 巡线速度 ---
P8_BASE_SPEED = 0.3         # 基础前进速度 (m/s)

# --- 跳后前进 ---
P8_POST_FORWARD_DUR = 5.8                   # 跳后前进时长 (秒)
P8_POST_FORWARD_SPEED = P8_BASE_SPEED        # 跳后前进速度 (m/s, 默认同 P8)

# --- 跳后左转 (IMU 闭环, 经典模式) ---
P8_POST_TURN_ANGLE_DEG = 85                  # 跳后左转角度 (度)
P8_POST_TURN_SPEED = 1.0                     # 跳后左转角速度 (rad/s)

# --- 左转后前进 (蓝色驱动: 画面底部 ROI 出现蓝色则以 P8_BLUE_SPEED 前进, 蓝色消失则停) ---
P8_BLUE_SPEED = 0.22             # 蓝色存在时前进速度 (m/s)
P8_BLUE_HSV_LOWER = np.array([84, 71, 63])   # 蓝色 HSV 下界 (实测色域, OpenCV H:0-179)
P8_BLUE_HSV_UPPER = np.array([140, 199, 185])  # 蓝色 HSV 上界
P8_BLUE_ROI_BOTTOM_RATIO = 0.25  # 蓝色检测取画面底部比例 (0.25=下面1/4, 调大=区域更大)
P8_BLUE_RATIO_THRESH = 0.02      # 底部 ROI 蓝色像素占比触发阈值


# ================================================================
# 🔩 状态机常量 — Phase 1 子状态
#  流程: NORMAL(0) → JUMP(3) → NORMAL(跳后循线) → 丢线 → DONE(5)
#  白线检测后直接跳 (JUMP_ALIGN 已废弃), 跳后不再触发第二次跳跃
#  GO_FORWARD(1) / ROTATING(2) 为死代码 (is_sharp_turn 硬禁用)
# ================================================================
P1S_NORMAL = 0
P1S_GO_FORWARD = 1
P1S_ROTATING = 2
P1S_JUMP = 3
P1S_JUMP_ALIGN = 4
P1S_DONE = 5

# --- Phase 3 子状态 ---
#   CENTER_1(0) → LINE_TRACK(1) → STAIRS_UP(2) → TURN_LEFT(3)
#   → STAIRS_DOWN(4) → CENTER_2(5) → DONE(6)
P3S_CENTER_1 = 0        # 初始居中：横向平移对齐黑线 (超时强制进入下一步)
P3S_LINE_TRACK = 1      # PID 巡线 + 偏航角采样 + 黑色占比检测
P3S_STAIRS_UP = 2       # IMU 姿态闭环上台阶 (俯仰监测 + 偏航纠偏)
P3S_TURN_LEFT = 3       # IMU 闭环左转
P3S_STAIRS_DOWN = 4     # ClassicWalk 下台阶 (纯延时)
P3S_CENTER_2 = 5        # 二次居中：左旋搜索 → 右旋搜索 → 循线对齐
P3S_DONE = 6            # Phase 3 完成


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
# 统一黑线检测器 (合并 track_and_control.py + step.py)
# ============================================================
class LineDetector:
    """黑线检测 + 白线横切检测 + 黑色占比"""

    def __init__(self, black_threshold=80, min_area=200.0, min_width=0,
                 white_threshold=180, min_white_gap=6,
                 white_bgr_threshold=155, white_ratio=0.30):
        self.black_threshold = black_threshold
        self.white_threshold = white_threshold
        self.min_white_gap = min_white_gap
        self.min_area = min_area
        self.min_width = min_width
        self.avg_area = 800.0
        self.white_bgr_threshold = white_bgr_threshold
        self.white_ratio_threshold = white_ratio
        # True=合格候选中选外接矩形最宽(最粗)的线, 默认 False 选面积最大。
        # 场地存在"主粗线 + 细线"时开启, 只跟最粗的主线, 避免循到细线 (当前仅 Phase 1)
        self.prefer_thickest = False

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
        best_right_x = 0  # 最佳轮廓最右端 x 坐标
        largest_area = 0.0
        touches_left = False
        touches_right = False

        # 收集合格候选 (宽度/面积过滤后), 再按策略选取:
        #   默认: 面积最大;  prefer_thickest=True: 外接矩形最宽 (最粗的线)
        candidates = []  # (bw, area, cx, cy, cnt)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            _x, _y, bw, _bh = cv2.boundingRect(cnt)
            # 宽度过滤：细线的外接矩形宽度远小于真正的黑线
            if self.min_width > 0 and bw < self.min_width:
                continue
            if area > self.min_area:
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    candidates.append((
                        bw,
                        area,
                        int(M["m10"] / M["m00"]),
                        int(M["m01"] / M["m00"]) + roi_top,
                        cnt,
                    ))
        if candidates:
            if self.prefer_thickest:
                _, largest_area, best_cx, best_cy, best_cnt = max(
                    candidates, key=lambda c: c[0])
            else:
                _, largest_area, best_cx, best_cy, best_cnt = max(
                    candidates, key=lambda c: c[1])
            found = True
            best_right_x = max(pt[0][0] for pt in best_cnt)
            for pt in best_cnt:
                if pt[0][0] <= 2:
                    touches_left = True
                if pt[0][0] >= w - 3:
                    touches_right = True
        significant_count = sum(1 for cnt in contours
                                if cv2.contourArea(cnt) > 300)
        if found:
            offset = float(img_center_x - best_cx) / img_center_x
            self.avg_area = self.avg_area * 0.85 + largest_area * 0.15
            self.best_right_x = best_right_x  # 提供给外部对齐使用
        else:
            offset = 0.0
        return (found, offset, best_cx, best_cy, largest_area,
                touches_left, touches_right, significant_count)

    def detect_white_line_cross(self, gray_frame, color_frame=None):
        """检测白线横切（双模式）"""
        h, w = gray_frame.shape
        roi_top = h * 2 // 3
        roi_h = h - roi_top
        if roi_h < 20:
            return False
        center_x = w // 2

        # 模式1: 直接检测白色像素
        if color_frame is not None:
            roi_color = color_frame[roi_top:h, :]
            b, g, r = cv2.split(roi_color)
            bright_mask = (b > self.white_bgr_threshold) & \
                          (g > self.white_bgr_threshold) & \
                          (r > self.white_bgr_threshold)
            white_mask = bright_mask.astype(np.uint8) * 255
            half_win = 70
            left = max(0, center_x - half_win)
            right = min(w, center_x + half_win)
            win_w = right - left
            row_white = np.count_nonzero(white_mask[:, left:right], axis=1)
            white_ratio = row_white.astype(float) / max(win_w, 1)
            white_line_rows = white_ratio > self.white_ratio_threshold
            segments = []
            in_seg = False
            seg_start = 0
            for r in range(roi_h):
                if white_line_rows[r] and not in_seg:
                    in_seg = True
                    seg_start = r
                elif not white_line_rows[r] and in_seg:
                    in_seg = False
                    h_seg = r - seg_start
                    if h_seg >= self.min_white_gap:
                        segments.append((seg_start, r, h_seg))
            if in_seg:
                h_seg = roi_h - seg_start
                if h_seg >= self.min_white_gap:
                    segments.append((seg_start, roi_h, h_seg))
            if segments:
                best = max(segments, key=lambda s: s[2])
                gs, ge, gh = best
                margin = int(roi_h * 0.15)
                if gs > margin and ge < roi_h - margin:
                    return True

        # 模式2: 黑线投影间隙
        _, black_binary = cv2.threshold(
            gray_frame, self.black_threshold, 255, cv2.THRESH_BINARY_INV)
        roi_black = black_binary[roi_top:h, :]
        half_win = 50
        left = max(0, center_x - half_win)
        right = min(w, center_x + half_win)
        row_black = np.count_nonzero(roi_black[:, left:right], axis=1)
        kernel = np.ones(3) / 3.0
        row_black_smooth = np.convolve(row_black, kernel, mode='same')
        max_black = np.max(row_black_smooth)
        if max_black < 5:
            return False
        gap_threshold = max(2.0, max_black * 0.05)
        gap_segments = []
        in_gap = False
        gap_start = 0
        for r in range(roi_h):
            is_gap = row_black_smooth[r] < gap_threshold
            if is_gap and not in_gap:
                in_gap = True
                gap_start = r
            elif not is_gap and in_gap:
                in_gap = False
                if r - gap_start >= self.min_white_gap:
                    gap_segments.append((gap_start, r, r - gap_start))
        if in_gap and roi_h - gap_start >= self.min_white_gap:
            gap_segments.append((gap_start, roi_h, roi_h - gap_start))
        margin = int(roi_h * 0.20)
        for gs, ge, gh in gap_segments:
            if gs > margin and ge < roi_h - margin:
                return True
        return False

    def get_black_ratio(self, gray_frame):
        """计算画面中黑色像素占比"""
        h, w = gray_frame.shape
        _, binary = cv2.threshold(gray_frame, self.black_threshold, 255,
                                   cv2.THRESH_BINARY_INV)
        black_pixels = cv2.countNonZero(binary)
        ratio = black_pixels / binary.size
        return ratio


# ============================================================
# 红圆检测器 (D435i, 参考红圆对准.py)
# ============================================================
class RedCircleDetector:
    """在 D435i 图像中检测红色圆形靶心"""

    def __init__(self):
        self._frame_h = 0
        self._frame_w = 0

    def detect(self, frame: np.ndarray):
        """返回 (found, debug_info)
        debug_info: {"mask": np.ndarray, "num_contours": int,
                       "max_area_ratio": float, "max_circularity": float}"""
        self._frame_h, self._frame_w = frame.shape[:2]
        frame_area = self._frame_h * self._frame_w

        blurred = cv2.GaussianBlur(frame, RED_BLUR_KERNEL, 0)
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, RED_HSV_LOWER1, RED_HSV_UPPER1)
        mask2 = cv2.inRange(hsv, RED_HSV_LOWER2, RED_HSV_UPPER2)
        mask = cv2.bitwise_or(mask1, mask2)

        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (RED_MORPH_KERNEL, RED_MORPH_KERNEL))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        debug = {"mask": mask, "num_contours": len(contours),
                 "max_area_ratio": 0.0, "max_circularity": 0.0, "found": False}

        if not contours:
            return False, debug

        best_circularity = 0.0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            area_ratio = area / frame_area
            if area_ratio < RED_AREA_MIN:
                continue
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter ** 2)
            if area_ratio > debug["max_area_ratio"]:
                debug["max_area_ratio"] = area_ratio
            if circularity > best_circularity:
                best_circularity = circularity
            if circularity >= RED_CIRCULARITY_THRESH:
                debug["found"] = True

        debug["max_circularity"] = best_circularity
        return debug["found"], debug


# ============================================================
# 机械臂控制器适配器: 复用 完整.py 已有的单实例 DDS 通道
# ============================================================
class _ArmAdapter:
    """把 IntegratedMission 已有的机械臂控制层 (self._arm_*) 包装成
    各机械臂模块 (中转放置/左右放置) 期望的 D1DirectController 兼容接口。

    关键: 复用同一发布器/订阅器, 不再每个模块新建 DDS 控制器 ——
    集成运行时只存在一套 arm_Command / current_servo_angle 通道, 避免卡顿。
    """

    def __init__(self, mission):
        self._m = mission

    @property
    def current_angles(self):
        return list(self._m._arm_current_angles)

    @property
    def is_connected(self):
        return True  # 已在 __init__ 确认上电并等待到角度数据

    def enable(self):
        return True  # 已在 __init__ 完成使能

    def smooth_move(self, target_angles, duration=2.0, steps=30):
        """复用 完整.py 的插值平滑移动 (不新建 DDS)"""
        self._m._arm_interpolate_to(list(target_angles), steps=steps,
                                    step_delay=duration / max(steps, 1), wait=False)

    def wait_until_reached(self, target_angles, tolerance=5.0, timeout=30.0,
                           settle=0.2, check_interval=0.1):
        """轮询角度反馈到位 (检查全部 7 关节)"""
        self._m._arm_wait_for_angles(list(target_angles), tolerance=tolerance,
                                     timeout=min(timeout, 8.0))
        time.sleep(settle)
        return True


# ============================================================
# Phase 1 主控类
# ============================================================
class IntegratedMission:
    """Go2 Phase 1-8 全流程: 黑线循迹 + 白线检测 → 单次前跳 → ... → Phase 8"""

    def __init__(self, network_interface="", action_mode=1):
        # ---- 共享命令 ----
        self._cmd_lock = threading.Lock()
        self._target_vx = 0.0
        self._target_vy = 0.0
        self._target_vyaw = 0.0

        # ---- 机器人状态 ----
        self._robot_state = None
        self._robot_state_lock = threading.Lock()

        # ---- 动作模式 ----
        self._action_mode = action_mode

        # ---- 网络接口 (供子进程使用) ----
        self._network_interface = network_interface

        # ---- 运行标志 ----
        self._running = True
        self._control_running = True
        self._init_done = False     # 初始化完成标志，防止控制线程提前发指令

        # ---- 检测器 ----
        self._detector = LineDetector(
            black_threshold=P1_THRESHOLD,
            min_area=P1_MIN_AREA,
            min_width=P1_MIN_WIDTH,
            white_threshold=P1_WHITE_BRIGHTNESS,
            min_white_gap=P1_WHITE_GAP_MIN,
            white_bgr_threshold=P1_WHITE_BGR_THRESH,
            white_ratio=P1_WHITE_LINE_RATIO,
        )
        self._pid = PIDController(
            kp=P1_PID_KP, ki=P1_PID_KI, kd=P1_PID_KD,
            output_min=-P1_PID_MAX_YAW, output_max=P1_PID_MAX_YAW,
            integral_min=-P1_PID_INTEGRAL_MAX, integral_max=P1_PID_INTEGRAL_MAX,
        )

        # ---- 摄像头 (USB Live camera, /dev/video0, OpenCV V4L2) ----
        self._cap = None
        self._camera_on = False  # 摄像头是否正在运行（跳跃期间关闭）
        self._read_fail_count = 0  # read() 连续失败计数 (用于自动重启摄像头)

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

        self._audio = AudioClient()
        self._audio.SetTimeout(5.0)
        self._audio.Init()
        print("[INIT] AudioClient 初始化完成")

        # 前照灯控制 (通过 VuiClient)
        self._vui = VuiClient()
        self._vui.SetTimeout(5.0)
        self._vui.Init()
        print("[INIT] VuiClient 初始化完成")

        # D435i RealSense 深度相机 (用于红圆检测)
        self._d435i_pipeline = None
        self._d435i_started = False
        self._d435i_preview = None   # 供主线程显示的预览帧
        self._d435i_mask = None      # 供主线程显示的 HSV mask 调试帧
        self._d435i_last_frame = None  # 红圆线程最新彩色帧 (兜底, 避免重开摄像头)
        self._d435i_capture_pending = False  # 一次性"停稳后新帧"请求标志
        self._d435i_capture_frame = None     # 停稳后捕获帧 (OCR 专用, 保证是停车后画面)

        # Phase 4 OCR 平台识别结果 (1号平台/2号平台, None=未识别)
        # Phase 7 据此决定放物方向 (回退 COMBO_SELECT)
        self._ocr_platform = None
        self._ocr_confidence = 0.0

        # 红圆检测器
        self._red_detector = RedCircleDetector()

        print(f"[INIT] 订阅状态主题: {TOPIC_HIGHSTATE}")
        self._state_suber = ChannelSubscriber(TOPIC_HIGHSTATE, SportModeState_)
        self._state_suber.Init(self._on_high_state, 10)

        # 机械臂角度订阅
        self._arm_current_angles = [0.0] * 7
        self._arm_angle_sub = ChannelSubscriber("current_servo_angle", PubServoInfo_)
        self._arm_angle_sub.Init(self._on_arm_angle, 10)
        print("[INIT] 机械臂角度订阅已初始化")

        # 机械臂控制发布器
        self._arm_pub = ChannelPublisher("rt/arm_Command", ArmString_)
        self._arm_pub.Init()
        self._arm_seq = 0
        print("[INIT] 机械臂发布器已初始化")

        # 等待角度数据，检测是否已上电
        print("[ARM] 等待舵机角度数据...")
        waited_arm = 0
        while all(abs(a) < 0.1 for a in self._arm_current_angles) and waited_arm < 30:
            time.sleep(0.1)
            waited_arm += 1
        arm_already_on = not all(abs(a) < 0.1 for a in self._arm_current_angles)
        if arm_already_on:
            print(f"[ARM] 检测到已上电，跳过使能 "
                  f"(当前角度: {[round(a, 1) for a in self._arm_current_angles]})")
        else:
            print("[ARM] 舵机未上电，执行使能...")
            self._arm_enable()
            # 使能后重新等待角度数据
            waited_arm = 0
            while all(abs(a) < 0.1 for a in self._arm_current_angles) and waited_arm < 30:
                time.sleep(0.1)
                waited_arm += 1
            if not all(abs(a) < 0.1 for a in self._arm_current_angles):
                print(f"[ARM] 使能后角度: {[round(a, 1) for a in self._arm_current_angles]}")

        # 进入"夹住走"默认姿态，保持关节上力
        self._arm_set_angles(ARM_ACTIONS["夹住走"])
        self._arm_wait_for_angles(ARM_ACTIONS["夹住走"])
        time.sleep(0.3)
        print("[ARM] 默认姿态: 夹住走")

        print("[INIT] 等待首帧机器人状态...")
        waited = 0
        while self._robot_state is None and waited < 30:
            time.sleep(0.1)
            waited += 1
        if self._robot_state is None:
            print("[WARN] 未收到机器人状态，里程计数据将不可用")

    # ================================================================
    # 机器人状态
    # ================================================================
    def _on_high_state(self, msg):
        with self._robot_state_lock:
            self._robot_state = msg

    def _get_yaw(self):
        with self._robot_state_lock:
            if self._robot_state is None:
                return 0.0
            return float(self._robot_state.imu_state.rpy[2])

    def _get_position(self):
        with self._robot_state_lock:
            if self._robot_state is None:
                return (0.0, 0.0, 0.0)
            p = self._robot_state.position
            return (float(p[0]), float(p[1]), float(p[2]))

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
        time.sleep(0.1)  # 短暂等待，确保 sport 接口就绪
        period = 1.0 / CTRL_HZ
        while self._control_running:
            if self._init_done:
                vx, vy, vyaw = self._get_command()
                self._sport.Move(vx, vy, vyaw)
            time.sleep(period)
        print("[CTRL] 控制线程退出")

    # ================================================================
    # 机器人初始化 (仅一次)
    # ================================================================
    def _init_robot(self):
        print("[INIT] SpeedLevel(1)...")
        self._sport.SpeedLevel(1)
        time.sleep(1.0)
        print("[INIT] ClassicWalk(True)...")
        self._sport.ClassicWalk(True)
        time.sleep(1.0)
        print("[INIT] Move(0,0,0) 锁定位置...")
        self._sport.Move(0.0, 0.0, 0.0)

    # ================================================================
    # 摄像头管理（启动 / 暂停 / 重启）
    # ================================================================
    def _start_camera(self, retries: int = 5, width: int = None):
        """启动 USB Live camera (OpenCV V4L2, 自动检测设备索引, 支持重试)

        Args:
            retries: 重试次数
            width:  覆盖 FRAME_WIDTH (None=使用默认 640), Phase 6 后可用 848 加宽视野
        """
        target_w = width if width is not None else FRAME_WIDTH
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
                continue  # 没找到，重试
            # 尝试 MJPG，失败则用默认格式
            if not self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG')):
                print("[CAM] MJPG 不可用，使用默认像素格式")
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            self._cap.set(cv2.CAP_PROP_FPS, FPS)
            self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
            self._cap.set(cv2.CAP_PROP_EXPOSURE, CAMERA_EXPOSURE)
            self._camera_on = True
            print(f"[CAM] USB Live camera 已启动 "
                  f"({int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
                  f"{int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})")
            return
        raise RuntimeError("无法打开 USB Live camera (尝试了 /dev/video0,1,2,8)")

    def _stop_camera(self):
        """跳跃前暂停摄像头，释放 USB 带宽，避免丢帧卡顿"""
        if self._cap and self._camera_on:
            try:
                self._cap.release()
                self._camera_on = False
                print("[CAM] USB Live camera 已暂停（跳跃期间）")
            except Exception as e:
                print(f"[CAM] 暂停摄像头异常: {e}")

    def _camera_read(self, max_fail: int = 30):
        """读取一帧 USB 摄像头；read() 连续失败达到阈值时自动重启摄像头。

        背景: USB 摄像头掉线/重新枚举 (如 RealSense D435i 共用 USB 总线触发
        复位) 会让 V4L2 句柄失效, read() 返回 ENODEV。旧逻辑 `if not ret: continue`
        会永久空转且不刹车, 本方法负责自愈并停车。

        注意: `_camera_on` 表示"应处于工作状态" (跳跃暂停时由 _stop_camera 置 False);
        `_cap` 为实际设备句柄, 失效时置 None 触发重新枚举。跳跃期间本方法直接返回
        (False, None), 不触发重开, 不影响 Phase 1/8 的跳跃暂停流程。
        """
        if not self._camera_on:
            return False, None
        if self._cap is None:
            # 设备丢失: 持续重试重开 (成功前每帧调用一次, _start_camera 内部限流)
            self._reopen_camera()
            return False, None
        ret, color_img = self._cap.read()
        if ret:
            self._read_fail_count = 0
            return True, color_img
        self._read_fail_count += 1
        if self._read_fail_count >= max_fail:
            self._read_fail_count = 0
            print(f"[CAM] read() 连续失败 {max_fail} 次 -> 停车并重启摄像头")
            self.set_command(0.0, 0.0, 0.0)   # 摄像头失效期间不允许盲走
            self._restart_camera()
        return False, None

    def _restart_camera(self):
        """强制释放旧 V4L2 句柄并重新打开 (read 连续失败后恢复)。

        保持 `_camera_on=True`: 重开失败时 `_cap` 仍为 None, 后续 _camera_read
        会继续调用 _reopen_camera 重试, 直到设备恢复。
        """
        try:
            if self._cap is not None:
                self._cap.release()
        except Exception as e:
            print(f"[CAM] 释放旧摄像头异常: {e}")
        self._cap = None
        time.sleep(0.3)   # 等待 USB 设备重新枚举
        self._reopen_camera()

    def _reopen_camera(self):
        """尝试重新打开摄像头 (设备丢失后自愈)。失败时静默, 下次读帧继续重试。"""
        try:
            self._start_camera(retries=2)
        except Exception as e:
            print(f"[CAM] 重新打开摄像头失败: {e}")

    # ================================================================
    # 步态切换
    # ================================================================
    def _switch_to_classic(self):
        # 先清零目标速度，让控制线程发 Move(0,0,0)，确保机器人完全静止再切步态
        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.15)
        self._sport.StopMove()
        time.sleep(0.3)
        self._sport.ClassicWalk(True)
        time.sleep(0.5)
        print("[GAIT] 切换经典步态 ClassicWalk")

    # ================================================================
    # 机械臂控制 (来自 Arm.py)
    # ================================================================
    def _arm_send(self, funcode: int, data: dict = None):
        self._arm_seq += 1
        cmd = {"seq": self._arm_seq, "address": 1, "funcode": funcode}
        if data:
            cmd["data"] = data
        self._arm_pub.Write(ArmString_(json.dumps(cmd, ensure_ascii=False)))

    def _on_arm_angle(self, msg):
        """机械臂角度回调"""
        self._arm_current_angles = [
            msg.servo0_data_, msg.servo1_data_, msg.servo2_data_,
            msg.servo3_data_, msg.servo4_data_, msg.servo5_data_,
            msg.servo6_data_,
        ]

    def _arm_set_angles(self, angles: list):
        self._arm_send(2, {
            "mode": 1,
            "angle0": angles[0], "angle1": angles[1], "angle2": angles[2],
            "angle3": angles[3], "angle4": angles[4], "angle5": angles[5],
            "angle6": angles[6],
        })

    def _arm_enable(self):
        """使能机械臂关节 (funcode=5, mode=0)"""
        print("[ARM] 使能关节...")
        self._arm_send(5, {"mode": 0})
        time.sleep(1.0)

    def _arm_wait_for_angles(self, target_angles, tolerance=2.0, timeout=5.0,
                              ignore_servos=None):
        """等待舵机到达目标角度

        Args:
            target_angles: 7元素列表，目标角度(度)
            tolerance: 允许的角度误差(度)，默认 ±2°
            timeout: 超时时间(秒)
            ignore_servos: 跳过的舵机索引列表，如 [6] 忽略夹爪
        """
        skip = set(ignore_servos or [])
        start = time.time()
        target = list(target_angles)
        while time.time() - start < timeout:
            all_reached = True
            for i in range(7):
                if i in skip:
                    continue
                if abs(self._arm_current_angles[i] - target[i]) > tolerance:
                    all_reached = False
                    break
            if all_reached:
                print(f"[ARM] 舵机到达目标 (耗时 {time.time() - start:.2f}s)")
                return True
            time.sleep(0.05)
        # 超时 — 报告未到达的舵机 (跳过 ignore 的)
        print(f"[ARM] ⚠ 舵机超时({timeout}s):")
        for i in range(7):
            if i in skip:
                continue
            diff = abs(self._arm_current_angles[i] - target[i])
            if diff > tolerance:
                print(f"  servo{i}: 当前={self._arm_current_angles[i]:.1f}° "
                      f"目标={target[i]:.1f}° Δ={diff:.1f}°")
        return False

    def _arm_interpolate_to(self, target_angles, steps=3, step_delay=1.0,
                            wait=True):
        """从当前舵机角度线性插值到目标姿态，分步执行

        Args:
            target_angles: 7元素列表，目标角度(度)
            steps: 插值步数，默认3
            step_delay: 每步间等待时间(秒)，默认1.0
            wait: 是否等待舵机到达目标角度，默认True
        """
        start_angles = list(self._arm_current_angles)
        print(f"[ARM] 插值移动: "
              f"{[round(a,1) for a in start_angles]} -> "
              f"{[round(a,1) for a in target_angles]} ({steps}步)")
        for i in range(1, steps + 1):
            t = i / steps
            interp = [start_angles[j] + (target_angles[j] - start_angles[j]) * t
                      for j in range(7)]
            print(f"[ARM] 第{i}/{steps}步: {[round(a,1) for a in interp]}")
            self._arm_set_angles(interp)
            if wait:
                self._arm_wait_for_angles(interp)
            time.sleep(step_delay)

    def _arm_interpolate_to_action(self, action_name, steps=3, step_delay=1.0,
                                   wait=True):
        """按 ARM_ACTIONS 名称插值移动到目标姿态"""
        self._arm_interpolate_to(ARM_ACTIONS[action_name], steps, step_delay, wait)

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
    # Phase 7 放物方向: OCR 识别结果优先, 回退 COMBO_SELECT
    # ================================================================
    def _get_arm_drop_side(self):
        """返回 Phase 7 机械臂放物方向:
        Phase 4 OCR 识别到平台标志(1号/2号) → 按 OCR_PLATFORM_SIDE_MAP 决定;
        未识别/识别失败 → 回退 COMBO_SELECT (1-3=左, 4-6=右)。"""
        if getattr(self, "_ocr_platform", None) is not None:
            side = OCR_PLATFORM_SIDE_MAP.get(self._ocr_platform)
            if side:
                print(f"[P7] 放物方向: OCR 识别 {self._ocr_platform} -> 放{side}边 "
                      f"(conf={self._ocr_confidence:.2f})")
                return side
            print(f"[WARN] OCR 识别结果 {self._ocr_platform!r} 不在映射中, 回退 COMBO_SELECT")
        return "左" if COMBO_SELECT <= 3 else "右"

    # ================================================================
    # Phase 1: 黑线循迹 + 白线检测 → 前跳（跳跃时关闭摄像头）
    # ================================================================
    def _phase1_track_and_jump(self):
        print("\n" + "=" * 60)
        print("  Phase 1: 黑线循迹 + 白线检测 → 前跳 → 继续循线 → 丢线结束")
        print("=" * 60)

        # 配置 Phase 1 参数
        self._configure_detector(P1_THRESHOLD, P1_MIN_AREA, P1_MIN_WIDTH)
        self._configure_pid(P1_PID_KP, P1_PID_KI, P1_PID_KD,
                            P1_PID_MAX_YAW, P1_PID_INTEGRAL_MAX)
        # 场地存在主粗线 + 细线时, 只跟最粗的主线, 避免循到细线
        self._detector.prefer_thickest = True
        self._sport.SpeedLevel(1)

        # Phase 1 状态变量
        state = P1S_NORMAL
        state_start_time = 0.0
        line_lost_count = 0
        sharp_turn_count = 0
        turn_direction = 0
        cooldown_frames = 0
        forward_frame_count = 0
        forward_start_x = 0.0
        forward_start_y = 0.0
        rotation_start_yaw = 0.0
        rotation_frame_count = 0
        white_cross_count = 0
        jump_frame_count = 0
        jump_start_time = 0.0
        jump_triggered = False
        jump_count = 0
        self._pid.reset()
        startup_pid_pending = True

        phase1_done = False
        loop_frame = 0
        start_protect_frames = 20

        while self._running and not phase1_done:
            loop_frame += 1

            # ── 视觉检测（跳跃期间摄像头关闭，跳过帧读取）──
            if self._camera_on:
                ret, color_img = self._camera_read()
                if not ret:
                    continue
                gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)

                (found, offset, best_cx, best_cy, largest_area,
                 touches_left, touches_right, sig_count) = self._detector.detect(gray)

                img_center_x = FRAME_WIDTH // 2
                is_cross = False
                is_sharp_turn = False

                if found:
                    area_spike = (largest_area > self._detector.avg_area * 3.0
                                  and self._detector.avg_area > 0)
                    multi_branch = (sig_count >= 3)
                    is_cross = (area_spike and multi_branch
                                and abs(offset) < 0.4)
                    # 以下变量仅用于急转弯检测(GO_FORWARD/ROTATING), 但该功能已禁用
                    large_offset = abs(offset) > 0.75
                    near_left = best_cx < img_center_x * 0.08
                    near_right = best_cx > img_center_x * 1.92
                    at_edge = touches_left or touches_right or near_left or near_right
                    is_sharp_turn = False  # 急转弯检测已禁用 → GO_FORWARD/ROTATING 为死代码

                # 白线检测 (仅跳前，跳后不再检测白线)
                is_white_cross = False
                if state == P1S_NORMAL and jump_count < 1 and found:
                    is_white_cross = self._detector.detect_white_line_cross(
                        gray, color_img)
                    if is_white_cross:
                        white_cross_count += 1
                    else:
                        white_cross_count = max(0, white_cross_count - 1)
            else:
                # 摄像头关闭中（跳跃期间），跳过视觉检测，仅维护状态机时序
                found = False
                offset = 0.0
                time.sleep(0.01)

            if cooldown_frames > 0:
                cooldown_frames -= 1

            # ---- Phase 1 状态机 ----
            if state == P1S_NORMAL:
                # 摄像头重启中（刚跳完），等待摄像头就绪
                if not self._camera_on:
                    self.set_command(0.0, 0.0, 0.0)
                    continue

                if loop_frame <= start_protect_frames:
                    self.set_command(0.0, 0.0, 0.0)
                    if loop_frame == start_protect_frames:
                        print("[P1] 启动保护期结束，开始正常巡线")
                    continue

                # 首个可信检测值只用于初始化 PID，避免启动时 D 项瞬间冲击。
                if startup_pid_pending and found and abs(offset) <= 0.80:
                    self._pid.reset(initial_error=offset)
                    startup_pid_pending = False

                if abs(offset) > 0.80:
                    line_lost_count += 1
                    self._pid.reset()
                    self.set_command(0.0, 0.0, 0.0)
                    continue
                else:
                    line_lost_count = 0

                # 跳后丢线 -> 原地站立, Phase 1 结束
                if jump_count >= 1 and not found:
                    print(f"[DETECT] 跳后黑线丢失！-> 原地站立结束")
                    state = P1S_DONE
                    self.set_command(0.0, 0.0, 0.0)
                    self._sport.StopMove()
                elif (jump_count < 1 and white_cross_count >= P1_WHITE_CROSS_CONFIRM
                        and cooldown_frames == 0):
                    print(f"[DETECT] 白线横切！连续 {white_cross_count} 帧 -> 直接前跳")
                    state = P1S_JUMP
                    white_cross_count = 0
                    jump_frame_count = 0
                    jump_start_time = time.time()
                    jump_triggered = False
                    self.set_command(0.0, 0.0, 0.0)
                elif not found:
                    line_lost_count += 1
                    self._pid.reset()
                    if line_lost_count < 30:
                        self.set_command(0.05, 0.0, 0.0)
                    else:
                        search_yaw = 0.3 if line_lost_count % 120 < 60 else -0.3
                        self.set_command(0.0, 0.0, search_yaw)
                elif jump_count < 1 and is_sharp_turn and cooldown_frames == 0:
                    sharp_turn_count += 1
                    if sharp_turn_count >= P1_SHARP_TURN_THRESHOLD:
                        state = P1S_GO_FORWARD
                        sharp_turn_count = 0
                        turn_direction = 1 if offset > 0 else -1
                        forward_frame_count = 0
                        fx, fy, _ = self._get_position()
                        forward_start_x = fx
                        forward_start_y = fy
                        direction_name = "LEFT" if turn_direction > 0 else "RIGHT"
                        print(f"[STATE] -> GO_FORWARD dir={direction_name}")
                        self.set_command(0.5, 0.0, 0.0)
                    else:
                        yaw = self._pid.update(offset, CTRL_DT)
                        self.set_command(P1_BASE_SPEED, 0.0, yaw)
                elif is_cross:
                    line_lost_count = 0
                    self._pid.reset()
                    self.set_command(0.35, 0.0, 0.0)
                else:
                    sharp_turn_count = 0
                    line_lost_count = 0
                    yaw = self._pid.update(offset, CTRL_DT)
                    if abs(offset) > 0.5:
                        vx = P1_BASE_SPEED * 0.6
                    else:
                        vx = P1_BASE_SPEED
                    self.set_command(vx, 0.0, yaw)

            elif state == P1S_GO_FORWARD:
                forward_frame_count += 1
                fx, fy, _ = self._get_position()
                dx = fx - forward_start_x
                dy = fy - forward_start_y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist >= P1_FORWARD_DIST or forward_frame_count >= 80:
                    state = P1S_ROTATING
                    rotation_start_yaw = self._get_yaw()
                    rotation_frame_count = 0
                    vyaw = 1.0 if turn_direction > 0 else -1.0
                    self.set_command(0.0, 0.0, vyaw)
                    direction_name = "LEFT" if turn_direction > 0 else "RIGHT"
                    print(f"[STATE] -> ROTATING dir={direction_name} "
                          f"dist={int(dist * 100)}cm")
                else:
                    self.set_command(0.5, 0.0, 0.0)

            elif state == P1S_ROTATING:
                rotation_frame_count += 1
                vyaw = 1.0 if turn_direction > 0 else -1.0
                self.set_command(0.0, 0.0, vyaw)
                current_yaw = self._get_yaw()
                yaw_diff = self._normalize_angle(current_yaw - rotation_start_yaw)
                if (abs(yaw_diff) >= P1_ROTATION_ANGLE
                        or rotation_frame_count >= 80):
                    state = P1S_NORMAL
                    line_lost_count = 0
                    sharp_turn_count = 0
                    cooldown_frames = P1_COOLDOWN_FRAMES
                    self._pid.reset()
                    self.set_command(0.0, 0.0, 0.0)

            elif state == P1S_JUMP:
                elapsed = time.time() - jump_start_time
                t_forward_end = P1_JUMP_FORWARD_DUR
                t_stop_end = t_forward_end + P1_JUMP_STOP_DUR
                t_jump_end = t_stop_end + 2.5
                if elapsed < t_forward_end:
                    # 起跳前先前进 P1_JUMP_FORWARD_DUR=0.2s（摄像头保持开启）
                    self.set_command(P1_JUMP_FORWARD_SPEED, 0.0, 0.0)
                elif elapsed < t_stop_end:
                    # 前冲完成，关闭摄像头准备起跳，释放 USB 带宽避免丢帧
                    if self._camera_on:
                        self._stop_camera()
                    self.set_command(0.0, 0.0, 0.0)
                    if not jump_triggered and elapsed >= t_forward_end + 0.1:
                        # 确保机器人完全静止后再起跳
                        self._sport.StopMove()
                elif elapsed < t_jump_end:
                    if not jump_triggered:
                        jump_count += 1
                        code = self._sport.FrontJump()
                        jump_triggered = True
                        if code == 0:
                            print(f"[JUMP] FrontJump() OK")
                        else:
                            print(f"[JUMP] FrontJump() 失败, code={code}")
                    self.set_command(0.0, 0.0, 0.0)
                else:
                    # 跳跃完成，重启摄像头（释放旧句柄+等USB重新枚举，避免摄像头崩溃），继续循线直到丢线
                    state = P1S_NORMAL
                    cooldown_frames = P1_COOLDOWN_FRAMES
                    self._pid.reset()
                    self._switch_to_classic()
                    self._restart_camera()
                    print(f"[STATE] -> NORMAL (跳跃完成, 重启摄像头, 继续循线, 丢线后结束)")

            elif state == P1S_DONE:
                self.set_command(0.0, 0.0, 0.0)
                phase1_done = True

            # ---- 可视化（仅在摄像头开启时渲染）----
            if self._camera_on:
                display = color_img.copy()
                if found:
                    cv2.circle(display, (best_cx, best_cy), 6, (0, 255, 0), -1)
                cv2.line(display, (img_center_x, display.shape[0]),
                         (img_center_x, display.shape[0] - 40), (255, 0, 0), 2)
                roi_top = display.shape[0] * 2 // 3
                cv2.line(display, (0, roi_top), (display.shape[1], roi_top),
                         (0, 255, 255), 1)
                state_names = {P1S_NORMAL: "NORMAL", P1S_GO_FORWARD: "GO_FORWARD",
                               P1S_ROTATING: "ROTATING",
                               P1S_JUMP: "JUMP", P1S_DONE: "DONE"}
                cv2.putText(display, f"Phase1 {state_names[state]} jumps={jump_count}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                vx, _, vyaw = self._get_command()
                cv2.putText(display, f"vx={vx:.2f} vyaw={vyaw:+.2f}",
                            (10, display.shape[0] - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)
                cv2.imshow("Integrated Mission", display)

            # 按键检测始终运行，保证随时可退出
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                self._running = False
                return

            if loop_frame % 30 == 0 and state == P1S_NORMAL:
                print(f"[P1] offset={offset:+.3f} found={found}")

        # 恢复默认选区 (后续 Phase 3/5/6/7/8 循线仍按面积最大取线)
        self._detector.prefer_thickest = False
        print("[Phase1] 完成")

    # ================================================================
    # Phase 2 — 迷宫定序运动：前进 2s → TOF 迷宫导航（库函数接管）
    # ================================================================
    def _maze_go_forward(self, duration: float):
        """迷宫入口前进指定时长"""
        print(f"[P2] 前进 {duration}s")
        self.set_command(MAZE_FORWARD_SPEED, 0.0, 0.0)
        time.sleep(duration)
        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.1)

    def _phase_maze(self):
        """Phase 2: 迷宫定序运动 — 保留前进 2s，然后交由 TOF 迷宫导航，结束后继续后续阶段"""
        print("\n" + "=" * 60)
        print("  Phase 2: 迷宫定序运动（前进2s → TOF 迷宫导航）")
        print("=" * 60)
        self._switch_to_classic()
        # 保留原定序序列的第一步前进（原为 7.6s，现固定 2s 后交由 TOF 导航接管）
        self._maze_go_forward(2.0)
        run_maze_navigation(self)
        print("[P2] 迷宫导航结束，继续后续阶段")

    # ================================================================
    # Phase 3: 巡线 + 黑区检测 → 上台阶(IMU姿态闭环+偏航纠偏) → 左转 → 下台阶
    # ================================================================
    def _phase3_stairs(self):
        """
        Phase 3 流程 (全部 ClassicWalk, IMU 姿态闭环上台阶):
          1. CENTER_1   — 初始居中校准（横向平移对齐黑线，超时强制进入下一步）
          2. LINE_TRACK  — PID 巡线 + 边跑边记录偏航角取均值 + 黑色占比检测
          3. STAIRS_UP   — 上台阶: 俯仰监测 + 偏航角实时纠偏
          4. TURN_LEFT   — 台阶上原地左转（IMU 闭环）+ 顶部微调
          5. STAIRS_DOWN — ClassicWalk 直走下台阶（纯延时）
          6. CENTER_2    — 二次居中：左旋搜索 → 右旋搜索 → 循线对齐
        """

        print("\n" + "=" * 60)
        print("  Phase 3: 巡线 + 黑区检测 + 台阶 (IMU 姿态闭环)")
        print("=" * 60)

        # ── 配置 Phase 3 专用检测器和 PID 参数 ──
        self._configure_detector(P3_BLACK_THRESHOLD, P3_MIN_AREA)
        self._configure_pid(P3_PID_KP, P3_PID_KI, P3_PID_KD,
                            P3_PID_MAX_YAW, P3_PID_INTEGRAL_MAX)
        self._sport.SpeedLevel(2)  # 台阶需要更高扭矩
        # SpeedLevel 会切走经典步态，必须按其他 Phase 的模式在之后复位 ClassicWalk
        self._switch_to_classic()
        print("[P3] 速度档位 = 2（经典步态）")

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
                        # 原地停 1s，然后先后退，再左平移，再左转
                        time.sleep(0.5)
                        print(f"[P3] 后退 {P3_TOP_BACK_DUR}s...")
                        self.set_command(-P3_TOP_BACK_SPEED, 0, 0)
                        time.sleep(P3_TOP_BACK_DUR)
                        self.set_command(0, 0, 0)
                        time.sleep(0.15)
                        print(f"[P3] 左平移 {P3_TOP_STRAFE_LEFT_DUR}s...")
                        self.set_command(0, P3_TOP_STRAFE_LEFT_SPEED, 0)
                        time.sleep(P3_TOP_STRAFE_LEFT_DUR)
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
                        # 爬升中 → 全速 + 偏航纠偏
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
                        state_start_time = time.time()
                        center2_phase = 0
                        center2_start_yaw = self._get_yaw()
                        self._pid.reset()

                time.sleep(CTRL_DT)
                continue

            # ================================================================
            # 视觉处理状态 — 需要 USB 摄像头帧
            #   CENTER_1:   初始居中
            #   LINE_TRACK: PID 巡线 + 偏航角采样 + 黑色占比检测
            #   CENTER_2:   二次居中（左旋搜索 → 右旋搜索 → 循线对齐）
            # ================================================================
            ret, color_img = self._camera_read()
            if not ret:
                time.sleep(0.01)
                continue

            gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
            (found, offset, best_cx, best_cy, largest_area,
             _touches_left, _touches_right, _sig_count) = self._detector.detect(gray)

            # ---- Phase 3 状态机 ----
            if state == P3S_CENTER_1:
                # ── 初始居中：横向平移对齐黑线，超时强制进入下一步 ──
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
                if time.time() - state_start_time > P3_CENTER2_TIMEOUT:
                    print(f"[P3] 二次居中超时 ({P3_CENTER2_TIMEOUT}s)，Phase 3 结束")
                    self.set_command(0, 0, 0)
                    time.sleep(0.3)
                    state = P3S_DONE
                    continue
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
            cv2.imshow("Integrated Mission", display)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                self._running = False
                return

            time.sleep(CTRL_DT)


    # ================================================================
    # 循线黑线检测: 画面多个黑色区域时优先取最左 (Phase 4 全程 / Phase 5 快跑段后)
    # ================================================================
    def _detect_line_prefer_left(self, gray_frame):
        """与 LineDetector.detect() 相同的黑线提取流程, 但画面存在多个黑色区域时
        优先取质心最靠左的一个 —— 避免把画面右侧的黑色物块当成黑线带偏 PID。

        Returns:
            (found, offset, cx, cy)
        """
        h, w = gray_frame.shape
        blurred = cv2.GaussianBlur(gray_frame, (5, 5), 0)
        _, binary = cv2.threshold(blurred, P1_THRESHOLD, 255,
                                   cv2.THRESH_BINARY_INV)
        roi_top = h * 2 // 3
        roi = binary[roi_top:h, :]
        contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        best = None  # (cx, cy) 质心最靠左的候选
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area <= P1_MIN_AREA:
                continue
            # 宽度过滤 (同 LineDetector: 细线外接矩形宽度 < P1_MIN_WIDTH 忽略)
            _x, _y, bw, _bh = cv2.boundingRect(cnt)
            if bw < P1_MIN_WIDTH:
                continue
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"]) + roi_top
            if best is None or cx < best[0]:
                best = (cx, cy)
        if best is None:
            return False, 0.0, 0, 0
        cx, cy = best
        offset = float(w // 2 - cx) / (w // 2)
        return True, offset, cx, cy

    # ================================================================
    # Phase 4: 机械臂"识别" → 巡线 + D435i 红圆检测 → 抓取 → 延时 → 完成
    # ================================================================
    def _phase4_arm_and_red(self):
        """Phase 4: 机械臂识别姿态(与循线并行) → 循线前进 → D435i 检测红圆 → 3s倒计时 → 左平移 → 抓取 → 延时5s → 完成"""
        print("\n" + "=" * 60)
        print("  Phase 4: 机械臂识别 → 巡线 + 红圆检测 → 停止")
        print("=" * 60)

        # ── 机械臂识别序列动作 → 后台线程, 与循线快走并行 (不再阻塞起步) ──
        print("[P4] 启动机械臂识别序列(后台线程), 与循线快走并行...")

        def _arm_identify_seq():
            self._arm_interpolate_to_action("识别", steps=2, step_delay=0.5,
                                            wait=False)
            time.sleep(ARM_IDENTIFY_DELAY)
            print("[P4] 机械臂'识别'姿态就绪")

        arm_thread = threading.Thread(target=_arm_identify_seq, daemon=True,
                                      name="p4_arm_identify")
        arm_thread.start()

        # ── 参考 Go2.py Phase 4 配置 ──
        self._configure_detector(P1_THRESHOLD, P1_MIN_AREA)
        self._configure_pid(P1_PID_KP, P1_PID_KI, P1_PID_KD,
                            P1_PID_MAX_YAW, P1_PID_INTEGRAL_MAX)
        self._sport.SpeedLevel(1)
        self._switch_to_classic()

        # ── 巡线前重启 USB 摄像头 (释放旧 V4L2 句柄, 保证巡线画面清晰) ──
        print("[P4] 巡线前重启摄像头...")
        self._restart_camera()
        print("[P4] 摄像头已重启")

        # ── Go2.py Phase 4 风格巡线 + D435i 红圆检测 ──
        self._pid.reset()

        # 启动 D435i 红圆检测后台线程
        self._red_confirmed = False
        self._red_confirm_count = 0
        self._red_lock = threading.Lock()
        red_thread = threading.Thread(
            target=self._d435i_red_thread, daemon=True, name="d435i_red")
        red_thread.start()
        print("[P4] D435i 红圆检测线程已启动")

        # 预加载共享 OCR 识别器 (模型加载约 6s) — 在 Phase 4 快跑段开始加载,
        # 与快跑/循线并行; Phase 4 平台识别 + Phase 6 警示识别共用此模型,
        # 倒计时后识别时刻已就绪, 避免识别时现场加载
        _preload_ocr()

        # 红圆倒计时（首次检测到红圆即开始 3s 倒计时）
        red_timer_start = None
        RED_COUNTDOWN = P4_RED_COUNTDOWN  # 倒计时秒数 (顶部参数)
        fast_speed_until = 0.0    # 快跑段 (P4_BASE_SPEED) 截止时间戳, 0=尚未开始
        steady_announced = False  # 是否已打印恢复稳态速度提示

        while self._running:
            ret, color_img = self._camera_read()
            if not ret:
                time.sleep(0.01)
                continue
            gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
            # 循线黑线检测: 画面多个黑色区域时优先跟最靠左的 (避开右侧黑色物块)
            found, offset, best_cx, best_cy = \
                self._detect_line_prefer_left(gray)

            # 循线 (Go2.py Phase 4 风格)
            if not found:
                self._pid.reset()
                self.set_command(0.05, 0.0, 0.0)
            else:
                # 进入循线后前 P4_FAST_DURATION 秒以 P4_BASE_SPEED 快跑, 之后恢复稳态速度
                if fast_speed_until == 0.0:
                    fast_speed_until = time.time() + P4_FAST_DURATION
                fast_mode = time.time() < fast_speed_until
                if not fast_mode and not steady_announced:
                    steady_announced = True
                    print(f"[P4] 快跑段结束，恢复稳态速度 {P4_STEADY_SPEED} m/s")
                track_speed = P4_BASE_SPEED if fast_mode else P4_STEADY_SPEED
                yaw = self._pid.update(offset, CTRL_DT)
                vx = track_speed * 0.6 if abs(offset) > 0.5 else track_speed
                self.set_command(vx, 0.0, yaw)

            # 检查 D435i 红圆检测结果（后台线程更新）
            # 首次检测到红圆 → 开始 3s 倒计时；倒计时期间继续巡线
            with self._red_lock:
                red_seen = (self._red_confirm_count > 0)

            if red_seen and red_timer_start is None:
                red_timer_start = time.time()
                print(f"[P4] 检测到红圆！开始 {RED_COUNTDOWN}s 倒计时（继续巡线）...")
                

            if red_timer_start is not None:
                elapsed = time.time() - red_timer_start
                if elapsed >= RED_COUNTDOWN:
                    print(f"\n[P4] {RED_COUNTDOWN}s 倒计时完成 -> 站住")
                    self.set_command(0.0, 0.0, 0.0)
                    time.sleep(0.3)
                    # 切换到经典模式，确保侧移指令可正常执行 (同 Phase 7 右移前)
                    self._switch_to_classic()

                    # ── OCR 识别平台标志 (1号/2号) — 必须在左平移和机械臂抓取之前完成 ──
                    # 复用 D435i 红圆线程最新帧 (管线仍开启, 无需重开摄像头);
                    # 结果存入 self._ocr_platform, 决定 Phase 7 放物方向 (识别失败回退 COMBO_SELECT)
                    self._phase_ocr_recognize()

                    # ── 彻底关闭 D435i 红圆检测 ──
                    print("[P4] 关闭 D435i...")
                    self._stop_d435i()
                    # 关闭 D435i 预览窗口
                    with self._red_lock:
                        self._d435i_preview = None
                        self._d435i_mask = None
                    cv2.destroyWindow("D435i Red Detect")
                    cv2.destroyWindow("D435i HSV Mask")
                    # 等待后台线程退出
                    print("[P4] 等待 D435i 线程退出...")
                    time.sleep(0.3)

                    # ── 左平移 0.7s (标志识别完成后、启动抓取前) ──
                    print(f"[P4] 左平移 {P4_LEFT_STRAFE_DUR}s (速度={P4_LEFT_STRAFE_SPEED} m/s)...")
                    self.set_command(0.0, P4_LEFT_STRAFE_SPEED, 0.0)
                    time.sleep(P4_LEFT_STRAFE_DUR)
                    self.set_command(0.0, 0.0, 0.0)
                    time.sleep(0.2)

                    print("[P4] 执行机械臂动作: 识别物块")
                    arm_thread.join(timeout=3.0)   # 确保识别序列完成(通常早已结束)
                    self._arm_set_angles(ARM_ACTIONS["识别物块"])
                    self._arm_wait_for_angles(ARM_ACTIONS["识别物块"], ignore_servos=[6])

                    # ── 执行抓取 (IK + D435i深度直接集成) ──
                    self._run_pick_and_place()

                    print("[P4] Phase 4 完成")
                    break

            # 可视化
            display = color_img.copy()
            h, w = display.shape[:2]
            cv2.line(display, (w // 2, 0), (w // 2, h), (255, 0, 0), 2)
            cv2.line(display, (0, h * 2 // 3), (w, h * 2 // 3), (0, 255, 255), 2)
            if found:
                cv2.circle(display, (int(best_cx), int(best_cy)), 8, (0, 255, 0), -1)
            status_text = "Phase4 Track+Red"
            if red_timer_start is not None:
                remaining = max(0, RED_COUNTDOWN - (time.time() - red_timer_start))
                status_text += f" | COUNTDOWN:{remaining:.1f}s"
            elif red_seen:
                status_text += " | RED DETECTED"
            cv2.putText(display, status_text, (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow("Integrated Mission", display)

            # D435i 预览 + HSV mask（主线程显示）
            with self._red_lock:
                if self._d435i_preview is not None:
                    cv2.imshow("D435i Red Detect", self._d435i_preview)
                if self._d435i_mask is not None:
                    cv2.imshow("D435i HSV Mask", self._d435i_mask)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                self._running = False
                return

            time.sleep(CTRL_DT)

        print("[Phase4] 完成")

    # ================================================================
    # 停稳后新帧请求: 复用 D435i 红圆线程管线 (不开新摄像头, 避开 ~10s 硬件复位慢路径)
    # ================================================================
    def _request_ocr_frame(self, timeout: float = 1.0):
        """请求红圆线程在机器人停稳后抓取一帧新图 (保证是停车后画面, 而非循线移动中的帧)

        倒计时结束、机器人已停下后调用。红圆线程仍运行 (关 D435i 前), 收到请求后
        立即把下一帧存为一次性捕获帧; 超时未得到新帧 → 回退到连续保存的最新帧;
        两者均无 → None (调用方走现场开摄像头兜底)。
        """
        with self._red_lock:
            self._d435i_capture_pending = True
            self._d435i_capture_frame = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._red_lock:
                if self._d435i_capture_frame is not None:
                    return self._d435i_capture_frame
            time.sleep(0.02)
        # 兜底: 用连续保存的最新帧 (可能是停车前最后一帧, 仍比无帧强)
        with self._red_lock:
            last = self._d435i_last_frame
        return last if (last is not None and last.size > 0) else None

    # ================================================================
    # OCR 平台标志识别 (D435i 彩色帧): Phase 4 倒计时完成后调用,
    # 必须在左平移和机械臂抓取之前执行; 结果存入 self._ocr_platform, 决定 Phase 7 放物方向
    # ================================================================
    def _phase_ocr_recognize(self):
        """OCR 平台标志识别: 用 D435i 彩色帧识别 1号/2号平台 (决定 Phase 7 放物方向)

        图像来源优先复用 D435i 红圆线程"停稳后"新帧, 不重新开启摄像头;
        无可用帧时才兜底现场开启摄像头识别。只保留 1号平台/2号平台,
        取置信度最高者存入 self._ocr_platform / self._ocr_confidence。
        Phase 7 放物方向据此决定 (OCR_PLATFORM_SIDE_MAP: 1号=左, 2号=右);
        识别失败/超时 → self._ocr_platform=None, Phase 7 回退 COMBO_SELECT。
        与 Phase 6 共用同一识别模型 (见 _get_ocr_recognizer), 只加载一次。
        """
        print("=" * 60)
        print("  [P4] OCR 平台标志识别 (D435i 彩色帧, 1号/2号)")
        print("=" * 60)

        rec = _get_ocr_recognizer()
        if rec is None:
            print("[OCR] 识别器不可用 -> Phase 7 回退 COMBO_SELECT")
            self._ocr_platform = None
            self._ocr_confidence = 0.0
            return

        # ── 优先: 请求红圆线程在机器人停稳后抓取一帧新图, 再识别 (不开新摄像头) ──
        markers = []
        frame_src = ""
        frame = self._request_ocr_frame()
        if frame is not None:
            frame_src = "停稳后新帧"
            markers = rec.recognize_frame(frame, save=True)
            # 只保留 1号平台/2号平台 (等效 Final1 DepthOCRRecognizer.ALLOWED_MARKER_TYPES)
            markers = [m for m in markers
                       if m.category in ("1号平台", "2号平台")]
        else:
            # ── 兜底: 无可用帧时现场开启摄像头识别 (极少发生) ──
            frame_src = "现场开启摄像头"
            if rec.init_camera():
                try:
                    markers = rec.recognize_from_camera(timeout=OCR_RECOG_TIMEOUT)
                    markers = [m for m in markers
                               if m.category in ("1号平台", "2号平台")]
                finally:
                    rec.release_camera()
            else:
                print("[OCR] [ERROR] 摄像头初始化失败 -> Phase 7 回退 COMBO_SELECT")
                self._ocr_platform = None
                self._ocr_confidence = 0.0
                return

        if not markers:
            print(f"[OCR] ({frame_src}) 未识别到平台标志 -> Phase 7 回退 COMBO_SELECT")
            self._ocr_platform = None
            self._ocr_confidence = 0.0
            return

        best = max(markers, key=lambda m: m.confidence)
        self._ocr_platform = best.category
        self._ocr_confidence = best.confidence
        print(f"[OCR] ({frame_src}) 识别到平台标志: {best.category} "
              f"(置信度={best.confidence:.2f})")
        print(f"[OCR] Phase 7 将放{self._get_arm_drop_side()}边")

    # ================================================================
    # Phase 4B: 通过 PickAndPlaceController 执行抓取 (动态导入 pick_and_place.py)
    # ================================================================
    def _run_pick_and_place(self):
        """Phase 4B: D1 机械臂识别抓取 — 通过深度相机检测物块 + IK 控制机械臂抓取"""
        print("\n" + "=" * 60)
        print("  Phase 4B: D1 机械臂识别抓取 (Pick & Place)")
        print("=" * 60)

        # 保存当前信号处理器 (pick_and_place 模块导入时会覆盖)
        saved_sigint = signal.getsignal(signal.SIGINT)
        saved_sigterm = signal.getsignal(signal.SIGTERM)

        try:
            # 确保依赖路径可导入
            deps_dir = "/home/unitree/1/D1/final_code/视觉抓取"
            if deps_dir not in sys.path:
                sys.path.insert(0, deps_dir)

            # 删除字节码缓存 → 刷新导入系统 → 清除模块缓存
            cache_dir = os.path.join(deps_dir, "__pycache__")
            if os.path.isdir(cache_dir):
                for _f in os.listdir(cache_dir):
                    os.remove(os.path.join(cache_dir, _f))
                os.rmdir(cache_dir)
                print("[P4B] 已删除字节码缓存 __pycache__/")
            importlib.invalidate_caches()
            for _mod in list(sys.modules.keys()):
                if (_mod.startswith("pick_and_place") or
                    _mod.startswith("arm_ik_control") or
                    _mod.startswith("depth_camera") or
                    _mod.startswith("color_object_detector") or
                    _mod.startswith("d1_ik_solver") or
                    _mod.startswith("d1_forward_kinematics")):
                    sys.modules.pop(_mod, None)

            from pick_and_place import PickAndPlaceController

            controller = PickAndPlaceController(
                network_interface=self._network_interface,
                color_name="green",
                dry_run=False,
                show_window=True,
            )
            success = controller.run(once=True)
            controller.cleanup()

            if success:
                print("[P4B] ✓ 抓取成功!")
            else:
                print("[P4B] 抓取未完成 (物块丢失或居中失败)")

            return success

        except Exception as e:
            print(f"[P4B] ✗ 抓取失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 恢复主程序的信号处理器
            signal.signal(signal.SIGINT, saved_sigint)
            signal.signal(signal.SIGTERM, saved_sigterm)

    # ================================================================
    # Phase 5B: 通过 PickAndPlaceController 执行抓取 (动态导入 pick_and_place1.py)
    # ================================================================
    def _run_pick_and_place1(self):
        """Phase 5B: D1 机械臂识别抓取 — 通过深度相机检测物块 + IK 控制机械臂抓取"""
        print("\n" + "=" * 60)
        print("  Phase 5B: D1 机械臂识别抓取 (Pick & Place v2)")
        print("=" * 60)

        # 保存当前信号处理器 (pick_and_place1 模块导入时会覆盖)
        saved_sigint = signal.getsignal(signal.SIGINT)
        saved_sigterm = signal.getsignal(signal.SIGTERM)

        try:
            # 确保依赖路径可导入
            deps_dir = "/home/unitree/1/D1/final_code/视觉抓取"
            if deps_dir not in sys.path:
                sys.path.insert(0, deps_dir)

            # 删除字节码缓存 → 刷新导入系统 → 清除模块缓存
            cache_dir = os.path.join(deps_dir, "__pycache__")
            if os.path.isdir(cache_dir):
                for _f in os.listdir(cache_dir):
                    os.remove(os.path.join(cache_dir, _f))
                os.rmdir(cache_dir)
                print("[P5B] 已删除字节码缓存 __pycache__/")
            importlib.invalidate_caches()
            for _mod in list(sys.modules.keys()):
                if (_mod.startswith("pick_and_place") or
                    _mod.startswith("arm_ik_control") or
                    _mod.startswith("depth_camera") or
                    _mod.startswith("color_object_detector") or
                    _mod.startswith("d1_ik_solver") or
                    _mod.startswith("d1_forward_kinematics")):
                    sys.modules.pop(_mod, None)

            from pick_and_place1 import PickAndPlaceController

            controller = PickAndPlaceController(
                network_interface=self._network_interface,
                color_name="green",
                dry_run=False,
                show_window=True,
            )
            success = controller.run(once=True)
            controller.cleanup()

            if success:
                print("[P5B] ✓ 抓取成功!")
            else:
                print("[P5B] 抓取未完成 (物块丢失或居中失败)")

            return success

        except Exception as e:
            print(f"[P5B] ✗ 抓取失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 恢复主程序的信号处理器
            signal.signal(signal.SIGINT, saved_sigint)
            signal.signal(signal.SIGTERM, saved_sigterm)

    def _start_placement_async(self, func, *args):
        """在后台线程启动机械臂放置动作, 与巡线并行 (节省放物等待时间)。

        Phase 5 (中转放置) / Phase 7 (左右放置): 快跑段结束后机器人继续巡线,
        机械臂同步执行放置; 主线程在触发点(丢线/倒计时结束) join() 等待完成。
        """
        t = threading.Thread(target=func, args=args, daemon=True,
                             name="arm_placement")
        t.start()
        return t

    # ================================================================
    # Phase 5C: 通过 中转放置.py 执行丢线后放物 (预备放 → 放 → 松 → 抬)
    # ================================================================
    def _run_transfer_placement(self):
        """Phase 5C: 中转放置 — 动态导入 视觉抓取/中转放置.py 的
        run_transfer_placement() 执行 预备放 → 放 → 松 → 抬"""
        print("\n" + "=" * 60)
        print("  Phase 5C: 中转放置 (预备放 → 放 → 松 → 抬)")
        print("=" * 60)

        # 保存当前信号处理器 (中转放置 模块导入时可能覆盖)。
        # 注意: signal.signal() 只能在主线程调用, 后台线程(并行放置)时跳过保存/恢复。
        _in_main_thread = threading.current_thread() is threading.main_thread()
        saved_sigint = signal.getsignal(signal.SIGINT) if _in_main_thread else None
        saved_sigterm = signal.getsignal(signal.SIGTERM) if _in_main_thread else None

        try:
            # 确保依赖路径可导入 (模块单次导入即缓存, 不再删 pycache/刷新缓存, 提速)
            deps_dir = "/home/unitree/1/D1/final_code/视觉抓取"
            if deps_dir not in sys.path:
                sys.path.insert(0, deps_dir)

            import 中转放置

            success = 中转放置.run_transfer_placement(
                network_interface=self._network_interface,
                arm=_ArmAdapter(self),
            )
            if success == 0:
                print("[P5C] ✓ 中转放置完成!")
            else:
                print("[P5C] 中转放置返回异常码")

            return success == 0

        except Exception as e:
            print(f"[P5C] ✗ 中转放置失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 恢复主程序的信号处理器 (仅主线程; 后台线程不操作 signal)
            if _in_main_thread:
                signal.signal(signal.SIGINT, saved_sigint)
                signal.signal(signal.SIGTERM, saved_sigterm)

    # ================================================================
    # Phase 7 放物: 通过 左右放置.py 执行左右侧定点放置
    # ================================================================
    def _run_placement(self, side):
        """Phase 7 放物 — 动态导入 视觉抓取/左右放置.py 的 run_placement(side)

        Args:
            side: "左" 或 "右"
        Returns:
            bool: 是否执行成功
        """
        print("\n" + "=" * 60)
        print(f"  左右放置 (side={side}): 抬起1 → 1 → 平放 → 松开 → 抬起2 → 平")
        print("=" * 60)

        # 保存当前信号处理器 (左右放置 模块导入时可能覆盖)。
        # 注意: signal.signal() 只能在主线程调用, 后台线程(并行放置)时跳过保存/恢复。
        _in_main_thread = threading.current_thread() is threading.main_thread()
        saved_sigint = signal.getsignal(signal.SIGINT) if _in_main_thread else None
        saved_sigterm = signal.getsignal(signal.SIGTERM) if _in_main_thread else None

        try:
            # 确保依赖路径可导入 (模块单次导入即缓存, 不再删 pycache/刷新缓存, 提速)
            deps_dir = "/home/unitree/1/D1/final_code/视觉抓取"
            if deps_dir not in sys.path:
                sys.path.insert(0, deps_dir)

            import 左右放置

            success = 左右放置.run_placement(
                network_interface=self._network_interface,
                side=side,
                arm=_ArmAdapter(self),
            )
            if success == 0:
                print("[P7] ✓ 左右放置完成!")
            else:
                print("[P7] 左右放置返回异常码")

            return success == 0

        except Exception as e:
            print(f"[P7] ✗ 左右放置失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # 恢复主程序的信号处理器 (仅主线程; 后台线程不操作 signal)
            if _in_main_thread:
                signal.signal(signal.SIGINT, saved_sigint)
                signal.signal(signal.SIGTERM, saved_sigterm)

    # ================================================================
    # Phase 5: 继续循线 → 丢线后放物(中转放置.py) → 识别物块2+等10s → pick_and_place1抓取 → 左转30°
    # ================================================================
    def _phase5_track(self):
        """Phase 5: 继续循线 → 丢线后放物(中转放置.py) → 识别物块2+等10s → pick_and_place1抓取 → 左转30°"""
        print("\n" + "=" * 60)
        print("  Phase 5: 继续循线 → 丢线放物 → pick_and_place1 → 左转30°")
        print("=" * 60)


        self._configure_detector(P1_THRESHOLD, P1_MIN_AREA)
        self._configure_pid(P1_PID_KP, P1_PID_KI, P1_PID_KD,
                            P1_PID_MAX_YAW, P1_PID_INTEGRAL_MAX)
        self._sport.SpeedLevel(1)
        self._switch_to_classic()
        self._pid.reset()

        # 启动保护：跳过前若干帧，等 PID 稳定后再开始巡线
        startup_pid_pending = True
        start_protect_frames = 20
        loop_frame = 0
        lost_count = 0            # 连续丢线帧数计数
        LOST_THRESHOLD = 30       # 连续丢线触发阈值（帧数）
        fast_speed_until = 0.0    # 快跑段 (P5_BASE_SPEED) 截止时间戳, 0=尚未开始
        steady_announced = False  # 是否已打印恢复稳态速度提示
        placement_thread = None   # 后台中转放置线程 (快跑结束后启动, 与巡线并行)

        while self._running:
            loop_frame += 1
            ret, color_img = self._camera_read()
            if not ret:
                time.sleep(0.01)
                continue
            gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
            # 快跑段(P5_BASE_SPEED)期间沿用原检测; 快跑段结束后, 画面多个黑色区域时
            # 优先跟最靠左的黑色 (避开画面右侧的黑色物块带偏 PID)
            in_fast_segment = (fast_speed_until != 0.0
                               and time.time() < fast_speed_until)
            if in_fast_segment:
                found, offset, best_cx, best_cy, _, _, _, _ = \
                    self._detector.detect(gray)
            else:
                found, offset, best_cx, best_cy = \
                    self._detect_line_prefer_left(gray)

            # 启动保护期：静止等待
            if loop_frame <= start_protect_frames:
                self.set_command(0.0, 0.0, 0.0)
                if loop_frame == start_protect_frames:
                    print("[P5] 启动保护期结束，开始正常巡线")
                continue

            # 首个可信检测值初始化 PID，避免 D 项瞬间冲击
            if startup_pid_pending and found and abs(offset) <= 0.80:
                self._pid.reset(initial_error=offset)
                startup_pid_pending = False

            # 循线 (同 Phase 4 风格)，带丢线检测
            if not found:
                lost_count += 1
                self._pid.reset()
                if lost_count >= LOST_THRESHOLD:
                    # 丢线触发：停车 → 通过 中转放置.py 执行机械臂放物动作序列
                    print(f"[P5] 连续丢线 {lost_count} 帧 -> 执行放物动作序列")
                    self.set_command(0.0, 0.0, 0.0)
                    time.sleep(0.3)

                    # 若快跑结束后已后台启动中转放置, 等待其完成;
                    # 若丢线发生在快跑段内(线程未启动), 则同步执行。
                    if placement_thread is not None:
                        print("[P5] 等待后台中转放置完成...")
                        placement_thread.join()
                    else:
                        self._run_transfer_placement()

                    self._run_pick_and_place1()
                    time.sleep(1.0)

                    break  # 退出 Phase 5 循环
                else:
                    self.set_command(0.05, 0.0, 0.0)
            else:
                lost_count = 0
                # 进入循线后前 P5_FAST_DURATION 秒以 P5_BASE_SPEED 快跑, 之后恢复稳态速度
                if fast_speed_until == 0.0:
                    fast_speed_until = time.time() + P5_FAST_DURATION
                fast_mode = time.time() < fast_speed_until
                if not fast_mode and not steady_announced:
                    steady_announced = True
                    print(f"[P5] 快跑段结束，恢复稳态速度 {P5_STEADY_SPEED} m/s")
                    # 快跑结束: 后台启动中转放置, 与后续巡线并行 (节省放物等待时间)
                    if placement_thread is None:
                        print("[P5] 快跑结束 -> 后台启动中转放置 (与巡线并行)")
                        placement_thread = self._start_placement_async(
                            self._run_transfer_placement)
                track_speed = P5_BASE_SPEED if fast_mode else P5_STEADY_SPEED
                yaw = self._pid.update(offset, CTRL_DT)
                vx = track_speed * 0.6 if abs(offset) > 0.5 else track_speed
                self.set_command(vx, 0.0, yaw)

            # 可视化
            display = color_img.copy()
            h, w = display.shape[:2]
            cv2.line(display, (w // 2, 0), (w // 2, h), (255, 0, 0), 2)
            cv2.line(display, (0, h * 2 // 3), (w, h * 2 // 3), (0, 255, 255), 2)
            if found:
                cv2.circle(display, (int(best_cx), int(best_cy)), 8, (0, 255, 0), -1)
            vx_cmd, _, vyaw_cmd = self._get_command()
            lost_info = f" lost={lost_count}" if lost_count > 0 else ""
            cv2.putText(display, f"Phase5 vx={vx_cmd:.2f} vyaw={vyaw_cmd:+.2f}{lost_info}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow("Integrated Mission", display)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                self._running = False
                return

            time.sleep(CTRL_DT)

        # ── 丢线后左转 (经典模式, IMU 闭环) ──
        if self._running:
            self._switch_to_classic()
            target_rad = math.radians(P5_LOST_TURN_DEG)
            turn_vyaw = P5_LOST_TURN_SPEED
            if self._robot_state is not None:
                start_yaw = self._get_yaw()
                print(f"[P5] 丢线后左转{P5_LOST_TURN_DEG}° (IMU 闭环)")
                while self._running:
                    current_yaw = self._get_yaw()
                    diff = abs(self._normalize_angle(current_yaw - start_yaw))
                    if diff >= target_rad:
                        break
                    self.set_command(0.0, 0.0, turn_vyaw)
                    time.sleep(0.01)
                self.set_command(0.0, 0.0, 0.0)
                time.sleep(0.3)
                actual_deg = math.degrees(abs(self._normalize_angle(self._get_yaw() - start_yaw)))
                print(f"[P5] 左转{P5_LOST_TURN_DEG}°完成，实际转角 {actual_deg:.1f}°")
            else:
                print(f"[P5] 无IMU，延时左转{P5_LOST_TURN_DEG}°")
                self.set_command(0.0, 0.0, turn_vyaw)
                time.sleep(target_rad / turn_vyaw)
                self.set_command(0.0, 0.0, 0.0)
                time.sleep(0.3)

        print("[Phase5] 完成")

    # ================================================================
    # Phase 6 动作: 打招呼 / 伸懒腰 / 闪灯三次
    # ================================================================
    def _recognize_phase6_action(self, timeout=P6_RECOG_TIMEOUT):
        """用当前 USB 摄像头识别标志 → 返回动作 ('hello'/'stretch'/'flash'/None)
        多帧投票: 同一类别连续 P6_RECOG_MIN_FRAMES 帧即确认;
        超时未确认 → 回退 get_phase6_action() (COMBO_SELECT), 保证流程不中断。"""
        print(f"[OCR] 开始识别标志 (超时 {timeout:.0f}s)...")
        start = time.time()
        candidates = {}
        last_cat = None
        while time.time() - start < timeout:
            ret, frame = self._camera_read()
            if not ret:
                time.sleep(0.05)
                continue
            cat, conf = recognize_marker(frame)
            if cat:
                candidates[cat] = candidates.get(cat, 0) + 1 if cat == last_cat else 1
                last_cat = cat
                print(f"[OCR] 帧识别: {cat} ({conf:.2f}) 连续x{candidates[cat]}")
                if candidates[cat] >= P6_RECOG_MIN_FRAMES:
                    print(f"[OCR] 确认识别: {cat}")
                    return marker_to_phase6_action(cat)
            else:
                last_cat = None
            time.sleep(0.05)
        print("[OCR] 识别超时 -> 回退 COMBO_SELECT 动作")
        return get_phase6_action()

    # ================================================================
    def _execute_phase6_action(self):
        """识别标志 → 执行对应动作 (打招呼/伸懒腰/闪灯三次)
        识别用当前 USB 摄像头; 执行前关闭摄像头, 执行后以宽幅重新打开
        (便于 Phase 7 检测两侧黑色)"""
        action = self._recognize_phase6_action()
        print(f"[P6] 执行动作: {action}")

        # ── 关闭摄像头，释放资源 ──
        self._stop_camera()

        if action == "hello":
            print("[P6] 打招呼 Hello()...")
            code = self._sport.Hello()
            print(f"[P6] Hello() -> code={code}")
            time.sleep(1.0)

        elif action == "stretch":
            print("[P6] 伸懒腰 Stretch()...")
            code = self._sport.Stretch()
            print(f"[P6] Stretch() -> code={code}")
            time.sleep(1.0)

        elif action == "flash":
            print("[P6] 闪灯三次...")
            for i in range(3):
                self._vui.SetBrightness(10)
                time.sleep(0.3)
                self._vui.SetBrightness(0)
                time.sleep(0.3)
            print("[P6] 闪灯三次完成，关灯")
            time.sleep(1.0)

        else:
            print("[P6] 未识别到有效动作，跳过动作")

        print("[P6] Phase 6 动作完成")

        # ── 以宽幅重新打开摄像头 (便于 Phase 7 检测两侧黑色) ──
        time.sleep(0.5)
        self._start_camera(width=P6_WIDE_WIDTH)

    # ================================================================
    # Phase 6: 循线 + 红圆检测(USB, 出现→彻底消失后计时2s) → 左转85° → 后退0.8s → 识别标志 → 对应动作
    # ================================================================
    def _phase6_turn_and_track(self):
        """Phase 6: 循线 + 红圆检测(USB, 出现→彻底消失后计时2s) → 左转85° → 后退0.8s → 识别标志 → 对应动作"""
        print("\n" + "=" * 60)
        print("  Phase 6: 循线 + 红圆检测 + 计时")
        print("=" * 60)

        # -- 循线 (带红圆检测 + 计时, 经典模式) --
        self._configure_detector(P1_THRESHOLD, P1_MIN_AREA)
        self._configure_pid(P1_PID_KP, P1_PID_KI, P1_PID_KD,
                            P1_PID_MAX_YAW, P1_PID_INTEGRAL_MAX)
        self._sport.SpeedLevel(1)
        self._switch_to_classic()
        self._pid.reset()

        red_detector = RedCircleDetector()   # 使用 USB 摄像头帧检测红圆
        red_timer_start = None               # 红圆计时起点 (红圆出现并彻底消失后才开始)
        saw_red = False                      # 是否曾检测到红圆 (出现→彻底消失后才计时)
        red_gone_confirm = 0                 # 红圆连续未检出帧数 (确认"彻底消失")
        fast_speed_until = 0.0    # 快跑段 (P6_BASE_SPEED) 截止时间戳, 0=尚未开始
        steady_announced = False  # 是否已打印恢复稳态速度提示

        startup_pid_pending = True
        start_protect_frames = 20
        loop_frame = 0

        while self._running:
            loop_frame += 1
            ret, color_img = self._camera_read()
            if not ret:
                time.sleep(0.01)
                continue
            gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
            found, offset, best_cx, best_cy, _, _, _, _ = self._detector.detect(gray)

            if loop_frame <= start_protect_frames:
                self.set_command(0.0, 0.0, 0.0)
                if loop_frame == start_protect_frames:
                    print("[P6] 启动保护期结束，开始循线 + 红圆检测")
                continue

            if startup_pid_pending and found and abs(offset) <= 0.80:
                self._pid.reset(initial_error=offset)
                startup_pid_pending = False

            if not found:
                self._pid.reset()
                self.set_command(0.05, 0.0, 0.0)
            else:
                # 进入循线后前 P6_FAST_DURATION 秒以 P6_BASE_SPEED 快跑, 之后恢复稳态速度
                if fast_speed_until == 0.0:
                    fast_speed_until = time.time() + P6_FAST_DURATION
                fast_mode = time.time() < fast_speed_until
                if not fast_mode and not steady_announced:
                    steady_announced = True
                    print(f"[P6] 快跑段结束，恢复稳态速度 {P6_STEADY_SPEED} m/s")
                track_speed = P6_BASE_SPEED if fast_mode else P6_STEADY_SPEED
                yaw = self._pid.update(offset, CTRL_DT)
                vx = track_speed * 0.6 if abs(offset) > 0.5 else track_speed
                self.set_command(vx, 0.0, yaw)

                # 红圆检测 (参考 Go2fujian.py Phase 4)
                # 触发改为: 红圆出现 → 彻底消失(连续未检出 P6_RED_GONE_CONFIRM 帧)后 才开始计时
                red_found, _ = red_detector.detect(color_img)
                if red_found:
                    saw_red = True
                    red_gone_confirm = 0
                elif saw_red and red_timer_start is None:
                    red_gone_confirm += 1
                    if red_gone_confirm >= P6_RED_GONE_CONFIRM:
                        red_timer_start = time.time()
                        print(f"[P6] 红圆出现后彻底消失 -> 开始计时 {P6_RED_TIMER_DURATION}s...")

                if red_timer_start is not None:
                    red_elapsed = time.time() - red_timer_start
                    if red_elapsed >= P6_RED_TIMER_DURATION:
                        print(f"\n[P6] 红圆计时完成 ({red_elapsed:.1f}s) -> 左转85 deg")
                        self.set_command(0.0, 0.0, 0.0)
                        time.sleep(0.3)
                        self._sport.StopMove()
                        break

            # 可视化
            display = color_img.copy()
            h, w = display.shape[:2]
            cv2.line(display, (w // 2, 0), (w // 2, h), (255, 0, 0), 2)
            cv2.line(display, (0, h * 2 // 3), (w, h * 2 // 3), (0, 255, 255), 2)
            if found:
                cv2.circle(display, (int(best_cx), int(best_cy)), 8, (0, 255, 0), -1)
            vx_cmd, _, vyaw_cmd = self._get_command()
            red_info = ""
            if red_timer_start is not None:
                red_info = f" RED:{time.time() - red_timer_start:.1f}s"
            elif saw_red:
                red_info = f" redGone:{red_gone_confirm}/{P6_RED_GONE_CONFIRM}"
            cv2.putText(display, f"Phase6 vx={vx_cmd:.2f} vyaw={vyaw_cmd:+.2f}{red_info}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow("Integrated Mission", display)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                self._running = False
                return

            time.sleep(CTRL_DT)

        # ── 左转 85 deg (IMU 闭环, 经典模式) ──
        self._switch_to_classic()
        if self._robot_state is not None:
            start_yaw = self._get_yaw()
            print(f"[P6] 左转 {math.degrees(P6_RED_TURN_ANGLE):.0f} deg (IMU 闭环)")
            while self._running:
                current_yaw = self._get_yaw()
                diff = abs(self._normalize_angle(current_yaw - start_yaw))
                if diff >= P6_RED_TURN_ANGLE:
                    break
                self.set_command(0.0, 0.0, P6_RED_TURN_SPEED)
                time.sleep(0.01)
            self.set_command(0.0, 0.0, 0.0)
            time.sleep(0.3)
            actual_deg = math.degrees(abs(self._normalize_angle(self._get_yaw() - start_yaw)))
            print(f"[P6] 左转完成，实际转角 {actual_deg:.1f} deg")
        else:
            print("[P6] 无IMU，延时左转")
            self.set_command(0.0, 0.0, P6_RED_TURN_SPEED)
            time.sleep(P6_RED_TURN_ANGLE / P6_RED_TURN_SPEED)
            self.set_command(0.0, 0.0, 0.0)
            time.sleep(0.3)

        # ── 后退 0.8s ──
        print("[P6] 后退 0.8s")
        self.set_command(-0.20, 0.0, 0.0)
        time.sleep(0.8)
        # 停稳 2s 后才开始识别 (确保机器人完全静止, 画面稳定)
        self.set_command(0.0, 0.0, 0.0)
        print("[P6] 后退完成，停稳 2s...")
        time.sleep(2.0)
        # ── Phase 6 动作 (识别标志 → 打招呼/伸懒腰/闪灯三次; 识别失败回退 COMBO_SELECT) ──
        self._execute_phase6_action()

        print("[Phase6] 完成")

    # ================================================================
    # Phase 7 放物后: 前进离开放物点 → 继续循线固定时长 (然后进入 Phase 8)
    # ================================================================
    def _phase7_post_place_track(self):
        """放物动作完成后: 前进 P7_POST_PLACE_FORWARD_DUR s 离开放物点,
        再循线 P7_POST_PLACE_TRACK_DUR s (中央带 ROI, 避开两侧黑色物块),
        然后结束 Phase 7 进入 Phase 8。"""
        # -- 前进离开放物点 --
        print(f"[P7] 放物完成 -> 前进 {P7_POST_PLACE_FORWARD_DUR}s "
              f"(速度={P7_POST_PLACE_FORWARD_SPEED} m/s)...")
        self._switch_to_classic()
        self.set_command(P7_POST_PLACE_FORWARD_SPEED, 0.0, 0.0)
        time.sleep(P7_POST_PLACE_FORWARD_DUR)
        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.2)
        self._pid.reset()

        # -- 继续循线 (固定时长, 中央带 ROI 同主循线) --
        track_start = time.time()
        print(f"[P7] 继续循线 {P7_POST_PLACE_TRACK_DUR}s (中央带 ROI)...")
        while self._running and \
                time.time() - track_start < P7_POST_PLACE_TRACK_DUR:
            ret, color_img = self._camera_read()
            if not ret:
                time.sleep(0.01)
                continue
            gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
            _band_w = gray.shape[1]
            _band_l = int(_band_w * P7_LINE_ROI_LEFT)
            _band_r = int(_band_w * P7_LINE_ROI_RIGHT)
            found, offset, best_cx, best_cy, _, _, _, _ = \
                self._detector.detect(gray[:, _band_l:_band_r])
            best_cx += _band_l

            if not found:
                self._pid.reset()
                self.set_command(0.05, 0.0, 0.0)
            else:
                yaw = self._pid.update(offset, CTRL_DT)
                vx = P7_STEADY_SPEED * 0.6 if abs(offset) > 0.5 else P7_STEADY_SPEED
                self.set_command(vx, 0.0, yaw)

            time.sleep(CTRL_DT)

        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.3)
        print(f"[P7] 放物后循线 {P7_POST_PLACE_TRACK_DUR}s 结束 -> 进入 Phase 8")

    # ================================================================
    # Phase 7: 右转68° → 循线 + 倒计时 → 放物(左右放置.py)
    # ================================================================
    def _phase7_turn_and_track(self):
        """Phase 7: 右转68° → 前进1.5s → 循线(前2s底部全宽黑线→变回中央带ROI)
        + 两侧黑色触发倒计时 → 机械臂放物 → 放物后前进1.5s → 继续循线固定时长
        (放物通过 左右放置.py 执行, 方向由 OCR 识别平台标志决定, 回退 COMBO_SELECT)"""
        print("\n" + "=" * 60)
        print(f"  Phase 7: 右转 + 循线 + 倒计时 → 放{self._get_arm_drop_side()}边")
        print("=" * 60)

        # -- 右转 85 deg (IMU 闭环, 经典模式) --
        self._switch_to_classic()
        if self._robot_state is not None:
            start_yaw = self._get_yaw()
            print(f"[P7] 右转 {math.degrees(P7_TURN_ANGLE):.0f} deg (IMU 闭环)")
            while self._running:
                current_yaw = self._get_yaw()
                diff = abs(self._normalize_angle(current_yaw - start_yaw))
                if diff >= abs(P7_TURN_ANGLE):
                    break
                self.set_command(0.0, 0.0, P7_TURN_SPEED)
                time.sleep(0.01)
            self.set_command(0.0, 0.0, 0.0)
            time.sleep(0.3)
            actual_deg = math.degrees(abs(self._normalize_angle(self._get_yaw() - start_yaw)))
            print(f"[P7] 右转完成，实际转角 {actual_deg:.1f} deg")
        else:
            print("[P7] 无IMU，延时右转")
            self.set_command(0.0, 0.0, P7_TURN_SPEED)
            time.sleep(abs(P7_TURN_ANGLE) / abs(P7_TURN_SPEED))
            self.set_command(0.0, 0.0, 0.0)
            time.sleep(0.3)

        # -- 右转后前进 P7_POST_TURN_FORWARD_DUR s (经典模式), 前进到位后再开始循线 --
        print(f"[P7] 右转完成，前进 {P7_POST_TURN_FORWARD_DUR}s...")
        self.set_command(P7_POST_TURN_FORWARD_SPEED, 0.0, 0.0)
        time.sleep(P7_POST_TURN_FORWARD_DUR)
        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.2)

        # -- 循线 + 倒计时 (经典模式) --
        self._configure_detector(P1_THRESHOLD, P1_MIN_AREA)
        self._configure_pid(P1_PID_KP, P1_PID_KI, P1_PID_KD,
                            P1_PID_MAX_YAW, P1_PID_INTEGRAL_MAX)
        self._sport.SpeedLevel(1)
        self._switch_to_classic()
        self._pid.reset()

        timer_start = None  # 倒计时起点（两侧黑色触发后才开始）
        side_black_confirm = 0   # 两侧黑色连续确认帧数
        fast_speed_until = 0.0    # 快跑段 (P7_BASE_SPEED) 截止时间戳, 0=尚未开始
        steady_announced = False  # 是否已打印恢复稳态速度提示
        bottom_start = None       # 底部全宽循线模式起点 (前 P7_BOTTOM_TRACK_DUR 秒)
        bottom_mode_announced = False  # 是否已打印"切回中央带ROI"提示
        placement_thread = None   # 后台左右放置线程 (快跑结束后启动, 与巡线并行)
        print(f"[P7] 开始循线: 前{P7_BOTTOM_TRACK_DUR}s底部全宽黑线检测 + 等待画面两侧出现黑色...")

        startup_pid_pending = True
        start_protect_frames = 20
        loop_frame = 0

        while self._running:
            loop_frame += 1
            ret, color_img = self._camera_read()
            if not ret:
                time.sleep(0.01)
                continue
            gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
            # Phase 7 特殊: 前 P7_BOTTOM_TRACK_DUR 秒用全宽底部黑线检测
            # (只要画面底部有黑线就循线, 防止巡不到线), 之后变回中央带 ROI 循线
            # (排除两侧黑色物块带偏)。
            in_bottom_track = (bottom_start is not None
                               and time.time() - bottom_start < P7_BOTTOM_TRACK_DUR)
            if in_bottom_track:
                # 底部全宽: LineDetector 内部只取画面底部1/3, 全宽传入即可
                found, offset, best_cx, best_cy, _, _, _, _ = \
                    self._detector.detect(gray)
            else:
                if bottom_start is not None and not bottom_mode_announced:
                    bottom_mode_announced = True
                    print(f"[P7] 底部全宽循线 {P7_BOTTOM_TRACK_DUR}s 结束 -> 变回中央带 ROI 循线")
                _band_w = gray.shape[1]
                _band_l = int(_band_w * P7_LINE_ROI_LEFT)
                _band_r = int(_band_w * P7_LINE_ROI_RIGHT)
                found, offset, best_cx, best_cy, _, _, _, _ = \
                    self._detector.detect(gray[:, _band_l:_band_r])
                best_cx += _band_l

            if loop_frame <= start_protect_frames:
                self.set_command(0.0, 0.0, 0.0)
                if loop_frame == start_protect_frames:
                    bottom_start = time.time()
                    print(f"[P7] 启动保护期结束 -> 底部全宽循线 {P7_BOTTOM_TRACK_DUR}s")
                continue

            if startup_pid_pending and found and abs(offset) <= 0.80:
                self._pid.reset(initial_error=offset)
                startup_pid_pending = False

            # ── 两侧黑色检测：画面左1/3 和 右1/3 黑色占比均 > 阈值时触发倒计时 ──
            if timer_start is None:
                h, w = gray.shape
                third_w = w // 3
                left_region = gray[:, :third_w]
                right_region = gray[:, 2 * third_w:]
                left_black = np.count_nonzero(left_region < P3_BLACK_THRESHOLD) / left_region.size
                right_black = np.count_nonzero(right_region < P3_BLACK_THRESHOLD) / right_region.size
                if left_black > P7_SIDE_BLACK_RATIO and right_black > P7_SIDE_BLACK_RATIO:
                    side_black_confirm += 1
                else:
                    side_black_confirm = max(0, side_black_confirm - 1)
                if side_black_confirm >= P7_SIDE_BLACK_CONFIRM:
                    timer_start = time.time()
                    print(f"[P7] 画面两侧检测到黑色 (L={left_black:.2f} R={right_black:.2f}) "
                          f"-> 开始{P7_TIMER_DURATION}s倒计时")

            # 倒计时检查
            if timer_start is not None:
                elapsed = time.time() - timer_start
                if elapsed >= P7_TIMER_DURATION:
                    print(f"\n[P7] 倒计时完成 ({elapsed:.1f}s) -> 放{self._get_arm_drop_side()}边")
                    self.set_command(0.0, 0.0, 0.0)
                    time.sleep(0.3)
                    # 切换到经典模式，确保机械臂指令可即时执行
                    self._switch_to_classic()
                    # 仅放右边时右移对齐；放左边不需要右移
                    if self._get_arm_drop_side() == "右":
                        print(f"[P7] 右移 {P7_STRAFE_RIGHT_DUR}s (速度={P7_STRAFE_RIGHT_SPEED} m/s)...")
                        self.set_command(0.0, P7_STRAFE_RIGHT_SPEED, 0.0)
                        time.sleep(P7_STRAFE_RIGHT_DUR)
                        self.set_command(0.0, 0.0, 0.0)
                        time.sleep(0.2)
                    # 执行机械臂动作 (调用 左右放置.py, 传入放物方向)
                    # 若快跑结束后已后台启动左右放置, 等待其完成; 否则同步执行。
                    if placement_thread is not None:
                        print("[P7] 等待后台左右放置完成...")
                        placement_thread.join()
                    else:
                        self._run_placement(self._get_arm_drop_side())
                    # 放物后: 前进 P7_POST_PLACE_FORWARD_DUR s 离开放物点,
                    # 再继续循线 P7_POST_PLACE_TRACK_DUR s, 然后结束 Phase 7
                    self._phase7_post_place_track()
                    break

            if not found:
                self._pid.reset()
                self.set_command(0.05, 0.0, 0.0)
            else:
                # 进入循线后前 P7_FAST_DURATION 秒以 P7_BASE_SPEED 快跑, 之后恢复稳态速度
                if fast_speed_until == 0.0:
                    fast_speed_until = time.time() + P7_FAST_DURATION
                fast_mode = time.time() < fast_speed_until
                if not fast_mode and not steady_announced:
                    steady_announced = True
                    print(f"[P7] 快跑段结束，恢复稳态速度 {P7_STEADY_SPEED} m/s")
                    # 快跑结束: 后台启动左右放置, 与后续巡线并行 (节省放物等待时间)
                    if placement_thread is None:
                        print("[P7] 快跑结束 -> 后台启动左右放置 (与巡线并行)")
                        placement_thread = self._start_placement_async(
                            self._run_placement, self._get_arm_drop_side())
                track_speed = P7_BASE_SPEED if fast_mode else P7_STEADY_SPEED
                yaw = self._pid.update(offset, CTRL_DT)
                vx = track_speed * 0.6 if abs(offset) > 0.5 else track_speed
                self.set_command(vx, 0.0, yaw)

            # 可视化
            display = color_img.copy()
            h, w = display.shape[:2]
            cv2.line(display, (w // 2, 0), (w // 2, h), (255, 0, 0), 2)
            cv2.line(display, (0, h * 2 // 3), (w, h * 2 // 3), (0, 255, 255), 2)
            if found:
                cv2.circle(display, (int(best_cx), int(best_cy)), 8, (0, 255, 0), -1)
            vx_cmd, _, vyaw_cmd = self._get_command()
            timer_info = ""
            if timer_start is not None:
                remaining = max(0, P7_TIMER_DURATION - (time.time() - timer_start))
                timer_info = f" T:{remaining:.1f}s"
            cv2.putText(display, f"Phase7 vx={vx_cmd:.2f} vyaw={vyaw_cmd:+.2f}{timer_info}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow("Integrated Mission", display)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                self._running = False
                return

            time.sleep(CTRL_DT)

        print("[Phase7] 完成")

    # ================================================================
    # Phase 8 蓝色检测: USB 画面底部 ROI (占比 P8_BLUE_ROI_BOTTOM_RATIO) 是否出现蓝色
    # ================================================================
    def _phase8_detect_blue_bottom(self, color_img):
        """检测 USB 画面底部区域(占比 P8_BLUE_ROI_BOTTOM_RATIO)的蓝色,
        返回 (found, blue_ratio)。
        用于 Phase 8 最后一步: 底部画面出现蓝色则以 P8_BLUE_SPEED 前进,
        蓝色消失则停车结束。"""
        h, w = color_img.shape[:2]
        roi_top = h - int(h * P8_BLUE_ROI_BOTTOM_RATIO)
        roi = color_img[roi_top:, :]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, P8_BLUE_HSV_LOWER, P8_BLUE_HSV_UPPER)
        blue_ratio = cv2.countNonZero(mask) / mask.size
        return blue_ratio > P8_BLUE_RATIO_THRESH, blue_ratio

    # ================================================================
    # Phase 8: 循线 + 白线检测 → 前跳 (无 JUMP_ALIGN, 白线后直接跳)
    # ================================================================
    def _phase8_track_and_jump(self):
        """Phase 8: 循线 + 白线检测 → 前跳 (无居中校准) → 前进(P8_POST_FORWARD_DUR) → 左转85° → 蓝色驱动前进"""
        print("\n" + "=" * 60)
        print("  Phase 8: 循线 + 白线检测 → 前跳")
        print("=" * 60)

        self._configure_detector(P1_THRESHOLD, P1_MIN_AREA, P1_MIN_WIDTH)
        self._configure_pid(P1_PID_KP, P1_PID_KI, P1_PID_KD,
                            P1_PID_MAX_YAW, P1_PID_INTEGRAL_MAX)
        self._sport.SpeedLevel(1)
        self._switch_to_classic()
        self._pid.reset()

        white_cross_count = 0
        jump_triggered = False
        lost_count = 0
        state = "TRACK"  # TRACK | JUMP | POST_FORWARD | POST_TURN | POST_FORWARD2 | DONE
        state_entered = True  # 新状态首次进入标志

        startup_pid_pending = True
        start_protect_frames = 20
        loop_frame = 0

        while self._running:
            loop_frame += 1
            blue_ratio = 0.0   # 画面下半部蓝色占比 (POST_FORWARD2 蓝色检测使用)

            # ── 视觉检测（跳跃期间摄像头关闭，跳过帧读取）──
            if self._camera_on:
                ret, color_img = self._camera_read()
                if not ret:
                    time.sleep(0.01)
                    continue
                gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
                found, offset, best_cx, best_cy, _, _, _, _ = self._detector.detect(gray)
            else:
                found = False
                offset = 0.0
                time.sleep(0.01)

            if loop_frame <= start_protect_frames:
                self.set_command(0.0, 0.0, 0.0)
                if loop_frame == start_protect_frames:
                    print("[P8] 启动保护期结束，开始循线 + 白线检测")
                continue

            if startup_pid_pending and found and abs(offset) <= 0.80:
                self._pid.reset(initial_error=offset)
                startup_pid_pending = False

            if state == "TRACK":
                # 白线检测
                if found:
                    is_white = self._detector.detect_white_line_cross(gray, color_img)
                    if is_white:
                        white_cross_count += 1
                    else:
                        white_cross_count = max(0, white_cross_count - 1)

                    if white_cross_count >= P1_WHITE_CROSS_CONFIRM:
                        print(f"[P8] 白线横切！连续 {white_cross_count} 帧 -> 直接前跳")
                        state = "JUMP"
                        state_entered = True
                        jump_start_time = time.time()
                        jump_triggered = False
                        self.set_command(0.0, 0.0, 0.0)
                        continue
                else:
                    white_cross_count = max(0, white_cross_count - 1)

                # PID 巡线
                if not found:
                    self._pid.reset()
                    self.set_command(0.05, 0.0, 0.0)
                else:
                    yaw = self._pid.update(offset, CTRL_DT)
                    vx = P8_BASE_SPEED * 0.6 if abs(offset) > 0.5 else P8_BASE_SPEED
                    self.set_command(vx, 0.0, yaw)

            elif state == "JUMP":
                elapsed = time.time() - jump_start_time
                t_forward_end = P1_JUMP_FORWARD_DUR
                t_stop_end = t_forward_end + P1_JUMP_STOP_DUR
                t_jump_end = t_stop_end + 2.5
                if elapsed < t_forward_end:
                    self.set_command(P1_JUMP_FORWARD_SPEED, 0.0, 0.0)
                elif elapsed < t_stop_end:
                    if self._camera_on:
                        self._stop_camera()
                    self.set_command(0.0, 0.0, 0.0)
                    if not jump_triggered and elapsed >= t_forward_end + 0.1:
                        self._sport.StopMove()
                elif elapsed < t_jump_end:
                    if not jump_triggered:
                        code = self._sport.FrontJump()
                        jump_triggered = True
                        if code == 0:
                            print("[P8] FrontJump() OK")
                        else:
                            print(f"[P8] FrontJump() 失败, code={code}")
                    self.set_command(0.0, 0.0, 0.0)
                else:
                    time.sleep(1.0)  # 等摄像头设备释放完毕
                    self._start_camera()
                    state = "POST_FORWARD"
                    state_entered = True
                    forward_start = time.time()
                    print(f"[P8] 跳跃完成, 摄像头已重启 -> 前进{P8_POST_FORWARD_DUR}s")

            elif state == "POST_FORWARD":
                # ── 前进 P8_POST_FORWARD_DUR s (经典模式) ──
                if state_entered:
                    state_entered = False
                    self._switch_to_classic()
                elapsed = time.time() - forward_start
                if elapsed >= P8_POST_FORWARD_DUR:
                    print(f"[P8] 前进{P8_POST_FORWARD_DUR}s完成 -> 左转85°")
                    self.set_command(0.0, 0.0, 0.0)
                    time.sleep(0.2)
                    state = "POST_TURN"
                    state_entered = True
                    turn_start_yaw = self._get_yaw()
                else:
                    self.set_command(P8_BASE_SPEED, 0.0, 0.0)

            elif state == "POST_TURN":
                # ── 左转 85° (经典模式, IMU 闭环) ──
                if state_entered:
                    state_entered = False
                    self._switch_to_classic()
                current_yaw = self._get_yaw()
                diff = abs(self._normalize_angle(current_yaw - turn_start_yaw))
                if diff >= math.radians(85):
                    print("[P8] 左转85°完成 -> 蓝色驱动前进")
                    self.set_command(0.0, 0.0, 0.0)
                    time.sleep(0.2)
                    state = "POST_FORWARD2"
                    state_entered = True
                else:
                    self.set_command(0.0, 0.0, 1.0)

            elif state == "POST_FORWARD2":
                if state_entered:
                    state_entered = False
                    self._switch_to_classic()
                    print(f"[P8] 最后一步: 画面底部({P8_BLUE_ROI_BOTTOM_RATIO})出现蓝色"
                          f"则以 {P8_BLUE_SPEED} m/s 前进, 蓝色消失则停")
                # 蓝色驱动: 底部 ROI 出现蓝色 -> P8_BLUE_SPEED 前进; 蓝色消失 -> 停车结束
                blue_present = False
                if self._camera_on:
                    blue_present, blue_ratio = self._phase8_detect_blue_bottom(color_img)
                if blue_present:
                    self.set_command(P8_BLUE_SPEED, 0.0, 0.0)
                else:
                    print(f"[P8] 画面底部蓝色消失 (ratio={blue_ratio:.3f}) -> 停止, Phase 8 完成")
                    self.set_command(0.0, 0.0, 0.0)
                    state = "DONE"

            elif state == "DONE":
                self.set_command(0.0, 0.0, 0.0)
                break

            # 可视化 (摄像头开启时)
            if self._camera_on:
                display = color_img.copy()
                h, w = display.shape[:2]
                cv2.line(display, (w // 2, 0), (w // 2, h), (255, 0, 0), 2)
                cv2.line(display, (0, h * 2 // 3), (w, h * 2 // 3), (0, 255, 255), 2)
                if found:
                    cv2.circle(display, (int(best_cx), int(best_cy)), 8, (0, 255, 0), -1)
                    if state == "POST_ALIGN" and hasattr(self._detector, 'best_right_x'):
                        rx = self._detector.best_right_x
                        cv2.circle(display, (rx, int(best_cy)), 6, (0, 0, 255), -1)
                        cv2.line(display, (rx, int(best_cy) - 20), (rx, int(best_cy) + 20), (0, 0, 255), 2)
                vx_cmd, vy_cmd, vyaw_cmd = self._get_command()
                status = f"Phase8 {state} vx={vx_cmd:.2f} vy={vy_cmd:+.2f} vyaw={vyaw_cmd:+.2f}"
                if state == "POST_ALIGN" and found and hasattr(self._detector, 'best_right_x'):
                    err = (FRAME_WIDTH // 2) - self._detector.best_right_x
                    status += f" err={err}px"
                elif state == "POST_FORWARD":
                    status += f" T:{max(0, 8.0 - (time.time() - forward_start)):.1f}s"
                elif state == "POST_FORWARD2":
                    status += f" blue:{blue_ratio:.3f}"
                cv2.putText(display, status, (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                cv2.imshow("Integrated Mission", display)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                self._running = False
                return

            time.sleep(CTRL_DT)

        print("[Phase8] 完成")

    # ================================================================
    # D435i RealSense 红圆检测
    # ================================================================
    def _start_d435i(self):
        """启动 D435i RealSense 管道"""
        self._d435i_pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, FRAME_WIDTH, FRAME_HEIGHT,
                             rs.format.bgr8, FPS)
        self._d435i_pipeline.start(config)
        self._d435i_started = True
        print("[D435i] RealSense 管道已启动")

    def _stop_d435i(self):
        """停止 D435i RealSense 管道"""
        if self._d435i_pipeline and self._d435i_started:
            try:
                self._d435i_pipeline.stop()
                self._d435i_started = False
                print("[D435i] RealSense 管道已停止")
            except Exception:
                pass

    def _d435i_red_thread(self):
        """后台线程：RealSense D435i 红圆检测"""
        self._start_d435i()
        confirm = 0
        while self._running and self._d435i_started:
            red_found = False
            try:
                frames = self._d435i_pipeline.wait_for_frames(timeout_ms=100)
                color_frame = frames.get_color_frame()
                if color_frame:
                    frame = np.asanyarray(color_frame.get_data())
                    # 保存最新彩色帧 (副本), 供 OCR 平台识别兜底 — 避免识别时重新开启 D435i
                    # (重开会触发 ~10s 硬件复位慢路径)
                    with self._red_lock:
                        self._d435i_last_frame = frame.copy()
                        # 若 OCR 已请求"停稳后新帧" (倒计时结束机器人停稳后), 本帧即为其专用捕获帧
                        if self._d435i_capture_pending:
                            self._d435i_capture_frame = frame.copy()
                            self._d435i_capture_pending = False
                    red_found, debug = self._red_detector.detect(frame)
                    # 保存预览帧供主线程显示
                    d435i_preview = cv2.resize(frame, (480, 360))
                    cv2.putText(d435i_preview,
                                f"DETECTED" if red_found else f"NO DETECT",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                (0, 255, 0) if red_found else (0, 0, 255), 2)
                    cv2.putText(d435i_preview,
                                f"area={debug['max_area_ratio']:.3f} circ={debug['max_circularity']:.2f}",
                                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                (255, 255, 255), 2)
                    cv2.putText(d435i_preview,
                                f"contours={debug['num_contours']} conf={confirm}/{RED_CONFIRM_FRAMES}",
                                (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                (255, 255, 255), 2)
                    with self._red_lock:
                        self._d435i_preview = d435i_preview
                    # 保存 HSV mask 供主线程显示
                    mask_display = cv2.resize(debug["mask"], (480, 360))
                    mask_display = cv2.cvtColor(mask_display, cv2.COLOR_GRAY2BGR)
                    with self._red_lock:
                        self._d435i_mask = mask_display
            except RuntimeError:
                time.sleep(0.05)
                continue
            except Exception:
                time.sleep(0.05)
                continue

            if red_found:
                confirm += 1
            else:
                confirm = max(0, confirm - 1)

            with self._red_lock:
                self._red_confirm_count = confirm
                self._red_confirmed = (confirm >= RED_CONFIRM_FRAMES)


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
            self._stop_d435i()
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
    # 终端选择动作组合 (1-6)
    # ================================================================
    def _wait_combo_select(self):
        """初始化+摄像头就绪后, 等待终端输入 1-6 选择动作组合

        1=放左边+打招呼  2=放左边+伸懒腰  3=放左边+闪灯三次
        4=放右边+打招呼  5=放右边+伸懒腰  6=放右边+闪灯三次
        选中后立即开始 Phase 4-8 流程
        """
        global COMBO_SELECT
        print("\n" + "=" * 60)
        print("  初始化完成，请输入启动指令")
        print("=" * 60)
        while True:
            try:
                raw = input("启动指令 (1-6): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("[WARN] 未收到输入，使用默认组合 3 (放左边+闪灯三次)")
                return
            if raw not in ("1", "2", "3", "4", "5", "6"):
                print(f"[WARN] 输入无效: {raw!r}，请输入 1-6")
                continue
            COMBO_SELECT = int(raw)
            print(f"[INFO] 已选择组合 {COMBO_SELECT}: "
                  f"{get_phase6_action()}动作，开始执行... "
                  f"(Phase 7 放物方向由 Phase 4 OCR 识别决定, "
                  f"失败回退 COMBO: 放{get_arm_drop_side()}边)")
            return

    # ================================================================
    # 顶层编排
    # ================================================================
    def run(self):
        # 一次性机器人初始化
        self._init_robot()

        # 启动控制线程（在摄像头之前，确保尽快开始发送 Move(0,0,0)）
        ctrl_thread = threading.Thread(
            target=self._control_loop, daemon=True, name="ctrl")
        ctrl_thread.start()

        # 启动摄像头
        self._start_camera()

        # 初始化完成，允许控制线程发指令
        self._init_done = True

        # 等待终端输入 1-6 选择动作组合, 选中后立即开始 Phase 流程
        self._wait_combo_select()

        # 全部 Phase 顺序执行
        try:
             self._phase1_track_and_jump()  # Phase 1: 巡线+白线→前跳→继续循线→丢线结束 (GO_FORWARD/ROTATING已禁用)

             if self._running:
                self._phase_maze()          # Phase 2: 迷宫定序运动（前进2s + TOF 迷宫导航）

             if self._running:
                self._phase3_stairs()     # Phase 3: 居中 → 巡线+黑区检测 → 上台阶 → 左转79° → 下台阶 → 二次居中

             if self._running:
                self._phase4_arm_and_red()    # Phase 4: 机械臂识别 → 巡线 + D435i红圆 → 3s倒计时 → pick_and_place抓取

             if self._running:
                self._phase5_track()            # Phase 5: 继续循线 → 丢线放物 → pick_and_place1抓取 → 左转30°

             if self._running:
                 self._phase6_turn_and_track()   # Phase 6: 循线 + 红圆检测(USB, 出现→彻底消失后计时2s) → 左转85° → 后退0.8s → 站立5s

             if self._running:
                 self._phase7_turn_and_track()   # Phase 7: 右转68° → 前进1.5s → 循线(底部2s→中央带ROI) + 倒计时 → 放左边

             if self._running:
                 self._phase8_track_and_jump()   # Phase 8: 循线 + 白线检测 → 前跳 → 前进(P8_POST_FORWARD_DUR) → 左转85° → 前进1s

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
            print("用法: python3 phase1_only.py <networkInterface>")
            print("示例: python3 phase1_only.py eth0")
            sys.exit(-1)

    print("=" * 60)
    print("  Go2 Phase 1-8 全流程程序")
    print(f"  网络接口: {network_iface}")
    print("=" * 60)

    # 信号处理
    def on_signal(sig, frame):
        print("\n[STOP] 收到终止信号")
        sys.exit(0)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    try:
        mission = IntegratedMission(network_interface=network_iface)
    except Exception as e:
        print(f"\n[ERROR] 使用接口 {network_iface} 初始化失败: {e}")
        auto_iface = auto_detect_interface()
        if auto_iface and auto_iface != network_iface:
            print(f"[INFO] 重试接口: {auto_iface}")
            mission = IntegratedMission(network_interface=auto_iface)
        else:
            print("[FATAL] 无法找到可用的网络接口")
            sys.exit(-1)

    mission.run()


if __name__ == "__main__":
    main()
