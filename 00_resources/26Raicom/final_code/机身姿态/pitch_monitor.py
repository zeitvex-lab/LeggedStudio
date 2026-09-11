#!/usr/bin/env python3
"""
Go2 俯仰角实时监控 — 用于标定上台阶的俯仰阈值
==============================================
用法:
  python3 pitch_monitor.py <networkInterface>
  python3 pitch_monitor.py eth0

操作:
  - 程序启动后机器人站立不动
  - 手动推机器人上台阶，观察终端实时输出的俯仰角
  - 关注三个关键时刻的俯仰值:
    1. 前脚刚接触第一级台阶 → pitch 开始偏离 0
    2. 前脚踩到第三级台阶顶部 → pitch 开始回零
    3. 身体回平 → pitch 接近 0
  - 按 Ctrl+C 退出，程序自动打印统计摘要
"""

import sys
import os
import time
import math
import threading
import signal
import subprocess
import re
from collections import deque

from unitree_sdk2py.core.channel import (
    ChannelFactoryInitialize,
    ChannelSubscriber,
)
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
from unitree_sdk2py.go2.sport.sport_client import SportClient
from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import (
    MotionSwitcherClient,
)

TOPIC_HIGHSTATE = "rt/sportmodestate"

# ── 显示参数 ──
DISPLAY_HZ = 20              # 终端刷新频率
HISTORY_SECONDS = 5           # 历史窗口 (秒), 用于打印摘要


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
            if os.path.exists(operstate_file):
                with open(operstate_file) as f:
                    if f.read().strip() != "up":
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


class PitchMonitor:
    """实时监控 Go2 IMU 俯仰角"""

    def __init__(self, network_interface=""):
        self._robot_state = None
        self._lock = threading.Lock()
        self._running = True

        # 历史记录 (用于统计)
        self._history_len = HISTORY_SECONDS * DISPLAY_HZ
        self._pitch_history = deque(maxlen=self._history_len)
        self._roll_history = deque(maxlen=self._history_len)
        self._yaw_history = deque(maxlen=self._history_len)

        # 峰值追踪
        self._pitch_max = 0.0
        self._pitch_min = 0.0
        self._pitch_peak_time = 0.0

        # ── DDS 初始化 ──
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
            print("[WARN] 未收到机器人状态")
        else:
            print("[INIT] 状态接收正常")

    def _on_high_state(self, msg):
        with self._lock:
            self._robot_state = msg

    def _get_rpy(self):
        """返回 (roll, pitch, yaw) 单位: 度"""
        with self._lock:
            if self._robot_state is None:
                return (0.0, 0.0, 0.0)
            rpy = self._robot_state.imu_state.rpy
            return (
                math.degrees(float(rpy[0])),
                math.degrees(float(rpy[1])),
                math.degrees(float(rpy[2])),
            )

    def _init_robot(self):
        """基础初始化，让机器人站立"""
        print("[INIT] SelectMode('normal')...")
        self._msc.SelectMode("normal")
        time.sleep(2.0)

        print("[INIT] StandUp...")
        self._sport.StandUp()
        time.sleep(4.0)

        print("[INIT] SpeedLevel(1)...")
        self._sport.SpeedLevel(1)
        time.sleep(1.0)

        print("[INIT] ClassicWalk(True)...")
        self._sport.ClassicWalk(True)
        time.sleep(1.0)
        print("[INIT] Move(0,0,0) 锁定位置...")
        self._sport.Move(0.0, 0.0, 0.0)
        print("[INIT] ✓ 机器人已站立，可以开始推上台阶\n")

    def _bar(self, value, width=30, center=0.0, scale=30.0):
        """生成 ASCII 柱状图"""
        pos = int((value - center) / scale * width + width // 2)
        pos = max(0, min(width - 1, pos))
        bar = ["-"] * width
        bar[width // 2] = "|"  # 零点标记
        bar[pos] = "#"
        return "".join(bar)

    def run(self):
        self._init_robot()

        print("=" * 70)
        print("  俯仰角实时监控 — 推机器人上台阶观察 pitch 变化")
        print("  按 Ctrl+C 退出并查看统计摘要")
        print("=" * 70)
        print(f"  {'时间':>8s} │ {'俯仰(pitch)':>10s} │ {'翻滚(roll)':>10s} │ {'偏航(yaw)':>10s} │ 柱状图")
        print(f"  {'─'*8}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*32}")

        start_time = time.time()
        last_display = 0.0
        period = 1.0 / DISPLAY_HZ

        try:
            while self._running:
                now = time.time()
                if now - last_display < period:
                    time.sleep(0.005)
                    continue
                last_display = now

                roll, pitch, yaw = self._get_rpy()
                elapsed = now - start_time

                # 记录历史
                self._pitch_history.append(pitch)
                self._roll_history.append(roll)
                self._yaw_history.append(yaw)

                # 追踪峰值
                if pitch > self._pitch_max:
                    self._pitch_max = pitch
                    self._pitch_peak_time = elapsed
                if pitch < self._pitch_min:
                    self._pitch_min = pitch

                # 每次打印一行
                bar = self._bar(pitch, width=34, center=0.0, scale=15.0)
                marker = ""
                if abs(pitch) > 8:
                    marker = " ◀── 大幅偏离"
                elif abs(pitch) > 4:
                    marker = " ◀── 爬升中"
                elif abs(pitch) > 1.5:
                    marker = " ◀── 回零中"

                print(f"  {elapsed:7.1f}s │ {pitch:+9.2f}° │ {roll:+9.2f}° │ {yaw:+9.2f}° │ {bar}{marker}")

        except KeyboardInterrupt:
            print("\n[INFO] 用户中断")
        finally:
            self._running = False
            self._print_summary()
            self._shutdown()

    def _print_summary(self):
        print("\n" + "=" * 70)
        print("  统计摘要")
        print("=" * 70)

        if len(self._pitch_history) < 2:
            print("  数据不足")
            return

        pitches = list(self._pitch_history)
        rolls = list(self._roll_history)

        abs_pitches = [abs(p) for p in pitches]

        print(f"  俯仰角 (pitch):")
        print(f"    最大值:    {max(pitches):+.2f}°")
        print(f"    最小值:    {min(pitches):+.2f}°")
        print(f"    绝对最大值: {max(abs_pitches):.2f}°")
        print(f"    平均值:    {sum(pitches)/len(pitches):+.2f}°")

        # 统计在各阈值范围内的占比
        print(f"\n  阈值建议参考:")
        thresholds = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
        for t in thresholds:
            count_above = sum(1 for p in abs_pitches if p > t)
            pct = count_above / len(abs_pitches) * 100
            bar = "#" * int(pct / 2)
            print(f"    |pitch| > {t:4.1f}° : {count_above:5d} 帧 ({pct:5.1f}%) {bar}")

        print(f"\n  翻滚角 (roll):  max={max(rolls):+.2f}°  min={min(rolls):+.2f}°")
        print(f"  总采样帧数: {len(pitches)}")
        print(f"  采样时长:   {len(pitches)/DISPLAY_HZ:.1f}s")

        print(f"\n  💡 建议的阈值 (根据实际观察调整):")
        if max(abs_pitches) > 5:
            climbing = max(abs_pitches) * 0.5
            returning = max(abs_pitches) * 0.25
            stop = max(abs_pitches) * 0.1
        else:
            climbing = 4.0
            returning = 2.0
            stop = 1.0
        print(f"     P3_PITCH_CLIMBING_THRESH = math.radians({climbing:.0f})   # 判定\"正在爬升\"")
        print(f"     P3_PITCH_RETURN_THRESH  = math.radians({returning:.0f})   # 触发减速")
        print(f"     P3_PITCH_STOP_THRESH    = math.radians({stop:.1f})    # 触发停止")

    def _shutdown(self):
        print("\n[SHUTDOWN] 停止...")
        try:
            self._sport.StopMove()
            time.sleep(0.3)
        except Exception:
            pass
        print("[SHUTDOWN] 程序安全退出")


def main():
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

    if len(sys.argv) >= 2:
        network_iface = sys.argv[1]
    else:
        print("[INFO] 未指定网络接口，自动检测...")
        network_iface = auto_detect_interface()
        if network_iface is None:
            print("用法: python3 pitch_monitor.py <networkInterface>")
            print("示例: python3 pitch_monitor.py eth0")
            sys.exit(-1)

    print("=" * 60)
    print("  Go2 俯仰角实时监控 (Pitch Monitor)")
    print(f"  网络接口: {network_iface}")
    print("=" * 60)

    def on_signal(sig, frame):
        print("\n[STOP] 收到终止信号")
        sys.exit(0)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    try:
        monitor = PitchMonitor(network_interface=network_iface)
    except Exception as e:
        print(f"\n[ERROR] 初始化失败: {e}")
        auto_iface = auto_detect_interface()
        if auto_iface and auto_iface != network_iface:
            print(f"[INFO] 重试接口: {auto_iface}")
            monitor = PitchMonitor(network_interface=auto_iface)
        else:
            print("[FATAL] 无法找到可用网络接口")
            sys.exit(-1)

    monitor.run()


if __name__ == "__main__":
    main()
