#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
左右放置 — D1 机械臂左右侧定点放置控制 (仅机械臂)
============================================
由 左边放置.py + 右边放置.py 整合而成, 通过 side 参数选择方向。

动作序列:
    side="左": 放左抬起1 → 放左1 → 放左 → 放左松开 → 放左抬起2 → 平
    side="右": 放右抬起1 → 放右1 → 放右 → 放右松开 → 放右抬起2 → 平

角度检测:
    除最后一步 "平" 外, 每步平滑移动后轮询舵机角度反馈, 所有关节误差 ≤
    ANGLE_TOLERANCE (5°) 判定到位, 自动执行下一步。最后一步 "平" 发布指令
    后程序即结束, 不再检测角度。

用法:
    python3 左右放置.py eth0 左            # 连接机械臂, 左侧放置
    python3 左右放置.py eth0 右            # 连接机械臂, 右侧放置
    python3 左右放置.py eth0 左 --dry-run  # 只打印动作序列, 不下发

整合说明:
    run_placement() 接受可选参数 arm —— 由外部(如 完整.py)传入已存在的机械臂
    控制器时, 直接复用其 DDS 通道, 不再新建发布器/订阅器。这避免集成运行时
    在同一进程里堆叠多个 DDS 控制器导致机械臂卡顿。
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

ACTIONS = {
    "左": [
        ("放左抬起1", [-58.0, 18.0, 48.0, -2.0, -90.0, 0.0, 19.0]),
        ("放左1",     [-58.0, 33.0, 48.0, -2.0, -90.0, 0.0, 19.0]),
        ("放左",      [-58.0, 48.0, 48.0, -2.0, -90.0, 0.0, 19.0]),
        ("放左松开",  [-58.0, 48.0, 48.0, -2.0, -90.0, 0.0, 40.0]),
        ("放左抬起2", [-58.0, 18.0, 48.0, -2.0, -90.0, 0.0, 60.0]),
        ("平",        [-6.9, -87.0, 89.7, -0.3, 3.8, 0.3, 60.0]),
    ],
    "右": [
        ("放右抬起1", [54.0, 20.0, 46.0, 0.0, -88.0, 0.0, 19.0]),
        ("放右1",     [54.0, 33.0, 48.0, -2.0, -90.0, 0.0, 19.0]),
        ("放右",      [54.0, 48.0, 48.0, -2.0, -90.0, 0.0, 19.0]),
        ("放右松开",  [54.0, 47.0, 46.0, 0.0, -88.0, 0.0, 40.0]),
        ("放右抬起2", [54.0, 20.0, 46.0, 0.0, -88.0, 0.0, 60.0]),
        ("平",        [-6.9, -87.0, 89.7, -0.3, 3.8, 0.3, 60.0]),
    ],
}

# 每步执行参数: (平滑时长s, 到达后停留s), 依次对应 抬起1之后/1/松开/抬起2/平
STEP_TIMING = [
    (0.7, 0.6),  # 抬起1  → 1
    (0.7, 0.6),  # 1      → 平放
    (0.4, 0.6),  # 平放   → 松开 (仅夹爪)
    (0.7, 0.6),  # 松开   → 抬起2
    (0.7, 0.6),  # 抬起2  → 平
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
        """轮询舵机角度反馈, 所有关节误差 <= tolerance 后返回"""
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

def run_placement(network_interface=None, side="左", dry_run=False, arm=None):
    """执行左右侧定点放置动作序列 (side 侧: 抬起1 → 1 → 平放 → 松开 → 抬起2 → 平)

    Args:
        network_interface: 网络接口 (如 eth0), dry_run 模式下可为 None
        side: "左" 或 "右"
        dry_run: 仅打印动作序列, 不下发
        arm: 可选; 复用外部机械臂控制器 (需提供 smooth_move / wait_until_reached /
             current_angles / is_connected / enable), 不新建 DDS 通道。
            传入时由调用方负责初始化/使能。None 时自建 D1DirectController (独立 CLI 用)。

    Returns:
        int: 0 成功, 1 失败
    """
    side = "右" if side == "右" else "左"

    if dry_run:
        print(f"[左右] dry-run 模式 (side={side}) 动作序列如下:")
        for name, angles in ACTIONS[side]:
            print(f"  {name}: {[f'{a:.0f}' for a in angles]}")
        return 0

    if arm is None:
        if not network_interface:
            print("用法: python3 左右放置.py eth0 左   (或加 --dry-run 离线预览)")
            return 1

        arm = D1DirectController(network_interface)
        arm.init()

        # 智能使能: 已上电则跳过 (避免重复使能)
        current = arm.current_angles
        if arm.is_connected and not all(abs(a) < 0.1 for a in current):
            print(f"[左右] 机械臂已上电, 跳过使能 (当前角度: {[f'{a:.1f}' for a in current]})")
            arm._enabled = True
        else:
            if not arm.enable():
                print("[左右] 错误: 使能失败!")
                return 1

    print(f"\n[左右] 开始执行 {side}侧放置: 抬起1 → 1 → 平放 → 松开 → 抬起2 → 平")
    print(f"      角度检测到位后自动下一步 (误差 ≤ {ANGLE_TOLERANCE}°); 最后一步 \"平\" 仅发布, 不检测")

    # 1. 移动到抬起1
    print(f"[左右] {ACTIONS[side][0][0]}: {[f'{a:.0f}' for a in ACTIONS[side][0][1]]}")
    arm.smooth_move(ACTIONS[side][0][1], duration=1.0)
    arm.wait_until_reached(ACTIONS[side][0][1], tolerance=ANGLE_TOLERANCE)

    # 2. 依次执行后续动作 (到位后自动进入下一步)
    for i in range(1, len(ACTIONS[side])):
        name, angles = ACTIONS[side][i]
        dur, settle = STEP_TIMING[i - 1]
        print(f"[左右] {ACTIONS[side][i-1][0]} → {name}: {[f'{a:.0f}' for a in angles]} (平滑{dur}s)")
        arm.smooth_move(angles, duration=dur)
        # 最后一步 "平": 平滑指令已发布, 不再检测角度, 程序即可结束
        if i == len(ACTIONS[side]) - 1:
            print("[左右] 最后一步已发布, 跳过角度检测, 程序结束")
        else:
            arm.wait_until_reached(angles, tolerance=ANGLE_TOLERANCE, settle=settle)

    print("[左右] 完成!")
    return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="左右放置 (仅机械臂控制)")
    parser.add_argument("interface", nargs="?", default=None,
                        help="网络接口 (如 eth0)")
    parser.add_argument("side", nargs="?", default="左", choices=["左", "右"],
                        help="放物方向: 左 / 右")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印动作序列, 不下发")
    args = parser.parse_args()

    return run_placement(args.interface, side=args.side, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[左右] 已中断, 退出")
        sys.exit(1)
