#!/usr/bin/env python3
# ========================================================================================
# test_pick_place.py — 蹲下+吸盘+气泵 全链路 ROS 交互测试（rclpy 节点）
# ========================================================================================
#
# test_pick_place.cpp 的 Python 版。一条取/放命令同时驱动两条链路，时序由 actor 收口：
#
#   - 狗腿链路: 每帧把 actor 返回的 Frame 发到 /joint_states（12 维关节角）
#               + /policy_mode（true 挂起 RL policy / false 恢复）
#   - 吸盘链路: actor 内部 SuckerController → pyserial → STM32（舵机角度 + 气泵 ON/OFF）
#
# actor 内部自动编排「挂起 RL → 蹲下插值 → 保持期转舵机+开泵 → 站起插值 → 恢复 RL」，
# 宿主只需 start_pickup/start_place + 每帧 tick + apply_frame，与 navigation_dog 一致。
#
# 运行（吸盘串口参数走命令行，蹲下/站姿参数走 --ros-args -p）:
#   ros2 run dog_nav test_pick_place [port] [baudrate]
#   例: ros2 run dog_nav test_pick_place /dev/ttyUSB0 115200
#
#   蹲下参数覆盖:
#     ros2 run dog_nav test_pick_place /dev/ttyUSB0 --ros-args -p squat_hold_sec:=6.0
#
#   ⚠ squat_hold_sec 须 ≥ 吸盘全程(2*move+hold)，否则蹲下先结束会卡住。
#      默认 squat_hold_sec=8.0 已对齐默认吸盘全程(2*3.0+0.5)，改 move 时记得同步调。
#
# 联动: 跑本节点前应先跑 dog_policy_test_13 —— 它订阅 /policy_mode，收到 true 后停发
#       /joint_states 交出控制权，本节点成为 /joint_states 唯一发布者。
#
# 安全:
#   - 启动前打印参数 + 必须 y 确认（即将驱动真实狗腿 + 舵机 + 泵）
#   - 启动时归位吸盘到存储位（270,270）泵 OFF
#   - Ctrl+C → spin 退出 → 归位吸盘 + 关串口
#
# 菜单（输入首字符，动作进行中会忽略新命令并提示）:
#   h  归位吸盘    1  取箱 left    2  取箱 right
#   3  放箱 left   4  放箱 right   q  退出
#
import threading
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool

# 复用 test_sucker.py 里的 SuckerController（重写自 sucker_controller.hpp）
# 这里就地再声明一份，保持本文件独立可运行（不依赖 test 目录成为 Python 包）
import serial


# ========================================================================================
# SuckerController — 吸盘 + 气泵控制器（与 test_sucker.py / sucker_controller.hpp 一致）
# ========================================================================================
class SuckerController:
    def __init__(self, move_sec=3.0, hold_sec=0.5):
        self.ser = None
        self.move_sec = move_sec
        self.hold_sec = hold_sec
        self.mode = "idle"
        self.phase = 0
        self.active = False
        self.direction = ""
        self.down_left = 270
        self.down_right = 270
        self.phase_start = 0.0

    def open(self, port, baudrate=115200):
        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
        except Exception as e:
            print(f"[Sucker] ★ 无法打开吸盘串口 {port}: {e}")
            return False
        print(f"[Sucker] ★ 吸盘串口已打开: {port} @ {baudrate} bps")
        return True

    def close(self):
        if self.ser is not None:
            self.ser.close()
            self.ser = None

    def set_move_sec(self, s):
        self.move_sec = s

    def set_hold_sec(self, s):
        self.hold_sec = s

    def home(self):
        self.mode = "idle"
        self.phase = 0
        self.active = False
        self._send_cmd(270, 270, 0)
        print("[Sucker] ★ 归位到存储位 (270,270) 泵 OFF")

    def start_pick(self, direction, now):
        self._setup_down_angles(direction)
        self.mode = "pick"
        self.phase = 0
        self.phase_start = now
        self.active = True
        self._send_cmd(self.down_left, self.down_right, 1)

    def start_place(self, direction, now):
        self._setup_down_angles(direction)
        self.mode = "place"
        self.phase = 0
        self.phase_start = now
        self.active = True
        self._send_cmd(self.down_left, self.down_right, 1)

    def update(self, now):
        if not self.active:
            return False
        elapsed = now - self.phase_start
        if elapsed < self._phase_duration():
            return False
        self.phase += 1
        self.phase_start = now
        if self.mode == "pick":
            if self.phase == 1:
                self._send_cmd(self.down_left, self.down_right, 1)
            elif self.phase == 2:
                self._send_cmd(270, 270, 1)
            else:
                self.active = False
                return True
        else:  # place
            if self.phase == 1:
                self._send_cmd(self.down_left, self.down_right, 0)
            elif self.phase == 2:
                self._send_cmd(270, 270, 0)
            else:
                self.active = False
                return True
        return False

    def is_active(self):
        return self.active

    def _setup_down_angles(self, direction):
        self.direction = direction
        if direction == "left":
            self.down_left, self.down_right = 0, 270
        else:
            self.down_left, self.down_right = 270, 0

    def _phase_duration(self):
        return self.hold_sec if self.phase == 1 else self.move_sec

    def _send_cmd(self, angle_left_logic, angle_right_logic, pump_on):
        angle_left_logic = max(0, min(270, angle_left_logic))
        angle_right_logic = max(0, min(270, angle_right_logic))
        angle_left_send = 270 - angle_left_logic   # 左舵机镜像
        buf = f"{angle_left_send},{angle_right_logic},{pump_on}\n"
        if self.ser is None:
            return
        try:
            self.ser.write(buf.encode("ascii"))
        except Exception as e:
            print(f"[Sucker] ★ 吸盘串口写入失败: {e}")


# ========================================================================================
# SquatController — 蹲下/起立姿态控制器（重写自 squat_controller.hpp）
# ========================================================================================
class SquatController:
    K_NUM_DOFS = 12

    def __init__(self, stand_pose=None, squat_pose=None, interp_sec=1.0, hold_sec=1.0):
        self.stand_pose = stand_pose or [0.0] * self.K_NUM_DOFS
        self.squat_pose = squat_pose or [0.0] * self.K_NUM_DOFS
        self.interp_sec = max(0.01, interp_sec)
        self.hold_sec = max(0.0, hold_sec)
        self.active = False
        self.phase = 0      # 0=站→蹲, 1=保持, 2=蹲→站, 3=完成
        self.phase_start = 0.0

    def set_stand_pose(self, p):
        self.stand_pose = list(p)

    def set_squat_pose(self, p):
        self.squat_pose = list(p)

    def set_interp_sec(self, s):
        self.interp_sec = max(0.01, s)

    def set_hold_sec(self, s):
        self.hold_sec = max(0.0, s)

    def start_squat(self, now):
        """启动蹲下动作，返回首帧（policy_mode=True + 初始站立姿态）"""
        self.active = True
        self.phase = 0
        self.phase_start = now
        return {"has_pose": True, "pose": list(self.stand_pose), "policy_mode": True}

    def update(self, now):
        """每帧推进，返回本帧该发什么（姿态 + 可能的 policy_mode 切换）"""
        if not self.active:
            return {"has_pose": False, "pose": [0.0] * self.K_NUM_DOFS, "policy_mode": None}
        elapsed = now - self.phase_start

        if self.phase == 0:
            # 站→蹲插值
            t = max(0.0, min(1.0, elapsed / self.interp_sec))
            pose = self._interp(self.stand_pose, self.squat_pose, t)
            frame = {"has_pose": True, "pose": pose, "policy_mode": None}
            if elapsed >= self.interp_sec:
                self.phase = 1
                self.phase_start = now
            return frame
        elif self.phase == 1:
            # 保持蹲下姿态
            frame = {"has_pose": True, "pose": list(self.squat_pose), "policy_mode": None}
            if elapsed >= self.hold_sec:
                self.phase = 2
                self.phase_start = now
            return frame
        else:  # phase == 2
            # 蹲→站插值
            t = max(0.0, min(1.0, elapsed / self.interp_sec))
            pose = self._interp(self.squat_pose, self.stand_pose, t)
            frame = {"has_pose": True, "pose": pose, "policy_mode": None}
            if elapsed >= self.interp_sec:
                self.phase = 3
                self.phase_start = now
                frame["policy_mode"] = False        # 恢复 policy
                frame["pose"] = list(self.stand_pose)  # 最后一帧站立兜底
                self.active = False
            return frame

    def is_active(self):
        return self.active

    def is_in_hold_phase(self):
        return self.active and self.phase == 1

    @staticmethod
    def _interp(a, b, t):
        return [a[i] + (b[i] - a[i]) * t for i in range(len(a))]


# ========================================================================================
# PickPlaceActor — 蹲下+吸盘 单次取/放动作编排器（重写自 pick_place_actor.hpp）
# ========================================================================================
class PickPlaceActor:
    def __init__(self):
        self.squat = SquatController()
        self.sucker = SuckerController()
        self._mode = "idle"                 # idle / pick / place
        self._pickup_executed = False
        self._pickup_suck_started = False
        self._place_executed = False
        self._place_suck_started = False
        self._sucker_direction = None
        self.direction = ""

    # ---- 配置（透传给内部 squat / sucker）----
    def configure_squat(self, stand, squat, interp_sec, hold_sec):
        self.squat.set_stand_pose(stand)
        self.squat.set_squat_pose(squat)
        self.squat.set_interp_sec(interp_sec)
        self.squat.set_hold_sec(hold_sec)

    def configure_sucker(self, move_sec, hold_sec):
        self.sucker.set_move_sec(move_sec)
        self.sucker.set_hold_sec(hold_sec)

    def open_sucker(self, port, baudrate):
        return self.sucker.open(port, baudrate)

    def home_sucker(self):
        self.sucker.home()

    # ---- StartPickup / StartPlace：返回首帧 ----
    def start_pickup(self, direction, now):
        self._mode = "pick"
        self._pickup_executed = True
        self._pickup_suck_started = False
        self._sucker_direction = direction
        self.direction = direction
        return self.squat.start_squat(now)

    def start_place(self, direction, now):
        self._mode = "place"
        self._place_executed = True
        self._place_suck_started = False
        self._sucker_direction = direction
        self.direction = direction
        return self.squat.start_squat(now)

    # ---- Tick：每帧推进（首帧除外），返回 (frame, action_done) ----
    def tick(self, now):
        empty = {"has_pose": False, "pose": [0.0] * SquatController.K_NUM_DOFS, "policy_mode": None}
        if self._mode == "idle":
            return empty, False

        pick = self._mode == "pick"
        executed = self._pickup_executed if pick else self._place_executed
        suck_started = self._pickup_suck_started if pick else self._place_suck_started

        # 1) 完成判定
        if (not self.squat.is_active()) and executed and suck_started and (not self.sucker.is_active()):
            self._reset()
            return empty, True

        # 2) 蹲下进行中
        if self.squat.is_active():
            frame = self.squat.update(now)
            # 进入保持期且吸盘未启动 → 触发吸盘动作
            if self.squat.is_in_hold_phase() and not suck_started and self._sucker_direction is not None:
                if pick:
                    self.sucker.start_pick(self._sucker_direction, now)
                    self._pickup_suck_started = True
                else:
                    self.sucker.start_place(self._sucker_direction, now)
                    self._place_suck_started = True
            # 吸盘进行中 → 同步推进
            if self.sucker.is_active():
                self.sucker.update(now)
            return frame, False

        # 3) 其它（蹲下已结束但吸盘未完成，或异常配置）→ 空 frame
        return empty, False

    # ---- 状态查询 ----
    def is_idle(self):
        return self._mode == "idle"

    def is_running(self):
        return self._mode != "idle"

    def _reset(self):
        self._mode = "idle"
        self._pickup_executed = False
        self._pickup_suck_started = False
        self._place_executed = False
        self._place_suck_started = False
        self._sucker_direction = None
        self.direction = ""


# ========================================================================================
# PickPlaceTestNode — ROS2 节点
# ========================================================================================
class PickPlaceTestNode(Node):
    # 12 关节名（与 navigation_dog / dog_policy_test_13 一致）
    JOINT_NAMES = [
        "FL_hip", "FL_thigh", "FL_calf",
        "FR_hip", "FR_thigh", "FR_calf",
        "RL_hip", "RL_thigh", "RL_calf",
        "RR_hip", "RR_thigh", "RR_calf",
    ]

    def __init__(self, port, baudrate):
        super().__init__("test_pick_place")
        self._t0 = time.monotonic()

        # ---- 声明参数（默认与 navigation_dog 一致）----
        self.declare_parameter("stand_pose", [0.0] * SquatController.K_NUM_DOFS)
        self.declare_parameter("squat_pose", [0.0, 0.7, -1.4, 0.0, 0.7, -1.4,
                                              0.0, 0.7, -1.4, 0.0, 0.7, -1.4])
        self.declare_parameter("squat_interp_sec", 1.0)
        # 默认给足保持时间，确保 ≥ 吸盘全程(2*3.0+0.5)，避免蹲下先结束卡住
        self.declare_parameter("squat_hold_sec", 8.0)
        self.declare_parameter("sucker_move_sec", 3.0)
        self.declare_parameter("sucker_hold_sec", 0.5)

        # ---- 读取参数（rclpy 的 .value 直接返回原生 Python 类型）----
        stand = list(self.get_parameter("stand_pose").value)
        squat = list(self.get_parameter("squat_pose").value)
        interp_sec = float(self.get_parameter("squat_interp_sec").value)
        squat_hold_sec = float(self.get_parameter("squat_hold_sec").value)
        move_sec = float(self.get_parameter("sucker_move_sec").value)
        sucker_hold_sec = float(self.get_parameter("sucker_hold_sec").value)

        # ---- 配置 actor ----
        actor = PickPlaceActor()
        actor.configure_squat(stand, squat, interp_sec, squat_hold_sec)
        actor.configure_sucker(move_sec, sucker_hold_sec)

        if not actor.open_sucker(port, baudrate):
            self.get_logger().warn(
                f"★ 吸盘串口 {port} 打开失败，吸盘链路不可用（蹲下 / policy_mode 仍会发）")
        self.actor = actor

        # ---- 发布器（与 navigation_dog 同名同类型）----
        # ★ 蹲下取箱：挂起 RL 时 nav 成为 /joint_states 唯一发布者
        self.joint_state_pub = self.create_publisher(JointState, "/joint_states", 10)
        # ★ /policy_mode: true=挂起 policy 发布（交出控制权），false=恢复
        self.policy_mode_pub = self.create_publisher(Bool, "/policy_mode", 10)

        # ---- 200Hz timer（与 dog_policy_test_13 的 /joint_states 频率对齐）----
        self._pending = None   # 待执行动作（输入线程写，timer 线程读并清空）
        self.create_timer(0.005, self._on_timer)   # 5ms = 200Hz

        self.get_logger().info("★ test_pick_place 就绪（蹲下+吸盘全链路）")
        self.get_logger().info(
            f"  蹲下: interp={interp_sec:.2f}s hold={squat_hold_sec:.2f}s  "
            f"吸盘: move={move_sec:.2f}s hold={sucker_hold_sec:.2f}s")

    def init_home(self):
        self.actor.home_sucker()

    def shutdown_home(self):
        self.actor.home_sucker()

    # --------------------------------------------------------------------------------------
    # 输入线程入口：读 stdin → 翻 _pending / 触发退出
    # --------------------------------------------------------------------------------------
    def input_loop(self):
        while True:
            try:
                line = input()
            except EOFError:
                break
            if not line:
                continue
            c = line[0]
            if c in ("h", "H"):
                self._pending = "home"
            elif c == "1":
                self._pending = "pick_left"
            elif c == "2":
                self._pending = "pick_right"
            elif c == "3":
                self._pending = "place_left"
            elif c == "4":
                self._pending = "place_right"
            elif c in ("q", "Q"):
                self.get_logger().info("收到退出命令，关闭节点...")
                rclpy.shutdown()
                return

    # --------------------------------------------------------------------------------------
    # 200Hz timer：处理待执行动作 + 推进 actor
    # --------------------------------------------------------------------------------------
    def _on_timer(self):
        now_sec = time.monotonic() - self._t0
        act = self._pending
        self._pending = None

        if act == "home":
            if not self.actor.is_running():
                self.actor.home_sucker()
            else:
                self.get_logger().warn("动作进行中，归位已忽略")
            return

        if act is not None:
            # 新动作命令
            if self.actor.is_running():
                self.get_logger().warn("动作进行中，新命令已忽略")
                return
            if act == "pick_left":
                self.get_logger().info("★ [取箱 left] 启动...")
                self._apply(self.actor.start_pickup("left", now_sec))
            elif act == "pick_right":
                self.get_logger().info("★ [取箱 right] 启动...")
                self._apply(self.actor.start_pickup("right", now_sec))
            elif act == "place_left":
                self.get_logger().info("★ [放箱 left] 启动...")
                self._apply(self.actor.start_place("left", now_sec))
            elif act == "place_right":
                self.get_logger().info("★ [放箱 right] 启动...")
                self._apply(self.actor.start_place("right", now_sec))
            return   # 首帧不 tick（否则蹲下插值少推进一帧）

        # 推进进行中的动作
        if self.actor.is_running():
            frame, done = self.actor.tick(now_sec)
            self._apply(frame)
            if done:
                self.get_logger().info("★ 动作全部完成（蹲下 + 吸盘）")

    # --------------------------------------------------------------------------------------
    # apply — 把 actor 返回的 frame 落到 ROS 发布器（搬自 navigation_dog 的 ApplyActorFrame）
    # --------------------------------------------------------------------------------------
    def _apply(self, frame):
        if frame.get("policy_mode") is not None:
            self._publish_policy_mode(frame["policy_mode"])
        if frame.get("has_pose"):
            self._publish_joint_pose(frame["pose"])

    def _publish_joint_pose(self, pose):
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()
        js.header.frame_id = "base_link"
        js.name = list(self.JOINT_NAMES)
        js.position = [float(v) for v in pose]
        self.joint_state_pub.publish(js)

    def _publish_policy_mode(self, hold):
        msg = Bool()
        msg.data = bool(hold)
        self.policy_mode_pub.publish(msg)
        self.get_logger().info(f"★ /policy_mode = {'true(挂起)' if hold else 'false(恢复)'}")


# ========================================================================================
# 主程序
# ========================================================================================
def main():
    import sys
    # ---- 吸盘串口参数（全部可省，默认与 navigation_dog 一致）----
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    # ---- 打印参数 + 安全确认（驱动真实狗腿 + 舵机 + 泵，必须 y）----
    print("============================================================")
    print("  ★ 蹲下+吸盘+气泵 全链路 ROS 交互测试")
    print("============================================================")
    print(f"  吸盘串口: {port} @ {baudrate} bps")
    print("  蹲下/站姿参数经 --ros-args -p 覆盖（默认见启动日志）")
    print("============================================================")
    print("\n⚠️  即将驱动真实狗腿关节 + 舵机 + 气泵:")
    print("    - /policy_mode 会挂起 RL policy（确保 dog_policy_test_13 在运行以联动）")
    print("    - /joint_states 由本节点独占发布")
    print(f"    - 吸盘舵机/泵经 {port} 写 STM32")
    print("  确认机构无阻挡、气路正常后输入 y 继续，其它键退出: ", end="")

    try:
        line = input()
    except EOFError:
        print("已取消，退出。")
        return 0
    if not line or (line[0] != "y" and line[0] != "Y"):
        print("已取消，退出。")
        return 0

    # ---- 初始化 ROS ----
    rclpy.init()
    node = PickPlaceTestNode(port, baudrate)
    node.init_home()   # 启动安全初始态：归位吸盘

    # ---- 输入线程（读菜单）----
    threading.Thread(target=node.input_loop, daemon=True).start()

    # ---- 打印菜单 ----
    print("\n----- 菜单 -----")
    print("  h  归位吸盘    1  取箱 left    2  取箱 right")
    print("  3  放箱 left   4  放箱 right   q  退出")

    # ---- spin（Ctrl+C 会使其返回）----
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass

    # ---- 安全退出：归位吸盘 + 关串口 ----
    print("\n[退出] ", end="")
    node.shutdown_home()
    node.destroy_node()
    rclpy.shutdown()
    print("  -> 已归位吸盘，再见。")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
