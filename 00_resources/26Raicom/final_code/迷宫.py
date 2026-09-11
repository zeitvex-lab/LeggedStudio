#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Go2 定序运动控制（经典步态）
流程：前进 → 左转90° → 前进 → 左转90° → 前进 → 右转90° → 前进 → 右转90° → 前进 → 左转90°
"""
import sys
import os
import time
import math
import threading

from unitree_sdk2py.core.channel import (
    ChannelFactoryInitialize,
    ChannelSubscriber,
)
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_
from unitree_sdk2py.go2.sport.sport_client import SportClient
from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import (
    MotionSwitcherClient,
)

# ============================================================
# 全局可调参数（直接修改这里即可调整运动参数）
# ============================================================
BASE_FORWARD_SPEED = 0.25    # 前进速度 (m/s)
BASE_STRAFE_SPEED = 0.20     # 横向平移速度 (m/s)
TURN_SPEED = 1.2             # 转弯角速度 (rad/s)，正值左转，负值右转
CTRL_HZ = 100                # 运动指令发送频率
TURN_TIMEOUT = 10.0          # 转弯超时保护(秒)，防止IMU异常导致持续旋转

# 动作序列格式：
#   forward    : ("forward", duration_seconds)
#   move_right : ("move_right", duration_seconds)
#   turn_left  : ("turn_left", angle_deg, [micro_turn_deg], [micro_forward_duration], [micro_forward_speed], [turn_speed])
#   turn_right : ("turn_right", angle_deg, [micro_turn_deg], [micro_forward_duration], [micro_forward_speed], [turn_speed])
# 转弯参数若省略，则自动使用下方的全局默认值
ACTION_SEQUENCE = [
    ("forward", 7.1),       # 1. 前进
    ("turn_left", 80,        # 2. 左转：角度, 微调步长°, 微调前进s, 微调速度m/s, 角速度rad/s
     7.0, 0.8, 0.12, 1.35),
    # ("forward", 0.28),
    ("turn_left", 65,        # 3. 左转
     7.0, 0.8, 0.126, 1.55),
     ("move_right", 0.3),    # 3.5 向右平移 0.5s
    ("forward", 1.8),     # 4. 前进
    ("turn_right", 80,       # 5. 右转
     7.0, 0.8, 0.12, 1.17),
    ("forward", 0.5),
    ("turn_right", 70,     # 6. 右转
     7.0, 0.8, 0.15, 1.62),
    ("forward", 1.8),
    ("turn_left", 65,      # 7. 左转
    7.0, 0.8, 0.145, 1.3),
]

# ============================================================
# 微调转弯默认参数（转一点 → 前进一点 → 再转，防止撞围栏）
# 每个转弯可在 ACTION_SEQUENCE 中单独覆盖这些值
# ============================================================
MICRO_TURN_DEG = 7.0          # 每次微调转的角度（度），越小越精细
MICRO_FORWARD_DURATION = 0.8   # 每次微调后前进时间（秒）
MICRO_FORWARD_SPEED = 0.13     # 微调前进速度 (m/s)，比正常前进慢

# ============================================================
# 运动控制器
# ============================================================
class MotionController:
    def __init__(self, network_interface: str = ""):
        self._cmd_lock = threading.Lock()
        self._target_vx = 0.0
        self._target_vy = 0.0
        self._target_vyaw = 0.0
        self._robot_state = None
        self._robot_state_lock = threading.Lock()
        self._running = True
        self._control_running = True

        # 初始化DDS通信
        print("[INIT] 初始化 ChannelFactory...")
        if network_interface:
            ChannelFactoryInitialize(0, network_interface)
        else:
            ChannelFactoryInitialize(0)

        # 运动模式切换客户端
        self._msc = MotionSwitcherClient()
        self._msc.SetTimeout(5.0)
        self._msc.Init()

        # 运动控制客户端
        self._sport = SportClient()
        self._sport.SetTimeout(10.0)
        self._sport.Init()

        # 订阅机器人状态（用于获取IMU航向角）
        print("[INIT] 订阅机器人状态主题...")
        self._state_suber = ChannelSubscriber("rt/sportmodestate", SportModeState_)
        self._state_suber.Init(self._on_high_state, 10)

        # 等待首帧机器人状态
        print("[INIT] 等待机器人状态反馈...")
        waited = 0
        while self._robot_state is None and waited < 30:
            time.sleep(0.1)
            waited += 1
        if self._robot_state is None:
            print("[WARN] 未收到IMU状态，转弯将自动降级为时间估算模式")

    def _on_high_state(self, msg: SportModeState_):
        """接收机器人状态回调"""
        with self._robot_state_lock:
            self._robot_state = msg

    def _get_yaw(self) -> float:
        """获取当前航向角（弧度）"""
        with self._robot_state_lock:
            if self._robot_state is None:
                return 0.0
            return float(self._robot_state.imu_state.rpy[2])

    @staticmethod
    def _normalize_angle(angle: float) -> float:
        """角度归一化到 [-π, π]"""
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    def set_command(self, vx: float, vy: float, vyaw: float):
        """设置目标运动速度"""
        with self._cmd_lock:
            self._target_vx = vx
            self._target_vy = vy
            self._target_vyaw = vyaw

    def _get_command(self):
        """获取当前目标速度"""
        with self._cmd_lock:
            return (self._target_vx, self._target_vy, self._target_vyaw)

    def _control_loop(self):
        """控制线程：周期性发送速度指令（Go2需要持续发指令才会保持运动）"""
        print("[CTRL] 运动控制线程启动")
        period = 1.0 / CTRL_HZ
        while self._control_running:
            vx, vy, vyaw = self._get_command()
            self._sport.Move(vx, vy, vyaw)
            time.sleep(period)
        print("[CTRL] 运动控制线程退出")

    def _enable_classic_walk(self):
        """启用经典步态"""
        try:
            self._sport.ClassicWalk(True)
            print("[GAIT] 经典步态 ClassicWalk 已启用")
        except Exception as e:
            print(f"[GAIT] 经典步态启用异常: {e}")
        time.sleep(0.3)

    def go_forward(self, duration: float):
        """前进指定时长（秒）"""
        print(f"[动作] 前进 {duration}s，速度 {BASE_FORWARD_SPEED}m/s")
        self.set_command(BASE_FORWARD_SPEED, 0.0, 0.0)
        time.sleep(duration)
        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.1)
        print("[动作] 前进完成")

    def move_right(self, duration: float):
        """向右平移指定时长（秒），vy负值表示右移"""
        print(f"[动作] 向右平移 {duration}s，速度 {BASE_STRAFE_SPEED}m/s")
        self.set_command(0.0, -BASE_STRAFE_SPEED, 0.0)
        time.sleep(duration)
        self.set_command(0.0, 0.0, 0.0)
        time.sleep(0.1)
        print("[动作] 向右平移完成")

    def turn_left(self, angle_deg: float,
                  micro_turn_deg: float = None,
                  micro_forward_duration: float = None,
                  micro_forward_speed: float = None,
                  turn_speed: float = None):
        """左转指定角度（度），微调步进模式。

        Args:
            angle_deg: 目标左转角度（度）
            micro_turn_deg: 每次微调转角（度），None则用全局默认
            micro_forward_duration: 微调后前进时长（秒），None则用全局默认
            micro_forward_speed: 微调前进速度（m/s），None则用全局默认
            turn_speed: 转弯角速度（rad/s），None则用全局默认 TURN_SPEED
        """
        self._turn_with_micro_steps(angle_deg, turn_direction=1,
                                    micro_turn_deg=micro_turn_deg,
                                    micro_forward_duration=micro_forward_duration,
                                    micro_forward_speed=micro_forward_speed,
                                    turn_speed=turn_speed)

    def turn_right(self, angle_deg: float,
                   micro_turn_deg: float = None,
                   micro_forward_duration: float = None,
                   micro_forward_speed: float = None,
                   turn_speed: float = None):
        """右转指定角度（度），微调步进模式。

        Args:
            angle_deg: 目标右转角度（度）
            micro_turn_deg: 每次微调转角（度），None则用全局默认
            micro_forward_duration: 微调后前进时长（秒），None则用全局默认
            micro_forward_speed: 微调前进速度（m/s），None则用全局默认
            turn_speed: 转弯角速度（rad/s），None则用全局默认 TURN_SPEED
        """
        self._turn_with_micro_steps(angle_deg, turn_direction=-1,
                                    micro_turn_deg=micro_turn_deg,
                                    micro_forward_duration=micro_forward_duration,
                                    micro_forward_speed=micro_forward_speed,
                                    turn_speed=turn_speed)

    def _turn_with_micro_steps(self, target_angle_deg: float, turn_direction: int,
                              micro_turn_deg: float = None,
                              micro_forward_duration: float = None,
                              micro_forward_speed: float = None,
                              turn_speed: float = None):
        """微调步进转弯：转 micro_turn_deg° → 停 → 前进一小段 → 停，循环直到完成目标角度。

        Args:
            target_angle_deg: 目标总转角（度，正数）
            turn_direction: 1=左转, -1=右转
            micro_turn_deg: 每次微调转的角度（度），None则用全局默认 MICRO_TURN_DEG
            micro_forward_duration: 每次微调后前进时间（秒），None则用全局默认
            micro_forward_speed: 微调前进速度（m/s），None则用全局默认
            turn_speed: 转弯角速度（rad/s），None则用全局默认 TURN_SPEED
        """
        # 未指定则使用全局默认值
        if micro_turn_deg is None:
            micro_turn_deg = MICRO_TURN_DEG
        if micro_forward_duration is None:
            micro_forward_duration = MICRO_FORWARD_DURATION
        if micro_forward_speed is None:
            micro_forward_speed = MICRO_FORWARD_SPEED
        if turn_speed is None:
            turn_speed = TURN_SPEED

        target_angle_rad = math.radians(target_angle_deg)
        turn_vyaw = turn_speed * turn_direction
        direction_name = "左转" if turn_direction == 1 else "右转"

        # ---- 无 IMU 降级：纯时间估算 ----
        if self._robot_state is None:
            total_time = target_angle_rad / turn_speed
            steps = max(1, int(target_angle_deg / micro_turn_deg))
            step_angle = target_angle_deg / steps
            step_time = total_time / steps
            print(f"[微调] 无IMU，{direction_name}拆为 {steps} 步，每步 {step_angle:.1f}°")
            for i in range(steps):
                self.set_command(0.0, 0.0, turn_vyaw)
                time.sleep(step_time)
                self.set_command(0.0, 0.0, 0.0)
                time.sleep(0.1)
                self.set_command(micro_forward_speed, 0.0, 0.0)
                time.sleep(micro_forward_duration)
                self.set_command(0.0, 0.0, 0.0)
                time.sleep(0.1)
                print(f"[微调] 第 {i+1}/{steps} 步完成，累计约 {(i+1)*step_angle:.1f}°")
            print(f"[微调] {direction_name}{target_angle_deg}° 完成（时间估算模式）")
            return

        # ---- IMU 闭环模式 ----
        accumulated_rad = 0.0
        step_count = 0
        overall_start_yaw = self._get_yaw()

        print(f"[微调] {direction_name}{target_angle_deg}°，"
              f"每步转 {micro_turn_deg}° 后前进 {micro_forward_duration}s")

        while accumulated_rad < target_angle_rad - math.radians(0.5):
            remaining = target_angle_rad - accumulated_rad
            this_turn_rad = min(math.radians(micro_turn_deg), remaining)
            step_count += 1

            # ——— 第 1 段：转 this_turn_rad ———
            step_start_yaw = self._get_yaw()
            self.set_command(0.0, 0.0, turn_vyaw)
            turn_start = time.time()

            while self._running:
                if time.time() - turn_start > TURN_TIMEOUT:
                    print("[WARN] 微调转弯超时，强制停止")
                    break
                current_yaw = self._get_yaw()
                yaw_diff = abs(self._normalize_angle(current_yaw - step_start_yaw))
                if yaw_diff >= this_turn_rad:
                    break
                time.sleep(0.01)

            self.set_command(0.0, 0.0, 0.0)
            time.sleep(0.1)

            actual_step_rad = abs(self._normalize_angle(self._get_yaw() - step_start_yaw))
            accumulated_rad += actual_step_rad

            # ——— 第 2 段：前进一小段 ———
            self.set_command(micro_forward_speed, 0.0, 0.0)
            time.sleep(micro_forward_duration)
            self.set_command(0.0, 0.0, 0.0)
            time.sleep(0.1)

            print(f"[微调] 第 {step_count} 步：转 {math.degrees(actual_step_rad):.1f}°"
                  f" → 前进 {micro_forward_duration}s"
                  f" → 累计 {math.degrees(accumulated_rad):.1f}°")

        total_actual_deg = math.degrees(abs(
            self._normalize_angle(self._get_yaw() - overall_start_yaw)))
        print(f"[微调] {direction_name}完成，共 {step_count} 步，实际转过 {total_actual_deg:.1f}°")

    def run(self):
        """执行完整运动流程"""
        # 机器人初始化流程
        print("[INIT] 切换运动模式为 normal...")
        self._msc.SelectMode("normal")
        time.sleep(1.5)

        print("[INIT] 机器人站立...")
        self._sport.StandUp()
        time.sleep(2)

        print("[INIT] 关闭摇杆接管...")
        self._sport.SwitchJoystick(False)
        time.sleep(0.5)

        self._enable_classic_walk()

        # 启动控制线程
        ctrl_thread = threading.Thread(
            target=self._control_loop, daemon=True, name="motion_ctrl"
        )
        ctrl_thread.start()

        print("=" * 50)
        print("  开始执行预设运动序列")
        print("=" * 50)

        try:
            total_steps = len(ACTION_SEQUENCE)
            for idx, entry in enumerate(ACTION_SEQUENCE, 1):
                action = entry[0]
                print(f"\n===== 步骤 {idx}/{total_steps} =====")
                if action == "forward":
                    # forward: (action, duration)
                    duration = entry[1]
                    self.go_forward(duration)
                elif action == "move_right":
                    # move_right: (action, duration)
                    duration = entry[1]
                    self.move_right(duration)
                elif action in ("turn_left", "turn_right"):
                    # turn: (action, angle, [micro_turn_deg], [micro_forward_duration], [micro_forward_speed], [turn_speed])
                    angle = entry[1]
                    micro_turn_deg = entry[2] if len(entry) > 2 else None
                    micro_forward_duration = entry[3] if len(entry) > 3 else None
                    micro_forward_speed = entry[4] if len(entry) > 4 else None
                    turn_speed = entry[5] if len(entry) > 5 else None
                    if action == "turn_left":
                        self.turn_left(angle, micro_turn_deg, micro_forward_duration, micro_forward_speed, turn_speed)
                    else:
                        self.turn_right(angle, micro_turn_deg, micro_forward_duration, micro_forward_speed, turn_speed)
                else:
                    print(f"[WARN] 未知动作类型: {action}，跳过")

            print("\n[INFO] 全部动作执行完毕")

        except KeyboardInterrupt:
            print("\n[INFO] 用户手动中断")
        finally:
            # 安全停止流程
            print("\n[停止] 停止运动...")
            self._control_running = False
            self.set_command(0, 0, 0)
            time.sleep(0.2)
            self._sport.StopMove()
            time.sleep(0.3)
            print("[停止] 程序已安全退出（机器人保持站立）")

# ============================================================
# 程序入口
# ============================================================
def main():
    # 行缓冲，确保打印实时输出
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <networkInterface>")
        print(f"示例: {sys.argv[0]} eth0")
        sys.exit(-1)

    print("=" * 50)
    print("  Go2 定序运动控制（经典步态版）")
    print("=" * 50)

    controller = MotionController(network_interface=sys.argv[1])
    controller.run()

if __name__ == "__main__":
    main()
