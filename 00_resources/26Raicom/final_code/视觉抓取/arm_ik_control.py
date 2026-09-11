#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D1 机械臂 XYZ 坐标控制 (基于 IK 求解, Angle.py 模式)
=================================================
通过逆运动学将 XYZ 厘米坐标转换为关节角度, 直接通过 DDS 发送指令控制机械臂。

参考原点 (0, 0, 0) cm = 关节角度 (82, 10, 55, -2, -61, 1, 60)°
坐标单位: 1 单位 = 1 cm 现实世界

控制模式: 参照 Angle.py, 直接发送角度指令, 不使用后台控制循环。
          发送使能 → 执行动作 → 保持使能状态。

用法:
    python3 arm_ik_control.py eth0 --xyz 5 0 3    # 单次移动
    python3 arm_ik_control.py eth0 -i              # 交互模式
    python3 arm_ik_control.py --dry-run --xyz 5 0 3  # 离线 IK 测试
"""

import sys
import os
import time
import json
import argparse

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))  # 父目录(final_code), 使 dds_lib_fix 可导入
import dds_lib_fix  # noqa: E402  (must run before cyclonedds)

from d1_forward_kinematics import D1ForwardKinematics
from d1_ik_solver import D1InverseKinematics, D1ReachabilityAnalyzer

# ============================================================
# 参考姿态
# ===========================================================

REF_JOINT_ANGLES = [-90.0, 10.0, 55.0, 0.0, -61.0, 0.0, 60.0]


# ============================================================
# DDS 通信层 (参照 Angle.py)
# ============================================================

def _init_dds_modules():
    """延迟导入 DDS 模块, 兼容离线模式"""
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
    """D1 机械臂直接控制器 (Angle.py 模式: 发送指令, 无后台循环)"""

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

    # ---- 初始化 ----

    def init(self):
        """初始化 DDS 通道, 等待角度数据"""
        (ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize, _, _) = _init_dds_modules()
        self._ChannelPublisher = ChannelPublisher
        self._ChannelSubscriber = ChannelSubscriber
        print(f"[DDS] 初始化 (interface={self._interface or 'auto'})")
        ChannelFactoryInitialize(0, self._interface)

        # 订阅角度
        self._angle_sub = self._ChannelSubscriber("current_servo_angle", self._PubServoInfo)
        self._angle_sub.Init(self._on_angle, 10)
        print("[DDS] 已订阅 current_servo_angle")

        # 订阅反馈
        self._feedback_sub = self._ChannelSubscriber("rt/arm_Feedback", self._ArmString)
        self._feedback_sub.Init(self._on_feedback, 10)
        print("[DDS] 已订阅 rt/arm_Feedback")

        # 发布器
        self._pub = self._ChannelPublisher("rt/arm_Command", self._ArmString)
        self._pub.Init()
        print("[DDS] 已创建 rt/arm_Command 发布器")

        # 等待角度数据
        print("[DDS] 等待舵机数据...")
        timeout = time.time() + 10.0
        while self._angle_count == 0 and time.time() < timeout:
            time.sleep(0.1)
            elapsed = time.time() - (timeout - 10.0)
            if elapsed > 3 and int(elapsed) % 3 == 0:
                # 避免刷屏, 只在特定秒数打印
                pass

        if self._angle_count > 0:
            angles = [round(a, 1) for a in self._current_angles]
            print(f"[DDS] 舵机已连接! 当前角度: {angles}")
        else:
            print("[DDS] 警告: 未收到舵机数据, 将继续尝试...")

    # ---- 回调 ----

    def _on_angle(self, msg):
        self._angle_count += 1
        self._current_angles = [
            msg.servo0_data_, msg.servo1_data_, msg.servo2_data_,
            msg.servo3_data_, msg.servo4_data_, msg.servo5_data_,
            msg.servo6_data_,
        ]

    def _on_feedback(self, msg):
        self._feedback_count += 1

    # ---- 发送指令 ----

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

    def smooth_move(self, target_angles, duration=1.4, steps=30):
        """平滑移动: 线性插值, 分步发送

        不使用后台循环, 每一步直接发送指令 + sleep。
        步数少 (30步) 以降低 DDS 负载。
        """
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

    @property
    def current_angles(self):
        return self._current_angles[:]

    @property
    def is_connected(self):
        return self._angle_count > 0


# ============================================================
# IK 控制器
# ============================================================

class IKController:
    """离线 IK 控制器: 输入 XYZ cm, 输出关节角度"""

    def __init__(self, j4_bias=0.0, j4_scale_x_pos=0.0, j4_scale_x_neg=0.0,
                 j4_scale_y=0.0, j4_scale_z=0.0):
        self.fk = D1ForwardKinematics()
        self.analyzer = D1ReachabilityAnalyzer(self.fk)
        self.ik = D1InverseKinematics(
            self.fk,
            ref_angles=REF_JOINT_ANGLES[:6],
            damping=0.3,
            max_iters=200,
            tol_position=0.1,
            nullspace_gain=0.0,
        )
        self._gripper_angle = REF_JOINT_ANGLES[6]
        self.j4_bias = j4_bias
        self.j4_scale_x_pos = j4_scale_x_pos  # X>0 (前方) 补偿
        self.j4_scale_x_neg = j4_scale_x_neg  # X<0 (后方) 补偿
        self.j4_scale_y = j4_scale_y
        self.j4_scale_z = j4_scale_z

    def xyz_to_joints(self, x_cm, y_cm, z_cm, gripper=None, lock_j0=None):
        """XYZ 厘米坐标 -> 7 个关节角度 (度), 保持末端姿态水平

        Args:
            x_cm, y_cm, z_cm: 目标坐标 (cm)
            gripper: 夹爪角度 (度)
            lock_j0: 锁定底座角度 (度); None = 底座自由 (居中/对中时由 IK 决定)

        锁定底座 (lock_j0 非 None) 时, Y 表示沿当前底座方位角的径向伸出距离
        (负 = 伸出), 目标点落在锁定底座角度的竖直平面内, 因此底座 (J0) 角度
        在整个伸出/升降过程中保持不变, 只有对中 (lock_j0=None) 才会转动底座。
        """
        # J4 补偿 = 偏置 + X(正/负分离) + Y + Z
        x_contrib = (self.j4_scale_x_pos * x_cm if x_cm > 0
                     else self.j4_scale_x_neg * abs(x_cm))
        j4_offset = (self.j4_bias + x_contrib +
                     self.j4_scale_y * abs(y_cm) +
                     self.j4_scale_z * abs(z_cm))
        j4_target = REF_JOINT_ANGLES[4] + j4_offset if abs(j4_offset) > 0.01 else None
        # 构建锁定关节: J3=0, J4=目标值, J5=0
        locked = {3: 0.0, 5: 0.0}
        if j4_target is not None:
            locked[4] = j4_target
        else:
            locked[4] = REF_JOINT_ANGLES[4]  # 参考 J4

        if lock_j0 is not None:
            # 锁定底座: 把径向 (Y) + 高度 (Z) 转换到基坐标系,
            # 使目标位于锁定底座角度的竖直平面内, 底座无需转动。
            locked[0] = float(lock_j0)
            u_x = np.cos(np.deg2rad(lock_j0))
            u_y = np.sin(np.deg2rad(lock_j0))
            r_ref = np.hypot(self.ik.ref_position[0], self.ik.ref_position[1])
            r_target = r_ref - y_cm * 10.0   # Y 负 = 伸出 → 半径增大 (mm)
            tx = u_x * r_target
            ty = u_y * r_target
            x_cm = (tx - self.ik.ref_position[0]) / 10.0
            y_cm = (ty - self.ik.ref_position[1]) / 10.0

        angles_6dof, success, info = self.ik.solve_relative_xyz_with_orientation(
            x_cm, y_cm, z_cm, ori_weight=0.0,  # J4/J5 已锁定, 无需姿态约束
            locked_joints=locked)
        if gripper is not None:
            self._gripper_angle = gripper
        angles_7dof = list(angles_6dof) + [self._gripper_angle]

        target_mm = self.ik.ref_position + np.array([x_cm * 10, y_cm * 10, z_cm * 10])
        reachable = self.analyzer.check_reachable(target_mm)
        if not reachable:
            dist = np.linalg.norm(target_mm)
            print(f"[IK] 警告: 目标距离 {dist:.0f}mm 可能超出工作空间")

        return angles_7dof, success, info

    def print_move_info(self, x_cm, y_cm, z_cm, angles_7dof, info):
        """打印移动信息"""
        print(f"\n{'='*60}")
        print(f"  目标: ({x_cm:+.1f}, {y_cm:+.1f}, {z_cm:+.1f}) cm")
        print(f"  收敛: {'OK' if info['error_mm'] < 0.5 else '△'}")
        print(f"  位置误差: {info['error_mm']:.2f} mm")
        if 'error_ori_deg' in info:
            print(f"  姿态误差: {info['error_ori_deg']:.2f} deg")
        if 'j4_angle' in info:
            print(f"  J4角度: {info['j4_angle']:.1f} deg (参考={self.ik.ref_angles[4]:.0f})")
        print(f"  迭代: {info['iterations']}")
        print(f"  关节: {[f'{a:+.1f}' for a in angles_7dof]} deg")
        T = self.fk.forward_kinematics(angles_7dof[:6])
        p = T[:3, 3]
        offset = (p - self.ik.ref_position) / 10.0
        print(f"  末端: [{p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f}] mm")
        print(f"  偏移: ({offset[0]:+.1f}, {offset[1]:+.1f}, {offset[2]:+.1f}) cm")
        print(f"{'='*60}")


# ============================================================
# 在线控制
# ============================================================

class ArmIKController:
    """在线 IK 控制器: IK 解算 + DDS 直接控制"""

    def __init__(self, network_interface=None, j4_bias=0.0,
                 j4_scale_x_pos=0.0, j4_scale_x_neg=0.0,
                 j4_scale_y=0.0, j4_scale_z=0.0):
        self.ik_ctrl = IKController(j4_bias=j4_bias,
                                    j4_scale_x_pos=j4_scale_x_pos,
                                    j4_scale_x_neg=j4_scale_x_neg,
                                    j4_scale_y=j4_scale_y,
                                    j4_scale_z=j4_scale_z)
        self.arm = D1DirectController(network_interface)

    def init(self, force_enable=False):
        """初始化 DDS, 智能使能 (已上电则跳过)

        Args:
            force_enable: 强制重新使能 (即使已上电)
        """
        self.arm.init()

        # 读取当前角度判断机械臂状态
        current = self.arm.current_angles
        all_zero = all(abs(a) < 0.1 for a in current)
        already_enabled = self.arm.is_connected and not all_zero

        if already_enabled and not force_enable:
            print(f"[ArmIK] 机械臂已上电, 跳过使能 (当前角度: {[f'{a:.1f}' for a in current]} deg)")
            self.arm._enabled = True
        else:
            if all_zero:
                print("[ArmIK] 检测到角度全为零, 需要使能...")
            elif force_enable:
                print("[ArmIK] 强制使能...")
            if not self.arm.enable():
                raise RuntimeError("机械臂使能失败")

        current = self.arm.current_angles
        print(f"[ArmIK] 当前角度: {[f'{a:.1f}' for a in current]} deg")
        print("[ArmIK] 就绪")

    def move_to_xyz(self, x_cm, y_cm, z_cm, gripper=None,
                    smooth=True, duration=2.0, lock_j0=None):
        """移动到指定 XYZ 坐标 (cm)

        Args:
            lock_j0: 锁定底座角度 (度); None = 底座自由 (对中/居中时使用)
        """
        angles_7dof, success, info = self.ik_ctrl.xyz_to_joints(
            x_cm, y_cm, z_cm, gripper, lock_j0=lock_j0)
        self.ik_ctrl.print_move_info(x_cm, y_cm, z_cm, angles_7dof, info)

        if not success:
            print("[ArmIK] 警告: IK 未完全收敛, 继续执行...")

        if smooth:
            self.arm.smooth_move(angles_7dof, duration=duration)
        else:
            self.arm.set_angles(angles_7dof)

        return angles_7dof, success, info

    def move_to_home(self, smooth=True):
        """回到参考原点"""
        print("[ArmIK] 回到原点...")
        if smooth:
            self.arm.smooth_move(REF_JOINT_ANGLES, duration=2.0)
        else:
            self.arm.set_angles(REF_JOINT_ANGLES)

    def print_status(self):
        """打印当前状态"""
        current = self.arm.current_angles
        print(f"\n当前角度: {[f'{a:.1f}' for a in current]} deg")
        print(f"连接状态: {'已连接' if self.arm.is_connected else '未连接'}")
        self.ik_ctrl.ik.print_status()


# ============================================================
# 交互模式
# ============================================================

def interactive_mode(controller, use_arm=True):
    """XYZ 控制交互模式"""
    print("""
+--------------------------------------------------+
|   D1 机械臂 XYZ 坐标控制                           |
+--------------------------------------------------+
|  xyz X Y Z     - 移动到坐标 (cm)                   |
|  xyz X Y Z G   - 移动到坐标 + 夹爪角度              |
|  xyz X Y Z d=D - 平滑移动 (时长秒, 默认2)           |
|  home          - 回到参考原点                       |
|  status        - 当前状态                          |
|  ik X Y Z      - 仅计算 IK (不下发)                |
|  quit          - 退出                             |
|                                                   |
|  参考原点: [82,10,55,0,-61,0,60] deg               |
|  单位: 1 = 1 cm, X+前 Y+左 Z+上                   |
+--------------------------------------------------+
""")

    ik = controller.ik_ctrl if use_arm else controller
    xyz_history = []

    while True:
        try:
            cmd_line = input("\nxyz> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出")
            break

        if not cmd_line:
            continue

        parts = cmd_line.split()
        command = parts[0].lower()

        try:
            if command in ("quit", "exit", "q"):
                break

            elif command == "home":
                if use_arm:
                    controller.move_to_home()
                else:
                    print(f"参考关节: {REF_JOINT_ANGLES} deg")
                xyz_history = []

            elif command == "status":
                if use_arm:
                    controller.print_status()
                else:
                    ik.ik.print_status()
                    print(f"历史: {xyz_history}")

            elif command == "ik":
                if len(parts) < 4:
                    print("用法: ik X Y Z")
                    continue
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                angles, ok, info = ik.xyz_to_joints(x, y, z)
                ik.print_move_info(x, y, z, angles, info)

            elif command == "xyz":
                if len(parts) < 4:
                    print("用法: xyz X Y Z [gripper] [d=duration]")
                    continue

                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])

                gripper = None
                duration = 2.0
                for p in parts[4:]:
                    if p.startswith("d="):
                        duration = float(p[2:])
                    else:
                        try:
                            gripper = float(p)
                        except ValueError:
                            pass

                if use_arm:
                    controller.move_to_xyz(x, y, z, gripper=gripper,
                                           duration=duration)
                else:
                    angles, ok, info = ik.xyz_to_joints(x, y, z, gripper)
                    ik.print_move_info(x, y, z, angles, info)

                xyz_history.append((x, y, z))

            else:
                print("可用命令: xyz, home, ik, status, quit")
                print("示例: xyz 5 0 3       - 移动到 X+5, Z+3 cm")
                print("      xyz 0 0 -5 d=3  - 3秒下降到 Z-5 cm")

        except (ValueError, IndexError) as e:
            print(f"参数错误: {e}")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="D1 机械臂 XYZ 坐标控制 (IK 求解)")
    parser.add_argument("interface", nargs="?", default=None,
                        help="网络接口 (如 eth0)")
    parser.add_argument("--xyz", "-x", nargs=3, type=float, default=None,
                        metavar=("X", "Y", "Z"),
                        help="移动到指定 XYZ 坐标 (cm)")
    parser.add_argument("--gripper", "-g", type=float, default=None,
                        help="夹爪角度 (deg)")
    parser.add_argument("--duration", "-d", type=float, default=2.0,
                        help="平滑移动时长 (秒, 默认 2.0)")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="进入交互模式")
    parser.add_argument("--dry-run", action="store_true",
                        help="离线模式 (不连接机械臂)")
    parser.add_argument("--force-enable", action="store_true",
                        help="强制重新使能 (即使机械臂已上电)")
    parser.add_argument("--j4-scale-y", type=float, default=0.73,
                        help="J4 Y轴补偿 (deg/cm), 默认 0.73")
    parser.add_argument("--j4-scale-x-pos", type=float, default=1.3,
                        help="J4 X轴前方补偿 (deg/cm), X>0时, 默认 1.3")
    parser.add_argument("--j4-scale-x-neg", type=float, default=-0.1,
                        help="J4 X轴后方补偿 (deg/cm), X<0时, 默认 -0.1")
    parser.add_argument("--j4-scale-z", type=float, default=0.0,
                        help="J4 Z轴补偿 (deg/cm)")
    parser.add_argument("--j4-bias", type=float, default=0.0,
                        help="J4 固定偏置 (deg)")
    args = parser.parse_args()

    use_arm = not args.dry_run and args.interface is not None

    if use_arm:
        print(f"[ArmIK] 初始化 (j4: x+={args.j4_scale_x_pos} x-={args.j4_scale_x_neg} y={args.j4_scale_y})")
        controller = ArmIKController(args.interface,
                                     j4_bias=args.j4_bias,
                                     j4_scale_x_pos=args.j4_scale_x_pos,
                                     j4_scale_x_neg=args.j4_scale_x_neg,
                                     j4_scale_y=args.j4_scale_y,
                                     j4_scale_z=args.j4_scale_z)
        try:
            controller.init(force_enable=args.force_enable)
        except Exception as e:
            print(f"[ERROR] 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return 1
    else:
        print(f"[ArmIK] 离线 IK 模式 (j4: x+={args.j4_scale_x_pos} x-={args.j4_scale_x_neg} y={args.j4_scale_y})")
        controller = IKController(j4_bias=args.j4_bias,
                                  j4_scale_x_pos=args.j4_scale_x_pos,
                                  j4_scale_x_neg=args.j4_scale_x_neg,
                                  j4_scale_y=args.j4_scale_y,
                                  j4_scale_z=args.j4_scale_z)

    try:
        if args.xyz is not None:
            x, y, z = args.xyz
            if use_arm:
                controller.move_to_xyz(x, y, z, gripper=args.gripper,
                                       duration=args.duration)
            else:
                angles, ok, info = controller.xyz_to_joints(x, y, z, args.gripper)
                controller.print_move_info(x, y, z, angles, info)
            return 0

        if args.interactive:
            interactive_mode(controller, use_arm=use_arm)
        elif not use_arm:
            parser.print_help()
        else:
            print("[ArmIK] 运行中 (Ctrl+C 退出)")
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        print("\n[ArmIK] 退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
