#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Go2 迷宫闯关：TOF 测距导航（入口 → 左回头 → 右回头 → 跟右墙 → 收尾左转）

传感器（TOF_read.py）：左(0)、右(1)、前(2) 三路 TinyF 红外测距，单位 mm。
运动（迷宫.py MotionController）：DDS 速度指令 + IMU 闭环微调转弯。

迷宫结构（按用户描述）：
  入口处检测左右墙距离，记录"中间值" = 左右墙读数的平均值（让狗处在两墙正中的读数）。
  [Phase1] 前进，靠右墙控制：右墙目标 = 入口中间值 + P1_RIGHT_OFFSET_MM；中途左侧
           出现道路时打日志（控制不变）；前方 ≤P1_FRONT_MM → 停车。
  [Phase2] 固定左回头弯，不检测：经典步态持续 Move(前进 + 左转)（HAIRPIN_* 参数）。
  [Phase3] 第一弯道结束，第二弯道开始，右墙不再可靠 → 改跟左墙（入口中间值 +
           P3_LEFT_OFFSET_MM）。先判断左墙距离：左墙偏远先左平移靠近（不检测前方）；
           到目标距离附近才跟墙前进，并检测前方 ≤P3_FRONT_MM → 停车。
  [Phase4] 在后面停车后，同样速度原理的右转弯（vyaw 取负，SECOND_TURN_* 参数）；
           转完跟右墙（入口中间值 + P4_RIGHT_OFFSET_MM）前进；
           前方 ≤P4_FRONT_MM → 停车。
  [Phase5] 停车后接着左转：与第一个弯道相同（THIRD_TURN_*，默认 = HAIRPIN_* 参数），
           但时间减半；任务结束。

毛刺滤波：墙体有缝隙时，某帧距离会突然增大、下一帧恢复。SpikeFilter 对
  "突然增大"要求连续 CONFIRM_FRAMES 帧保持才采信；单帧毛刺直接丢弃。
  减小方向的读数不过滤（保证前方逼近 25cm 能及时触发停车）。

步态使用经典步态 ClassicWalk（初始化流程与 完整.py 一致），启动后直接运行，
不需要遥控器操作。

所有可调参数集中在文件顶部常量区，真机调参直接改这里。

用法:
  python3 迷宫_tof.py eth0          # 真机，直接运行
  python3 迷宫_tof.py eth0 --sim    # 离线逻辑自检（无需硬件）
"""

import os
import sys
import threading
import time

# ---- 让同目录 TOF_read / 父目录 dds_lib_fix、迷宫 可被导入 ----
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
for _p in (_HERE, _PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dds_lib_fix  # noqa: E402  必须先于 unitree_sdk2py（cyclonedds）导入
from TOF_read import (  # noqa: E402
    TinyFSensor,
    scan_ports,
    sensor_id_from_port,
    SENSOR_LABELS,
)

# --sim 模式不依赖 unitree_sdk2py / cyclonedds，可离线跑逻辑自检 --
_SIM = "--sim" in sys.argv
if _SIM:
    class _PlaceholderMotion:
        """模拟模式占位基类（--sim 用 object.__new__ 构造，不会走 __init__）。"""

        def __init__(self, network_interface: str = ""):
            pass

    MotionController = _PlaceholderMotion
else:
    from 迷宫 import MotionController  # noqa: E402

# ============================================================
# 可调参数（真机调参改这里）
# ============================================================

# --- 运动 ---
BASE_FORWARD_SPEED = 0.25     # 正常前进速度 (m/s)
MAX_STRAFE         = 0.15     # 横向纠偏最大速度 (m/s)
CENTER_GAIN        = 0.002    # 横向纠偏增益 (m/s 每 mm 偏差)
CTRL_HZ            = 100      # 运动指令发送频率 (Hz)

# ============================================================
# 各阶段可调参数（真机调参改这里）
# ============================================================

# --- 阶段1 靠右墙前进（入口 → 第一个左回头弯） ---
P1_FRONT_MM        = 280      # 前方 ≤ 此值 → 停车 (mm)
P1_RIGHT_OFFSET_MM = 29       # 右墙目标 = 入口中间值 + 此值 (mm)

# --- 阶段2 第一个左回头弯（经典步态持续前进+左转，不检测） ---
HAIRPIN_VX       = 0.25       # 前进速度 (m/s)
HAIRPIN_VYAW     = 0.75       # 左转角速度 (rad/s)，正值 = 左转
HAIRPIN_VY       = 0.0        # 横向速度 (m/s)
HAIRPIN_DURATION = 4.57       # 持续时长 (s)

# --- 阶段3 跟左墙前进（第一弯结束 → 第二个右转弯前） ---
P3_FRONT_MM          = 350      # 前方 ≤ 此值 → 停车 (mm)
P3_LEFT_OFFSET_MM    = 63       # 左墙目标 = 入口中间值 + 此值 (mm)
P3_APPROACH_BAND_MM  = 40       # |左墙-目标| ≤ 此值 → 视为已到墙，进入跟墙前进 (mm)
P3_APPROACH_VX       = 0.0      # 靠近墙阶段的前进速度 (m/s)；0 = 纯左平移靠近，不前进

# --- 阶段4 第二个右转弯（同样速度原理，vyaw 取负）+ 跟右墙 ---
SECOND_TURN_VX       = HAIRPIN_VX       # 前进速度 (m/s)
SECOND_TURN_VYAW     = HAIRPIN_VYAW     # 转角速度幅值 (rad/s)，实际用 -SECOND_TURN_VYAW 右转
SECOND_TURN_DURATION = 4.70             # 右转弯持续时长 (s)
P4_FRONT_MM          = 280              # 跟右墙段：前方 ≤ 此值 → 停车 (mm)
P4_RIGHT_OFFSET_MM   = 55               # 跟右墙段：右墙目标 = 入口中间值 + 此值 (mm)

# --- 阶段5 第三个左转弯（同第一弯，时间减半） ---
THIRD_TURN_VX       = HAIRPIN_VX        # 前进速度 (m/s)
THIRD_TURN_VYAW     = HAIRPIN_VYAW      # 左转角速度 (rad/s)，正值 = 左转
THIRD_TURN_DURATION = 2.2               # 持续时长 (s)，时间减半（可单独覆盖）

# --- 滤波 / 道路检测 ---
ROAD_OPEN_MM       = 420      # 左侧距离 > 目标左墙值 + 此值 → 判定出现道路
SPIKE_DELTA_MM     = 150      # 相对基准突然增大超过此值 → 视为可疑尖峰
CONFIRM_FRAMES     = 2        # 突增需连续 N 帧保持才采信（滤单帧缝隙毛刺）
FRONT_HOLD_FRAMES  = 2        # 前方条件需连续满足 N 帧才触发（防读数抖动误停）

# --- 控制 / 安全 ---
NAV_DT              = 0.05    # 导航控制周期 (s) ≈ 20Hz
SENSOR_STOP_TIMEOUT = 3.0     # 某方向传感器持续无数据超过此值 → 停车
SENSOR_WAIT_TIMEOUT = 15.0    # 启动等待三路传感器就绪上限 (s)
ENTRANCE_SETTLE_S   = 1.0     # 入口"中间值"采样时长 (s)

# 方向 ↔ sensor_id
DIR_ORDER = ("left", "right", "front")
DIR_TO_SID = {"left": 0, "right": 1, "front": 2}


class SensorLostError(RuntimeError):
    """指定方向传感器持续无数据，导航中止。"""


# ============================================================
# 缝隙毛刺滤波
# ============================================================
class SpikeFilter:
    """滤掉墙体缝隙导致的单帧"突然增大"。

    规则：
      - 读数相对基准突然增大时，先标记为可疑尖峰；
      - 只有连续 confirm_frames 帧都保持增大才采信（真实信号，如左侧出现道路）；
      - 下一帧回落的单帧毛刺直接丢弃；
      - 减小方向的读数不过滤（如前方逼近 2500→250），保证停车触发及时。
    """

    def __init__(self, spike_delta=SPIKE_DELTA_MM, confirm_frames=CONFIRM_FRAMES):
        self.spike_delta = spike_delta
        self.confirm_frames = confirm_frames
        self._baseline = None
        self._spike = None
        self._spike_count = 0

    def update(self, raw):
        if raw is None:
            return None
        if self._baseline is None:
            self._baseline = float(raw)
            return self._baseline

        if raw > self._baseline + self.spike_delta:
            # 相对基准突然增大 → 疑似尖峰，需连续保持才采信
            if self._spike is None or abs(raw - self._spike) > self.spike_delta:
                self._spike = raw
                self._spike_count = 1
            else:
                self._spike_count += 1
            if self._spike_count >= self.confirm_frames:
                # 持续增大 → 真实信号（道路/开口），采信并更新基准
                self._baseline = raw
                self._spike = None
                self._spike_count = 0
            return self._baseline
        else:
            # 回到正常范围：确认之前的突增是缝隙毛刺，丢弃
            self._spike = None
            self._spike_count = 0
            # 正常范围内平滑跟随，防读数抖动
            self._baseline = self._baseline * 0.7 + raw * 0.3
            return raw

    def reset(self):
        """清除滤波状态（阶段切换时调用，避免上一阶段的基准/计数残留）。"""
        self._baseline = None
        self._spike = None
        self._spike_count = 0


# ============================================================
# 横向纠偏控制律（纯函数，便于离线验证）
#   约定：vy > 0 = 左移，vy < 0 = 右移（与 Move(0, vy, 0) 一致）
# ============================================================
def vy_wall_right(R, target_right, gain=CENTER_GAIN):
    """只参考右墙：保持 R 接近 target_right（左墙出现道路后使用）。"""
    return gain * (target_right - R)


def vy_wall_left(L, target_left, gain=CENTER_GAIN):
    """只参考左墙：保持 L 接近 target_left（第二弯道使用）。"""
    return gain * (L - target_left)


# ============================================================
# 迷宫控制器
# ============================================================
class MazeController(MotionController):
    def __init__(self, network_interface: str = ""):
        super().__init__(network_interface=network_interface)
        self._setup_sensors()

    # ---------------- 传感器 ----------------

    def _setup_sensors(self):
        ports = scan_ports()
        if not ports:
            print("[WARN] 未发现 TOF 串口（/dev/tinyf_* 或 /dev/ttyUSB*）")
        self._sensors = {}
        for port in ports:
            sid = sensor_id_from_port(port)
            s = TinyFSensor(sensor_id=sid, port=port)
            s.start()
            self._sensors[sid] = s
            time.sleep(0.25)  # 错开各串口上电时刻
        self._filters = {d: SpikeFilter(SPIKE_DELTA_MM, CONFIRM_FRAMES) for d in DIR_ORDER}
        self._missing_since = {}
        self._front_close_count = 0

    def _sensor_value(self, direction):
        """原始读数（mm）或 None。"""
        s = self._sensors.get(DIR_TO_SID[direction])
        if s is None:
            return None
        r = s.get_reading()
        return None if r is None else r[0]

    def _read_sensor(self, direction):
        """经毛刺滤波后的读数（mm）或 None。"""
        raw = self._sensor_value(direction)
        return self._filters[direction].update(raw)

    def _get_sensor_safe(self, direction):
        """读指定方向距离（已滤波）。若持续缺失超过 SENSOR_STOP_TIMEOUT → 抛 SensorLostError。"""
        d = self._read_sensor(direction)
        now = time.time()
        if d is None:
            t0 = self._missing_since.get(direction)
            if t0 is None:
                self._missing_since[direction] = now
            elif now - t0 > SENSOR_STOP_TIMEOUT:
                raise SensorLostError(f"{direction} 传感器 {SENSOR_STOP_TIMEOUT:.0f}s 无数据")
        else:
            self._missing_since.pop(direction, None)
        return d

    def _front_close(self, threshold):
        """前方是否已 ≤ threshold（连续 FRONT_HOLD_FRAMES 帧确认）。"""
        d = self._get_sensor_safe("front")
        if d is not None and d <= threshold:
            self._front_close_count += 1
        else:
            self._front_close_count = 0
        return self._front_close_count >= FRONT_HOLD_FRAMES

    def _wait_for_sensors(self, timeout=SENSOR_WAIT_TIMEOUT):
        print(f"[TOF] 等待三路传感器就绪（最多 {timeout:.0f}s）...")
        start = time.time()
        while time.time() - start < timeout:
            if all(self._sensor_value(d) is not None for d in DIR_ORDER):
                labels = "  ".join(
                    f"{SENSOR_LABELS[DIR_TO_SID[d]]}={self._sensor_value(d):.0f}mm"
                    for d in DIR_ORDER
                )
                print(f"[TOF] 就绪: {labels}")
                return True
            time.sleep(0.2)
        return False

    def _capture_entrance_targets(self):
        """机器人原地不动，采样 ENTRANCE_SETTLE_S 秒，返回"中间值" = 左右墙读数的平均值。"""
        print(f"[入口] 采样 {ENTRANCE_SETTLE_S}s 确定左右墙中间值（保持不动）...")
        lefts, rights = [], []
        deadline = time.time() + ENTRANCE_SETTLE_S
        while time.time() < deadline:
            L = self._read_sensor("left")
            R = self._read_sensor("right")
            if L is not None:
                lefts.append(L)
            if R is not None:
                rights.append(R)
            time.sleep(NAV_DT)
        if not lefts or not rights:
            raise RuntimeError("入口左右墙读数不足，无法确定中间值")
        center = (sum(lefts) / len(lefts) + sum(rights) / len(rights)) / 2
        print(f"[入口] 中间值 center={center:.0f}mm（左右墙平均值）")
        return center

    # ---------------- 机器人初始化（与 完整.py 一致的经典步态流程） ----------------

    def _init_robot(self):
        # 与 完整.py 已验证流程一致；不调用 RecoveryStand / ReleaseMode / SwitchJoystick
        print("[INIT] SelectMode('normal') ...")
        self._msc.SelectMode("normal")
        time.sleep(2.0)

        print("[INIT] StandUp ...")
        self._sport.StandUp()
        time.sleep(4.0)

        print("[INIT] SpeedLevel(1) ...")
        self._sport.SpeedLevel(1)
        time.sleep(1.0)

        print("[INIT] ClassicWalk(True) 经典步态 ...")
        self._sport.ClassicWalk(True)
        time.sleep(1.0)

        print("[INIT] Move(0,0,0) 锁定位置 ...")
        self._sport.Move(0.0, 0.0, 0.0)

    def _start_ctrl_thread(self):
        self._control_running = True
        self._ctrl_thread = threading.Thread(
            target=self._control_loop, daemon=True, name="maze_ctrl"
        )
        self._ctrl_thread.start()

    def go_forward(self, duration, speed=BASE_FORWARD_SPEED):
        """前进指定时长（秒），可指定速度。"""
        print(f"[动作] 前进 {duration}s @ {speed}m/s")
        self.set_command(speed, 0.0, 0.0)
        time.sleep(duration)
        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.1)

    @staticmethod
    def _clamp(v, lo, hi):
        return max(lo, min(hi, v))

    # ---------------- 三个导航阶段 ----------------

    def _reset_phase_sensors(self, wall_dir):
        """进入新阶段前重置墙向与前方传感器状态，避免跨阶段残留。

        残留来源：上一阶段结束时（如 Phase1 前方逼近 280mm 停车）前方滤波基准被
        拉低、`_front_close_count` 已 ≥FRONT_HOLD_FRAMES；若直接带入下一阶段，
        Phase3 刚开始跟墙（前方还很远，如 1500mm）时滤波器会先返回残留的低基准
        （≈280mm ≤ P3_FRONT_MM=350），叠加残留计数 ≥2，第一帧就会被误判"前方已近"
        → 提前停车转弯。这里清空基准与计数，让每个阶段从干净状态开始：前方仍须
        连续 FRONT_HOLD_FRAMES 帧 ≤ 阈值才停车。
        """
        for d in (wall_dir, "front"):
            self._filters[d].reset()
        self._front_close_count = 0

    def _phase_approach(self, target):
        """Phase1：前进，靠右墙控制 —— 右墙目标 = 入口中间值 + P1_RIGHT_OFFSET_MM；前方 ≤P1_FRONT_MM → 停车。

        左墙只用于检测道路/开口并打日志，不影响横向控制（本来就不转向进道路）。
        """
        self._reset_phase_sensors("right")
        right_target = target + P1_RIGHT_OFFSET_MM
        self._approach_mode = "right_only"
        self._road_logged = False
        print(f"[Phase1] 前进 {BASE_FORWARD_SPEED}m/s，靠右墙控制：目标右墙 {right_target:.0f}mm（入口中间值+{P1_RIGHT_OFFSET_MM}mm）...")
        self.set_command(BASE_FORWARD_SPEED, 0.0, 0.0)
        while True:
            try:
                if self._front_close(P1_FRONT_MM):
                    print(f"[Phase1] 前方 ≤{P1_FRONT_MM}mm → 停车，准备左回头")
                    self.set_command(0.0, 0.0, 0.0)
                    time.sleep(0.3)
                    return
                L = self._get_sensor_safe("left")
                R = self._get_sensor_safe("right")
            except SensorLostError as e:
                print(f"[WARN] {e}")
                self.set_command(0.0, 0.0, 0.0)
                return
            if L is None or R is None:
                time.sleep(NAV_DT)
                continue

            # 左侧出现道路/开口 → 只打日志，控制不变（本来就靠右墙）
            if L > target + ROAD_OPEN_MM and not self._road_logged:
                self._road_logged = True
                print(f"[Phase1] 左侧出现道路/开口 L={L:.0f}mm（保持靠右墙，目标 {right_target:.0f}mm）")

            vy = self._clamp(
                vy_wall_right(R, right_target), -MAX_STRAFE, MAX_STRAFE
            )
            self.set_command(BASE_FORWARD_SPEED, vy, 0.0)
            time.sleep(NAV_DT)

    def _continuous_turn(self, vx, vyaw, duration):
        """持续经典步态转弯：Move(vx, 0, vyaw) duration 秒后停车（不检测）。vyaw>0 左转，<0 右转。"""
        direction = "左转" if vyaw >= 0 else "右转"
        print(f"[转弯] {direction} vx={vx}m/s + vyaw={vyaw}rad/s，持续 {duration}s，不检测")
        self.set_command(vx, 0.0, vyaw)
        time.sleep(duration)
        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.3)

    def _hairpin_left_fixed(self):
        """Phase2：固定左回头弯（经典步态持续 Move）。"""
        print(f"[Phase2] 固定左回头弯：vx={HAIRPIN_VX}m/s + 左转 {HAIRPIN_VYAW}rad/s，持续 {HAIRPIN_DURATION}s，不检测")
        self._continuous_turn(HAIRPIN_VX, HAIRPIN_VYAW, HAIRPIN_DURATION)

    def _phase_return(self, target):
        """Phase3：第二弯道，右墙不可靠 → 跟左墙前进（目标 = 入口中间值 + P3_LEFT_OFFSET_MM）。

        两段式：
          1) 先判断左墙距离 —— 若左墙偏远（L > 目标 + P3_APPROACH_BAND_MM），先左平移
             靠近墙体（vx=P3_APPROACH_VX，vy 朝左），**此阶段不检测前方**；
          2) 左墙已到目标距离附近（|L-目标| ≤ P3_APPROACH_BAND_MM）→ 跟墙前进，
             靠左墙控制横向，并检测前方 ≤P3_FRONT_MM → 停车。
        """
        self._reset_phase_sensors("left")
        left_target = target + P3_LEFT_OFFSET_MM
        mode = "approach"  # 先靠近左墙；到目标附近后切 "follow" 跟墙前进
        print(f"[Phase3] 第二弯道：右墙不可靠，改跟左墙（目标 {left_target:.0f}mm = 入口中间值+{P3_LEFT_OFFSET_MM}mm）")
        print(f"[Phase3] 左墙偏远时先左平移靠近；到目标附近后跟墙前进，前方 ≤{P3_FRONT_MM}mm 停车")
        while True:
            try:
                L = self._get_sensor_safe("left")
                if mode == "follow" and self._front_close(P3_FRONT_MM):
                    print(f"[Phase3] 前方 ≤{P3_FRONT_MM}mm → 停车，准备第二个右转弯")
                    self.set_command(0.0, 0.0, 0.0)
                    time.sleep(0.3)
                    return
            except SensorLostError as e:
                print(f"[WARN] {e}")
                self.set_command(0.0, 0.0, 0.0)
                return
            if L is None:
                time.sleep(NAV_DT)
                continue

            if mode == "approach":
                if L > left_target + P3_APPROACH_BAND_MM:
                    # 左墙偏远 → 左平移靠近，不检测前方
                    vy = self._clamp(vy_wall_left(L, left_target), 0.0, MAX_STRAFE)
                    self.set_command(P3_APPROACH_VX, vy, 0.0)
                    time.sleep(NAV_DT)
                    continue
                mode = "follow"
                print(f"[Phase3] 左墙已到达目标附近 L={L:.0f}mm（目标 {left_target:.0f}mm）→ 跟墙前进")
                continue

            # 跟墙前进：靠左墙控制横向 + 检测前方
            vy = self._clamp(vy_wall_left(L, left_target), -MAX_STRAFE, MAX_STRAFE)
            self.set_command(BASE_FORWARD_SPEED, vy, 0.0)
            time.sleep(NAV_DT)

    def _phase_follow_right(self, target):
        """Phase4：右转弯后，靠右墙控制前进（目标 = 入口中间值 + P4_RIGHT_OFFSET_MM）；前方 ≤P4_FRONT_MM → 停车。"""
        self._reset_phase_sensors("right")
        right_target = target + P4_RIGHT_OFFSET_MM
        print(f"[Phase4] 右转后靠右墙控制前进（目标右墙 {right_target:.0f}mm = 入口中间值+{P4_RIGHT_OFFSET_MM}mm）...")
        self.set_command(BASE_FORWARD_SPEED, 0.0, 0.0)
        while True:
            try:
                if self._front_close(P4_FRONT_MM):
                    print(f"[Phase4] 前方 ≤{P4_FRONT_MM}mm → 停车，准备第三个左转弯")
                    self.set_command(0.0, 0.0, 0.0)
                    time.sleep(0.3)
                    return
                R = self._get_sensor_safe("right")
            except SensorLostError as e:
                print(f"[WARN] {e}")
                self.set_command(0.0, 0.0, 0.0)
                return
            if R is None:
                time.sleep(NAV_DT)
                continue
            vy = self._clamp(vy_wall_right(R, right_target), -MAX_STRAFE, MAX_STRAFE)
            self.set_command(BASE_FORWARD_SPEED, vy, 0.0)
            time.sleep(NAV_DT)

    # ---------------- 主流程 ----------------

    def _navigate(self, target):
        self._phase_approach(target)                             # 1. 靠右墙前进到回头弯
        self._hairpin_left_fixed()                               # 2. 第一个左回头弯
        self._phase_return(target)                               # 3. 跟左墙到后墙停车
        self._continuous_turn(SECOND_TURN_VX, -SECOND_TURN_VYAW,  # 4. 第二个右转弯（同样速度原理）
                              SECOND_TURN_DURATION)
        self._phase_follow_right(target)                         # 5. 跟右墙，到25cm停车
        self._continuous_turn(THIRD_TURN_VX, THIRD_TURN_VYAW,     # 6. 第三个左转弯（同第一弯，时间减半）
                              THIRD_TURN_DURATION)
        print("[完成] 任务结束")

    def run(self):
        try:
            self._init_robot()
            self._start_ctrl_thread()
            if not self._wait_for_sensors():
                print("[ERROR] TOF 三路传感器未就绪，终止")
                return
            try:
                center = self._capture_entrance_targets()
            except RuntimeError as e:
                print(f"[ERROR] {e}")
                return
            self._navigate(center)
        except KeyboardInterrupt:
            print("\n[INFO] 用户中断")
        finally:
            self._safe_stop()

    def _safe_stop(self):
        print("\n[停止] 停车 ...")
        self._control_running = False
        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.2)
        try:
            self._sport.StopMove()
        except Exception:
            pass
        time.sleep(0.3)
        for s in getattr(self, "_sensors", {}).values():
            s.stop()
        print("[停止] 已安全退出（机器人保持站立）")


# ============================================================
# 库函数入口：供 完整.py 集成调用（复用调用方已初始化的机器人与控制线程）
# ============================================================
def run_maze_navigation(driver):
    """在**已初始化**的机器人上执行迷宫 TOF 导航（库函数，供 完整.py 调用）。

    前提：调用方已完成机器人初始化（StandUp / ClassicWalk）并启动控制线程。
    本函数只负责两件事：
      1. 建立并等待 TOF 左/右/前 三路传感器就绪；
      2. 入口左右墙中间值采样 → 五阶段导航（靠右墙 → 左回头 → 跟左墙 → 右转 → 跟右墙 → 左转）。

    运动指令通过 ``driver.set_command(vx, vy, vyaw)`` 下发（由调用方的控制线程执行），
    安全停车复用 ``driver._sport.StopMove()``。函数结束只停止 TOF 传感器与运动，
    **不触碰调用方的控制线程**，保证后续阶段（Phase 3~8）可继续运行。

    Args:
        driver: 已初始化的运动驱动器（如 IntegratedMission 实例），需提供：
            - ``set_command(vx, vy, vyaw)``：下发运动指令
            - ``_sport``：SportClient，用于安全停车

    返回: None。TOF 未就绪 / 入口读数不足时打印错误后直接返回（不影响主流程）。
    """
    nav = object.__new__(MazeController)   # 只复用导航/传感器逻辑，不再初始化 DDS
    nav.set_command = driver.set_command
    nav._sport = driver._sport
    nav._running = True
    nav._control_running = True            # 本函数不启停控制线程，仅保证阶段代码不误判
    try:
        nav._setup_sensors()
        if not nav._wait_for_sensors():
            print("[迷宫] ERROR: TOF 三路传感器未就绪，跳过迷宫导航")
            return
        try:
            center = nav._capture_entrance_targets()
        except RuntimeError as e:
            print(f"[迷宫] ERROR: {e}")
            return
        nav._navigate(center)
    finally:
        # 只停运动与 TOF 传感器，保持调用方的控制线程运行
        nav.set_command(0.0, 0.0, 0.0)
        time.sleep(0.2)
        try:
            nav._sport.StopMove()
        except Exception:
            pass
        time.sleep(0.3)
        for s in nav._sensors.values():
            s.stop()
        print("[迷宫] 迷宫导航结束，TOF 传感器已关闭，可继续后续阶段")


# ============================================================
# 离线逻辑自检 (--sim)：不连硬件，用脚本化传感器场景驱动状态机
# ============================================================
class _SimMotion:
    """模拟运动后端：记录下发的指令。"""

    def __init__(self):
        self.cmds = []       # (t, vx, vy, vyaw)
        self.turns = []      # (dir, deg)
        self.forwards = []   # (sec, speed)
        self._t0 = time.time()

    def set_command(self, vx, vy, vyaw):
        self.cmds.append((time.time() - self._t0, vx, vy, vyaw))

    def turn_left(self, deg):
        self.turns.append(("left", deg))

    def turn_right(self, deg):
        self.turns.append(("right", deg))

    def go_forward(self, duration, speed=BASE_FORWARD_SPEED):
        self.forwards.append((duration, speed))


class _ApproachScenario:
    """Phase1 场景：靠右墙控制，右墙单帧缝隙毛刺 → 左侧出现道路 → 前方逼近 25cm。"""

    LEFT_ROAD_AT = 2.0      # s 后左侧出现道路
    FRONT_CLOSE_AT = 4.0    # s 后前方逼近 25cm
    RIGHT_SPIKE_AT = 1.0    # s 时右墙出现单帧缝隙毛刺

    def __init__(self):
        self._t0 = time.time()
        self._spike_done = False

    def value(self, direction):
        t = time.time() - self._t0
        if direction == "front":
            return 250 if t >= self.FRONT_CLOSE_AT else 1500
        if direction == "right":
            if not self._spike_done and t >= self.RIGHT_SPIKE_AT:
                self._spike_done = True
                return 2500  # 右墙单帧缝隙毛刺（下一帧恢复正常）
            return 350
        # left
        if t >= self.LEFT_ROAD_AT:
            return 2000  # 道路出现（持续增大）
        return 350


class _ReturnScenario:
    """Phase3 场景：左墙先偏远（550 → 应先左平移靠近）→ 到目标附近（400 → 跟墙前进）→ 前方逼近 29cm。

    前方 290mm 介于 P1_FRONT_MM(280) 与 P3_FRONT_MM 之间：
    验证 Phase3 用的是独立阈值 P3_FRONT_MM，若误用 P1_FRONT_MM(280) 就不会触发停车。
    """

    LEFT_NEAR_AT = 1.5     # s 后左墙到达目标附近（进入跟墙前进）
    FRONT_CLOSE_AT = 3.0   # s 后前方逼近 29cm

    def __init__(self):
        self._t0 = time.time()

    def value(self, direction):
        t = time.time() - self._t0
        if direction == "front":
            return 290 if t >= self.FRONT_CLOSE_AT else 1500
        if t >= self.LEFT_NEAR_AT:
            return 400  # 左墙已到目标附近（目标=入口中间值+offset）
        return 550  # 左墙偏远 → 应先左平移靠近


class _FollowRightScenario:
    """Phase4 场景：右墙 450（比目标 400 偏远 50mm → 应向右微调），前方逼近 25cm。"""

    FRONT_CLOSE_AT = 3.0

    def __init__(self):
        self._t0 = time.time()

    def value(self, direction):
        t = time.time() - self._t0
        if direction == "front":
            return 250 if t >= self.FRONT_CLOSE_AT else 1500
        return 450  # 右墙略偏远（目标=入口中间值+50mm=400）


def _test_filter():
    print("\n[1] SpikeFilter 毛刺滤波")
    f = SpikeFilter(SPIKE_DELTA_MM, CONFIRM_FRAMES)
    gap = [350, 350, 2500, 350, 350]                      # 缝隙单帧毛刺
    out_gap = [f.update(x) for x in gap]
    f2 = SpikeFilter(SPIKE_DELTA_MM, CONFIRM_FRAMES)
    road = [350, 350, 2000, 2000, 2000]                   # 道路出现（持续增大）
    out_road = [f2.update(x) for x in road]
    f3 = SpikeFilter(SPIKE_DELTA_MM, CONFIRM_FRAMES)
    front = [1500, 1200, 900, 600, 300, 250]              # 前方逼近（减小，不过滤）
    out_front = [f3.update(x) for x in front]
    print(f"  缝隙毛刺: {gap} -> {[round(x) for x in out_gap]}")
    print(f"  道路出现: {road} -> {[round(x) for x in out_road]}")
    print(f"  前方逼近: {front} -> {[round(x) for x in out_front]}")
    assert abs(out_gap[2] - 350) < 60, "单帧缝隙毛刺未被滤掉"
    assert out_road[-1] > 1500, "持续增大的道路信号未被采信"
    assert out_front[-1] <= 250, "前方逼近（减小方向）不应被过滤/滞后"
    print("  PASS")
    return True


def _test_vy():
    print("\n[2] 横向纠偏控制律 vy（>0 左移，<0 右移）")
    # 只跟右墙：太贴右（R 小）→ 左移 vy>0
    assert vy_wall_right(300, 350) > 0
    # 只跟右墙：目标 = 中间值+offset → 保持右墙偏大 → 左移
    assert vy_wall_right(350, 350 + P1_RIGHT_OFFSET_MM) > 0
    # 只跟左墙：太贴左（L 小）→ 右移 vy<0
    assert vy_wall_left(300, 350) < 0
    # 只跟左墙：目标 = 中间值+offset → 左墙比目标小 → 右移 vy<0
    assert vy_wall_left(350, 350 + P3_LEFT_OFFSET_MM) < 0
    print("  PASS")
    return True


def _test_phases():
    print("\n[3] 多阶段状态机（模拟传感器场景）")
    mc = object.__new__(MazeController)
    mc._missing_since = {}
    mc._front_close_count = 0
    mc._filters = {d: SpikeFilter(SPIKE_DELTA_MM, CONFIRM_FRAMES) for d in DIR_ORDER}

    # ---- Phase1：靠右墙控制（目标=中间值+3cm）+ 滤右墙缝隙毛刺 + 前方25cm停车 ----
    motion = _SimMotion()
    mc.set_command = motion.set_command
    mc.turn_left = motion.turn_left
    mc.turn_right = motion.turn_right
    mc.go_forward = motion.go_forward
    app = _ApproachScenario()
    mc._sensor_value = app.value
    mc._phase_approach(350)
    assert motion.cmds[-1][1:] == (0.0, 0.0, 0.0), "Phase1 结束应停车"
    assert mc._approach_mode == "right_only", "Phase1 应为靠右墙控制"
    max_vy = max(abs(c[2]) for c in motion.cmds)
    expected_vy = CENTER_GAIN * P1_RIGHT_OFFSET_MM
    assert max_vy < 0.10, f"右墙缝隙毛刺不应引起纠偏跳变，实际 max|vy|={max_vy:.3f}"
    assert any(abs(c[2] - expected_vy) < 1e-6 for c in motion.cmds), \
        f"靠右墙控制应在目标=中间值+{P1_RIGHT_OFFSET_MM}mm 时输出 vy≈{expected_vy:.3f}"
    print(f"  Phase1 PASS（靠右墙 vy≈{expected_vy:.3f}，右墙缝隙毛刺被滤掉，max|vy|={max_vy:.3f}）")

    # ---- Phase2：固定左回头弯（经典步态持续 Move） ----
    motion2 = _SimMotion()
    mc.set_command = motion2.set_command
    mc._hairpin_left_fixed()
    drive = [c for c in motion2.cmds if (c[1], c[2], c[3]) != (0.0, 0.0, 0.0)]
    assert drive, "Phase2 应下发驱动指令"
    vx, vy, vyaw = drive[0][1], drive[0][2], drive[0][3]
    assert (vx, vy, vyaw) == (HAIRPIN_VX, HAIRPIN_VY, HAIRPIN_VYAW), \
        f"Phase2 指令应为 (vx={HAIRPIN_VX}, vy={HAIRPIN_VY}, vyaw={HAIRPIN_VYAW})，实际 ({vx},{vy},{vyaw})"
    assert motion2.cmds[-1][1:] == (0.0, 0.0, 0.0), "Phase2 结束应停车"
    print(f"  Phase2 PASS（持续左回头 vx={HAIRPIN_VX} vyaw={HAIRPIN_VYAW} {HAIRPIN_DURATION}s，之后停车）")

    # ---- Phase3：先靠近左墙（左平移）→ 跟墙前进 + 前方停车 ----
    motion3 = _SimMotion()
    mc.set_command = motion3.set_command
    ret = _ReturnScenario()
    mc._sensor_value = ret.value
    mc._front_close_count = 0
    mc._phase_return(350)
    assert motion3.cmds[-1][1:] == (0.0, 0.0, 0.0), "Phase3 结束应停车"
    # 场景: 先 左墙偏远 550（目标 350+59=409）→ 应先左平移靠近
    #   靠近阶段 vy = clamp(gain*(550-409), 0, MAX_STRAFE) = clamp(0.282, 0, 0.15) = MAX_STRAFE
    approach_vy = min(CENTER_GAIN * (550 - (350 + P3_LEFT_OFFSET_MM)), MAX_STRAFE)
    assert any(abs(c[1] - P3_APPROACH_VX) < 1e-9 and abs(c[2] - approach_vy) < 1e-9
               for c in motion3.cmds), \
        f"左墙偏远(550mm)应先左平移靠近：vx={P3_APPROACH_VX}, vy={approach_vy:.3f}（不前进、不检测前方）"
    # 靠近阶段不应提前前进
    assert not any(abs(c[1] - BASE_FORWARD_SPEED) < 1e-9
                   and abs(c[2] - approach_vy) < 1e-9 for c in motion3.cmds), \
        "靠近墙阶段不应同时前进"
    # 场景: 之后 左墙 400（已到目标附近）→ 跟墙前进
    expected3 = CENTER_GAIN * (400 - (350 + P3_LEFT_OFFSET_MM))
    assert any(abs(c[1] - BASE_FORWARD_SPEED) < 1e-9 and abs(c[2] - expected3) < 1e-6
               for c in motion3.cmds), \
        f"跟墙前进应在目标=中间值+{P3_LEFT_OFFSET_MM}mm 时 vx={BASE_FORWARD_SPEED}、vy≈{expected3:.3f}"
    print(f"  Phase3 PASS（先左平移靠近 vy={approach_vy:.3f}，到目标后跟墙 vy≈{expected3:.3f}，前方 {P3_FRONT_MM}mm 停车）")

    # ---- Phase3 回归：跨阶段残留不应导致提前转弯 ----
    # 真机 Phase1 结束时前方滤波基准≈280、连续计数≥2（刚触发过停车）；若带进
    # Phase3，刚开始跟墙（前方还很远 1500mm）时滤波器先返回残留低基准
    # （≈280mm ≤ P3_FRONT_MM=350），叠加残留计数 ≥2 → 第一帧就被误判"前方已近"
    # 提前停车转弯。修复后应先跟墙多帧，等前方真正 ≤P3_FRONT_MM 连续两帧才停车。
    motion3r = _SimMotion()
    mc.set_command = motion3r.set_command
    mc._filters["front"]._baseline = 280.0    # 残留的低基准（Phase1 停车的读数）
    mc._front_close_count = 3                  # 残留的计数（Phase1 已触发）
    ret = _ReturnScenario()
    mc._sensor_value = ret.value
    mc._phase_return(350)
    assert motion3r.cmds[-1][1:] == (0.0, 0.0, 0.0), "Phase3 回归结束应停车"
    follow3r = [c for c in motion3r.cmds if abs(c[1] - BASE_FORWARD_SPEED) < 1e-9]
    assert len(follow3r) >= 2, \
        f"残留状态不应让 Phase3 第一帧就停车（应跟墙多帧后前方真正 ≤{P3_FRONT_MM}mm 才停），实际跟墙帧数={len(follow3r)}"
    print(f"  Phase3 回归 PASS（带残留基准/计数仍先跟墙 {len(follow3r)} 帧，前方真正 ≤{P3_FRONT_MM}mm 才停车）")

    # ---- Phase4：第二个右转弯（同样速度原理，vyaw 取负）+ 跟右墙 + 前方25cm停车 ----
    motion4 = _SimMotion()
    mc.set_command = motion4.set_command
    mc._continuous_turn(SECOND_TURN_VX, -SECOND_TURN_VYAW, SECOND_TURN_DURATION)
    drive4 = [c for c in motion4.cmds if (c[1], c[2], c[3]) != (0.0, 0.0, 0.0)]
    assert drive4, "Phase4 转弯应下发驱动指令"
    assert drive4[0][1:] == (SECOND_TURN_VX, 0.0, -SECOND_TURN_VYAW), \
        f"Phase4 转弯指令应为 ({SECOND_TURN_VX}, 0, {-SECOND_TURN_VYAW})，实际 {drive4[0][1:]}"
    assert motion4.cmds[-1][1:] == (0.0, 0.0, 0.0), "Phase4 转弯结束应停车"

    fr = _FollowRightScenario()
    mc._sensor_value = fr.value
    mc._front_close_count = 0
    mc._phase_follow_right(350)
    assert motion4.cmds[-1][1:] == (0.0, 0.0, 0.0), "Phase4 跟右墙结束应停车"
    assert any(c[2] < -0.01 for c in motion4.cmds), "右墙偏远时应向右微调 vy<0"
    print(f"  Phase4 PASS（同样速度原理右转 vx={SECOND_TURN_VX} vyaw={-SECOND_TURN_VYAW} {SECOND_TURN_DURATION}s + 跟右墙，前方 25cm 停车）")

    # ---- Phase5：第三个左转弯（同第一弯，时间减半） ----
    motion5 = _SimMotion()
    mc.set_command = motion5.set_command
    mc._continuous_turn(THIRD_TURN_VX, THIRD_TURN_VYAW, THIRD_TURN_DURATION)
    drive5 = [c for c in motion5.cmds if (c[1], c[2], c[3]) != (0.0, 0.0, 0.0)]
    assert drive5, "Phase5 转弯应下发驱动指令"
    assert drive5[0][1:] == (THIRD_TURN_VX, 0.0, THIRD_TURN_VYAW), \
        f"Phase5 转弯指令应为 ({THIRD_TURN_VX}, 0, {THIRD_TURN_VYAW})，实际 {drive5[0][1:]}"
    assert motion5.cmds[-1][1:] == (0.0, 0.0, 0.0), "Phase5 转弯结束应停车"
    print(f"  Phase5 PASS（第三个左转弯 vx={THIRD_TURN_VX} vyaw={THIRD_TURN_VYAW} {THIRD_TURN_DURATION:.2f}s = 第一弯一半，之后停车）")
    return True


def _test_run_maze_library():
    print("\n[4] run_maze_navigation 库函数（复用调用方控制线程）")
    recorded = []

    class _SimSport:
        def StopMove(self):
            recorded.append(("StopMove",))

    class FakeDriver:
        _sport = _SimSport()

        def set_command(self, vx, vy, vyaw):
            recorded.append((vx, vy, vyaw))

    # 打桩替代真实传感器/导航，只验证：建传感器 → 导航 → 收尾停车 + 停传感器
    orig_setup, orig_wait = MazeController._setup_sensors, MazeController._wait_for_sensors
    orig_cap, orig_nav = MazeController._capture_entrance_targets, MazeController._navigate
    MazeController._setup_sensors = lambda self: setattr(self, "_sensors", {})
    MazeController._wait_for_sensors = lambda self: True
    MazeController._capture_entrance_targets = lambda self: 350.0
    MazeController._navigate = lambda self, center: recorded.append(("navigate", center))
    try:
        run_maze_navigation(FakeDriver())
    finally:
        MazeController._setup_sensors, MazeController._wait_for_sensors = orig_setup, orig_wait
        MazeController._capture_entrance_targets, MazeController._navigate = orig_cap, orig_nav

    assert any(r[0] == "navigate" for r in recorded), "应执行导航"
    assert (0.0, 0.0, 0.0) in recorded, "收尾应下发停车指令"
    assert ("StopMove",) in recorded, "收尾应调用 sport.StopMove()"
    assert recorded[0][0] != "StopMove", "导航前不应先停车"
    print(f"  接线 PASS（建传感器 → navigate(350.0) → 停车 → StopMove），指令: {recorded}")
    return True


def _run_sim():
    print("=" * 62)
    print("  离线逻辑自检 (--sim，无需硬件)")
    print("=" * 62)
    ok = True
    for fn in (_test_filter, _test_vy, _test_phases, _test_run_maze_library):
        try:
            ok &= bool(fn())
        except AssertionError as e:
            print(f"  FAIL: {e}")
            ok = False
    print("=" * 62)
    print("  全部通过 ✓" if ok else "  存在失败 ✗")
    print("=" * 62)
    return 0 if ok else 1


# ============================================================
# 程序入口
# ============================================================
def main():
    sys.stdout = os.fdopen(sys.stdout.fileno(), "w", buffering=1)
    args = sys.argv[1:]
    if "--sim" in args:
        return _run_sim()
    if len(args) < 1:
        print(f"用法: {sys.argv[0]} <networkInterface> [--sim]")
        print(f"示例: {sys.argv[0]} eth0")
        return -1
    controller = MazeController(network_interface=args[0])
    controller.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
