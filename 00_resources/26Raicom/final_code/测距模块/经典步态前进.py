#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
经典步态前进 + 左转：前进 0.1 m/s，同时左转 0.05 rad/s（ClassicWalk 经典步态）。

直接运行，无需遥控器操作。运动控制复用 迷宫.py 的 MotionController，初始化
流程与 完整.py 一致（SelectMode → StandUp → SpeedLevel → ClassicWalk → Move）。

用法:
  python3 经典步态前进.py eth0            # 一直前进左转，直到 Ctrl-C
  python3 经典步态前进.py eth0 5          # 前进左转 5 秒后自动停止

可调参数在文件顶部（VX / VY / VYAW）。
"""

import os
import sys
import threading
import time

# ---- 让同目录 / 父目录模块可被导入 ----
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
for _p in (_HERE, _PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dds_lib_fix  # noqa: E402  必须先于 unitree_sdk2py（cyclonedds）
from 迷宫 import MotionController  # noqa: E402

# ============================================================
# 可调参数
# ============================================================
VX   = 0.25     # 前进速度 (m/s)
VYAW = 0.74    # 左转角速度 (rad/s)，正值 = 左转
VY   = 0.0     # 横向速度 (m/s)，正值 = 左移（若要"横向左移"而不是"转"就改这里）
CTRL_HZ = 100  # 控制线程发送频率


def main():
    sys.stdout = os.fdopen(sys.stdout.fileno(), "w", buffering=1)
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <networkInterface> [运行秒数]")
        print(f"示例: {sys.argv[0]} eth0 5")
        return -1
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else None

    print("=" * 56)
    print(f"  经典步态前进：vx={VX}m/s，左转 vyaw={VYAW}rad/s")
    print("=" * 56)

    ctrl = MotionController(network_interface=sys.argv[1])

    # ---- 初始化（与 完整.py 一致，经典步态） ----
    print("[INIT] SelectMode('normal') ...")
    ctrl._msc.SelectMode("normal")
    time.sleep(2.0)

    print("[INIT] StandUp ...")
    ctrl._sport.StandUp()
    time.sleep(4.0)

    print("[INIT] SpeedLevel(1) ...")
    ctrl._sport.SpeedLevel(1)
    time.sleep(1.0)

    print("[INIT] ClassicWalk(True) ...")
    ctrl._sport.ClassicWalk(True)
    time.sleep(1.0)

    ctrl._sport.Move(0.0, 0.0, 0.0)

    # ---- 启动控制线程（100Hz 持续发 Move 指令） ----
    ctrl._control_running = True
    drive_thread = threading.Thread(
        target=ctrl._control_loop, daemon=True, name="drive"
    )
    drive_thread.start()

    # ---- 前进 + 左转 ----
    ctrl.set_command(VX, VY, VYAW)
    print(f"[RUN] 前进 {VX}m/s + 左转 {VYAW}rad/s ..."
          + (f"（{duration}s 后自动停止）" if duration else "（Ctrl-C 停止）"))

    try:
        if duration:
            time.sleep(duration)
        else:
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[STOP] 用户中断")
    finally:
        ctrl.set_command(0.0, 0.0, 0.0)
        ctrl._control_running = False
        time.sleep(0.2)
        try:
            ctrl._sport.StopMove()
        except Exception:
            pass
        time.sleep(0.3)
        print("[STOP] 已停车（机器人保持站立）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
