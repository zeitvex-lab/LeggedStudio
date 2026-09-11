#!/usr/bin/env python3
"""
Go2 机身姿态读取程序
====================
读取并实时显示机器人的欧拉角 (roll, pitch, yaw)，单位：弧度。

对应 C++ SDK 的 int32_t Euler(float roll, float pitch, float yaw) 函数，
在 Python SDK 中通过 DDS 订阅 rt/sportmodestate 话题的 imu_state.rpy 获取。

用法:
  python3 read_attitude.py [network_interface]
  python3 read_attitude.py eth0
  python3 read_attitude.py             # 自动检测网络接口

按 Ctrl+C 退出。
"""

import sys
import os
import time
import math
import signal

# —— SDK 路径 ——
_script_dir = os.path.dirname(os.path.abspath(__file__))
_SDK_CANDIDATES = [
    os.path.join(_script_dir, "..", "unitree_sdk2_python"),
    os.path.join(os.path.dirname(_script_dir), "unitree_sdk2_python"),
    os.path.join(os.path.expanduser("~"), "unitree_sdk2_python"),
    os.path.join(os.path.expanduser("~"), "1", "D1", "unitree_sdk2_python"),
]
SDK_PATH = None
for _p in _SDK_CANDIDATES:
    if os.path.isdir(_p):
        SDK_PATH = os.path.abspath(_p)
        break
if SDK_PATH is None:
    print("[错误] 找不到 unitree_sdk2_python 目录!")
    sys.exit(1)
if SDK_PATH not in sys.path:
    sys.path.insert(0, SDK_PATH)

from unitree_sdk2py.core.channel import ChannelSubscriber, ChannelFactoryInitialize
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_


# ============================================================
# 全局状态 (线程安全由 DDS 回调保证)
# ============================================================
g_robot_state = None
g_running = True


def on_state(msg: SportModeState_):
    """DDS 回调：接收机器人状态"""
    global g_robot_state
    g_robot_state = msg


def signal_handler(sig, frame):
    """优雅退出"""
    global g_running
    g_running = False
    print("\n[退出] 收到中断信号，正在退出...")


def rad_to_deg(rad: float) -> float:
    """弧度转角度"""
    return rad * 180.0 / math.pi


def main():
    global g_running

    # 解析命令行参数
    interface = sys.argv[1] if len(sys.argv) > 1 else ""

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # —— 初始化 DDS ——
    print(f"[INIT] 初始化 DDS (interface={'auto' if not interface else interface})...")
    ChannelFactoryInitialize(0, interface)

    # —— 订阅运动状态 ——
    state_suber = ChannelSubscriber("rt/sportmodestate", SportModeState_)
    state_suber.Init(on_state, 10)

    # —— 等待首帧数据 ——
    print("[INIT] 等待机器人状态数据...")
    waited = 0
    while g_robot_state is None and waited < 50:
        time.sleep(0.1)
        waited += 1
    if g_robot_state is None:
        print("[ERROR] 超时未收到机器人状态! 请检查:")
        print("  1. 机器人是否已上电并处于运动模式")
        print("  2. 网络连接是否正常 (ping 192.168.123.161)")
        print("  3. 网络接口是否正确")
        sys.exit(1)

    print("[INIT] ✓ 已连接，开始读取姿态数据\n")

    # —— 主循环：实时读取并显示姿态 ——
    print(f"{'时间(s)':>8}  {'Roll(rad)':>10}  {'Pitch(rad)':>11}  {'Yaw(rad)':>10}"
          f"  {'Roll(°)':>9}  {'Pitch(°)':>10}  {'Yaw(°)':>9}")
    print("-" * 80)

    start_time = time.time()
    last_print = 0.0
    print_interval = 0.1  # 100ms 打印一次 (10Hz 显示)

    while g_running:
        if g_robot_state is None:
            time.sleep(0.01)
            continue

        now = time.time()
        if now - last_print < print_interval:
            time.sleep(0.01)
            continue
        last_print = now

        elapsed = now - start_time

        # —— 读取欧拉角 (rpy = [roll, pitch, yaw]) ——
        roll = float(g_robot_state.imu_state.rpy[0])
        pitch = float(g_robot_state.imu_state.rpy[1])
        yaw = float(g_robot_state.imu_state.rpy[2])

        # 打印 (弧度和角度)
        print(f"{elapsed:>8.2f}  {roll:>+10.4f}  {pitch:>+11.4f}  {yaw:>+10.4f}"
              f"  {rad_to_deg(roll):>+9.2f}  {rad_to_deg(pitch):>+10.2f}  {rad_to_deg(yaw):>+9.2f}")

    print("\n[退出] 姿态读取已停止.")


if __name__ == "__main__":
    main()
