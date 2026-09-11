#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中转放置 — D1 机械臂定点放置控制 (仅机械臂)
==========================================
基于 arm_sr-control.py, 只保留机械臂角度控制, 去掉 IK / 视觉 / 机器人等无关代码。

动作序列:
    预备放 → 放 → 松 → 抬

延时 (标准):
    预备放→放 : 2s 平滑 + 1s 到达后停留
    放→松     : 1s 平滑 (仅夹爪) + 1s 到达后停留
    松→抬     : 2s 平滑 + 1s 到达后停留
    抬执行完即结束

角度检测:
    每步平滑移动后轮询舵机角度反馈, 所有关节误差 ≤ ANGLE_TOLERANCE (5°)
    判定到位, 自动执行下一步, 不再靠固定延时。

用法:
    python3 中转放置.py eth0               # 连接机械臂执行
    python3 中转放置.py eth0 --dry-run     # 只打印动作序列, 不下发
"""

import os
import sys
import time
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import dds_lib_fix  # noqa: E402  (must run before cyclonedds, 修复 ddsi_sertype_v0 符号缺失)


# ============================================================
# 动作序列 (7 个关节角度: J0..J6, J6=夹爪, 12=夹紧, 60=松开)
# ============================================================

ACTIONS = [
    ("预备放", [80.0, 35.0, 18.0, -3.0, -77.0, 1.0, 19.0]),
    ("放",     [80.0, 57.0, 18.0, -3.0, -77.0, 1.0, 19.0]),
    ("松",     [80.0, 57.0, 18.0, -3.0, -77.0, 1.0, 40.0]),
    ("抬",     [80.0, 35.0, 18.0, -3.0, -77.0, 1.0, 60.0]),
]

# 每步执行参数: (平滑时长s, 到达后停留s), 依次对应 放/松/抬
# 平滑结束后轮询角度反馈, 所有关节误差 ≤ ANGLE_TOLERANCE 判定到位, 再停留 settle 秒
STEP_TIMING = [
    (0.7, 0.6),  # 预备放 → 放
    (0.4, 0.6),  # 放     → 松 (仅夹爪)
    (0.7, 0.6),  # 松     → 抬
]

ANGLE_TOLERANCE = 5.0  # 角度到位检测误差 (度)


# ============================================================
# DDS 通信层 (来自 arm_sr-control.py)
# ============================================================

def _init_dds_modules():
    """延迟导入 DDS 模块, 兼容离线模式 (--dry-run 不连接)"""
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _SDK_CANDIDATES = [
        os.path.join(_script_dir, "unitree_sdk2_python"),
        os.path.join(os.path.dirname(_script_dir), "unitree_sdk2_python"),
        os.path.join(os.path.expanduser("~"), "unitree_sdk2_python"),
        os.path.join(os.path.expanduser("~"), "1", "D1", "unitree_sdk2_python"),
    ]
    sdk_path = None
    for p in _SDK_CANDIDATES:
        if os.path.isdir(p):
            sdk_path = p
            break
    if sdk_path is None:
        raise ImportError("找不到 unitree_sdk2_python 目录")
    if sdk_path not in sys.path:
        sys.path.insert(0, sdk_path)

    from unitree_sdk2py.core.channel import ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize
    import cyclonedds.idl as idl
    import cyclonedds.idl.annotations as annotate
    import cyclonedds.idl.types as types
    from dataclasses import dataclass

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

    return (ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize,
            ArmString_, PubServoInfo_)


class D1DirectController:
    """D1 机械臂直接控制器 (发送角度指令, 无后台循环)"""

    def __init__(self, network_interface=None):
        (ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize,
         self._ArmString, self._PubServoInfo) = _init_dds_modules()

        self._interface = network_interface
        self._seq = 0
        self._pub = None
        self._angle_sub = None
        self._feedback_sub = None
        self._current_angles = [0.0] * 7
        self._angle_count = 0
        self._feedback_count = 0
        self._enabled = False

    def init(self):
        """初始化 DDS 通道, 等待角度数据"""
        (ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize, _, _) = _init_dds_modules()
        self._ChannelPublisher = ChannelPublisher
        self._ChannelSubscriber = ChannelSubscriber
        print(f"[DDS] 初始化 (interface={self._interface or 'auto'})")
        ChannelFactoryInitialize(0, self._interface)

        self._angle_sub = self._ChannelSubscriber("current_servo_angle", self._PubServoInfo)
        self._angle_sub.Init(self._on_angle, 10)
        print("[DDS] 已订阅 current_servo_angle")

        self._feedback_sub = self._ChannelSubscriber("rt/arm_Feedback", self._ArmString)
        self._feedback_sub.Init(self._on_feedback, 10)
        print("[DDS] 已订阅 rt/arm_Feedback")

        self._pub = self._ChannelPublisher("rt/arm_Command", self._ArmString)
        self._pub.Init()
        print("[DDS] 已创建 rt/arm_Command 发布器")

        print("[DDS] 等待舵机数据...")
        timeout = time.time() + 10.0
        while self._angle_count == 0 and time.time() < timeout:
            time.sleep(0.1)

        if self._angle_count > 0:
            angles = [round(a, 1) for a in self._current_angles]
            print(f"[DDS] 舵机已连接! 当前角度: {angles}")
        else:
            print("[DDS] 警告: 未收到舵机数据, 将继续尝试...")

    def _on_angle(self, msg):
        self._angle_count += 1
        self._current_angles = [
            msg.servo0_data_, msg.servo1_data_, msg.servo2_data_,
            msg.servo3_data_, msg.servo4_data_, msg.servo5_data_,
            msg.servo6_data_,
        ]

    def _on_feedback(self, msg):
        self._feedback_count += 1

    def _send(self, funcode, data=None, timeout=3.0):
        """发送 JSON 指令到机械臂"""
        self._seq += 1
        cmd = {"seq": self._seq, "address": 1, "funcode": funcode}
        if data:
            cmd["data"] = data
        json_str = json.dumps(cmd, ensure_ascii=False)
        ok = self._pub.Write(self._ArmString(json_str), timeout=timeout)
        if not ok:
            print(f"  [WARN] DDS Write 超时 (funcode={funcode})")
        return ok

    def enable(self):
        """使能关节 (funcode=5, mode=0)"""
        print("[Arm] 使能关节...")
        ok = self._send(5, {"mode": 0})
        if ok:
            self._enabled = True
            time.sleep(0.5)  # 等待使能生效
        else:
            print("[Arm] 错误: 使能失败! 检查机械臂是否上电")
        return ok

    def set_angles(self, angles):
        """设置 7 个关节角度 (funcode=2, mode=1)"""
        return self._send(2, {
            "mode": 1,
            "angle0": angles[0], "angle1": angles[1], "angle2": angles[2],
            "angle3": angles[3], "angle4": angles[4], "angle5": angles[5],
            "angle6": angles[6],
        })

    def smooth_move(self, target_angles, duration=2.0, steps=30):
        """平滑移动: 线性插值, 分步发送"""
        current = self._current_angles[:]
        if all(abs(a) < 0.1 for a in current):
            print("[Arm] 警告: 当前角度全为零, 直接跳转目标")
            self.set_angles(target_angles)
            time.sleep(duration)
            return

        dt = duration / steps
        for i in range(steps + 1):
            t = i / steps
            blended = [current[j] + t * (target_angles[j] - current[j])
                       for j in range(7)]
            self.set_angles(blended)
            time.sleep(dt)

    def wait_until_reached(self, target_angles, tolerance=5.0, timeout=30.0,
                           settle=0.5, check_interval=0.1):
        """轮询舵机角度反馈, 所有关节误差 <= tolerance 后返回 (到位自动触发下一步)

        Args:
            target_angles: 目标 7 关节角度 (度)
            tolerance: 到位判定误差 (度), 默认 5
            timeout: 最长等待 (秒), 超时告警并强制继续
            settle: 到位后额外停留 (秒), 让机械臂稳定
            check_interval: 轮询间隔 (秒)
        Returns:
            bool: 是否在超时前到位
        """
        start = time.time()
        last_report = 0.0
        while time.time() - start < timeout:
            current = self._current_angles
            max_err = max(abs(current[j] - target_angles[j]) for j in range(7))
            if max_err <= tolerance:
                print(f"    [检测] 已到位 (最大误差 {max_err:.1f}° ≤ {tolerance}°)")
                time.sleep(settle)
                return True
            now = time.time()
            if now - last_report >= 1.0:
                print(f"    [检测] 最大误差 {max_err:.1f}°, 等待到位...")
                last_report = now
            time.sleep(check_interval)

        max_err = max(abs(self._current_angles[j] - target_angles[j]) for j in range(7))
        print(f"    [WARN] 等待到位超时 ({timeout:.0f}s), 最大误差 {max_err:.1f}°, 强制继续")
        return False

    @property
    def current_angles(self):
        return self._current_angles[:]

    @property
    def is_connected(self):
        return self._angle_count > 0


# ============================================================
# 主流程: 连接 → 使能 → 执行动作序列
# ============================================================

def run_transfer_placement(network_interface=None, dry_run=False, arm=None):
    """执行中转放置动作序列: 预备放 → 放 → 松 → 抬 (连接 → 使能 → 执行)

    Args:
        network_interface: 网络接口 (如 eth0), dry_run 模式下可为 None
        dry_run: 仅打印动作序列, 不下发
        arm: 可选; 复用外部机械臂控制器 (需提供 smooth_move / wait_until_reached /
             current_angles / is_connected / enable), 不新建 DDS 通道。
            传入时由调用方负责初始化/使能。None 时自建 D1DirectController (独立 CLI 用)。

    Returns:
        int: 0 成功, 1 失败
    """
    if dry_run:
        print("[中转] dry-run 模式, 动作序列如下:")
        for name, angles in ACTIONS:
            print(f"  {name}: {[f'{a:.0f}' for a in angles]}")
        return 0

    if arm is None:
        if not network_interface:
            print("用法: python3 中转放置.py eth0   (或加 --dry-run 离线预览)")
            return 1

        arm = D1DirectController(network_interface)
        arm.init()

        # 智能使能: 已上电则跳过 (避免重复使能)
        current = arm.current_angles
        if arm.is_connected and not all(abs(a) < 0.1 for a in current):
            print(f"[中转] 机械臂已上电, 跳过使能 (当前角度: {[f'{a:.1f}' for a in current]})")
            arm._enabled = True
        else:
            if not arm.enable():
                print("[中转] 错误: 使能失败!")
                return 1

    print("\n[中转] 开始执行: 预备放 → 放 → 松 → 抬")
    print(f"      角度检测到位后自动下一步 (误差 ≤ {ANGLE_TOLERANCE}°)")

    # 1. 移动到预备放
    print(f"[中转] 预备放: {[f'{a:.0f}' for a in ACTIONS[0][1]]}")
    arm.smooth_move(ACTIONS[0][1], duration=2.0)
    arm.wait_until_reached(ACTIONS[0][1], tolerance=ANGLE_TOLERANCE)

    # 2. 依次执行 放 / 松 / 抬 (到位后自动进入下一步)
    for i in range(1, len(ACTIONS)):
        name, angles = ACTIONS[i]
        dur, settle = STEP_TIMING[i - 1]
        print(f"[中转] {ACTIONS[i-1][0]} → {name}: {[f'{a:.0f}' for a in angles]} (平滑{dur}s)")
        arm.smooth_move(angles, duration=dur)
        arm.wait_until_reached(angles, tolerance=ANGLE_TOLERANCE, settle=settle)

    print("[中转] 完成!")
    return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="中转放置 (仅机械臂控制)")
    parser.add_argument("interface", nargs="?", default=None,
                        help="网络接口 (如 eth0)")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印动作序列, 不下发")
    args = parser.parse_args()

    return run_transfer_placement(args.interface, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[中转] 已中断, 退出")
        sys.exit(1)
