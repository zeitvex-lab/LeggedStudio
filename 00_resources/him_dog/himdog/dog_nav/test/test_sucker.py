#!/usr/bin/env python3
# ========================================================================================
# test_sucker.py — 吸盘 + 气泵控制器【硬件版】交互测试
# ========================================================================================
#
# test_sucker.cpp 的 Python 版（逻辑 1:1 对应 sucker_controller.hpp）：
# 直接实例化真实 SuckerController，SendCmd 走 pyserial → 真实写串口到 STM32。
# 时序用 time.monotonic() 墙钟（与 navigation_dog 实物一致）。
#
# 串口协议（发往 STM32，与 resource/test_serial.py 一致）:
#   格式: "{angle_left},{angle_right},{pump}\n"   (ASCII)
#     angle_left / angle_right: 舵机角度 0~270  (0=动作位, 270=存储位)
#     pump: 1 = 泵 ON（吸取）, 0 = 泵 OFF（释放）
#   左舵机安装方向相反，发送前做镜像: send = 270 - logic
#
# 运行（参数全可省，默认与 navigation_dog 一致 /dev/ttyUSB0 @115200 move=3.0 hold=0.5）:
#   python3 test/test_sucker.py [port] [baudrate] [move_sec] [hold_sec]
#   例: python3 test/test_sucker.py /dev/ttyUSB0 115200 3.0 0.5
#
# 安全:
#   - 启动前打印参数 + 必须 y 确认（避免误跑驱动舵机/泵）
#   - 开头和退出各跑一次 Home()（归位到存储位 270,270 + 泵 OFF）
#   - Ctrl+C (SIGINT) → KeyboardInterrupt 捕获 → 自动 Home + Close
#   - 串口打开失败提示 sudo chmod 666 / ls /dev/ttyUSB*
#
# 菜单（输入首字符）:
#   h  归位 (270,270,0)
#   1  取箱 left    2  取箱 right
#   3  放箱 left    4  放箱 right
#   q  退出
#
import sys
import time

import serial


# ========================================================================================
# SuckerController — 吸盘 + 气泵控制器（重写自 sucker_controller.hpp）
# ========================================================================================
class SuckerController:
    """吸盘舵机 + 气泵串口控制器，动作时序基于时间推进的状态机"""

    def __init__(self, move_sec=3.0, hold_sec=0.5):
        self.ser = None
        self.port = None
        self.move_sec = move_sec    # 舵机 0↔270 满程转动时间
        self.hold_sec = hold_sec    # 下到位后保持时间（建真空 / 释放）

        # 状态机
        self.mode = "idle"          # idle / pick / place
        self.phase = 0
        self.active = False
        self.direction = ""
        self.down_left = 270        # 下到动作位的左舵机逻辑角度
        self.down_right = 270
        self.phase_start = 0.0

    # --------------------------------------------------------------------------------------
    # 串口
    # --------------------------------------------------------------------------------------
    def open(self, port, baudrate=115200):
        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
        except FileNotFoundError:
            print(f"[Sucker] ★ 无法打开吸盘串口 {port}: 找不到设备")
            return False
        except PermissionError:
            print(f"[Sucker] ★ 无法打开吸盘串口 {port}: 权限不足")
            return False
        except Exception as e:
            print(f"[Sucker] ★ 无法打开吸盘串口 {port}: {e}")
            return False
        self.port = port
        print(f"[Sucker] ★ 吸盘串口已打开: {port} @ {baudrate} bps")
        return True

    def close(self):
        if self.ser is not None:
            self.ser.close()
            self.ser = None

    def is_open(self):
        return self.ser is not None

    # --------------------------------------------------------------------------------------
    # 时间参数
    # --------------------------------------------------------------------------------------
    def set_move_sec(self, s):
        self.move_sec = s

    def set_hold_sec(self, s):
        self.hold_sec = s

    # --------------------------------------------------------------------------------------
    # Home — 归位到存储位（舵机 270,270，泵 OFF）
    # --------------------------------------------------------------------------------------
    def home(self):
        self.mode = "idle"
        self.phase = 0
        self.active = False
        self._send_cmd(270, 270, 0)
        print("[Sucker] ★ 归位到存储位 (270,270) 泵 OFF")

    # --------------------------------------------------------------------------------------
    # StartPick — 启动取箱动作
    # --------------------------------------------------------------------------------------
    def start_pick(self, direction, now):
        self._setup_down_angles(direction)
        self.mode = "pick"
        self.phase = 0
        self.phase_start = now
        self.active = True
        # phase 0: 下到箱位 + 泵 ON
        self._send_cmd(self.down_left, self.down_right, 1)
        print(f"[Sucker] ★ 取箱[{direction}]: 下到箱位 (左{self.down_left} 右{self.down_right}) "
              f"泵 ON — 等 {self.move_sec:.1f}s")

    # --------------------------------------------------------------------------------------
    # StartPlace — 启动放箱动作（进入时箱应已吸在存储位，泵 ON）
    # --------------------------------------------------------------------------------------
    def start_place(self, direction, now):
        self._setup_down_angles(direction)
        self.mode = "place"
        self.phase = 0
        self.phase_start = now
        self.active = True
        # phase 0: 下到放位 + 泵 ON（箱仍吸着）
        self._send_cmd(self.down_left, self.down_right, 1)
        print(f"[Sucker] ★ 放箱[{direction}]: 下到放位 (左{self.down_left} 右{self.down_right}) "
              f"泵 ON — 等 {self.move_sec:.1f}s")

    # --------------------------------------------------------------------------------------
    # Update — 每帧推进，返回 True 表示动作刚完成
    # --------------------------------------------------------------------------------------
    def update(self, now):
        if not self.active:
            return False
        elapsed = now - self.phase_start
        if elapsed < self._phase_duration():
            return False

        # 本 phase 完成，推进
        print(f"[Sucker]   phase{self.phase} 完成 (用时 {elapsed:.2f}s)")
        self.phase += 1
        self.phase_start = now

        if self.mode == "pick":
            # phase: 0(下) → 1(建真空) → 2(抬) → done
            if self.phase == 1:
                self._send_cmd(self.down_left, self.down_right, 1)   # 保持泵 ON 建立真空
                print(f"[Sucker] ★ 取箱: 建立真空 泵 ON — 等 {self.hold_sec:.1f}s")
            elif self.phase == 2:
                self._send_cmd(270, 270, 1)                          # 抬回存储，泵保持 ON（箱吸着）
                print(f"[Sucker] ★ 取箱: 抬回存储 (270,270) 泵 ON — 等 {self.move_sec:.1f}s")
            else:
                self.active = False
                print(f"[Sucker] ★ 取箱[{self.direction}] 完成（箱在存储位，泵保持 ON）")
                return True
        else:  # place
            # phase: 0(下) → 1(释放) → 2(抬) → done
            if self.phase == 1:
                self._send_cmd(self.down_left, self.down_right, 0)   # 泵 OFF 释放
                print(f"[Sucker] ★ 放箱: 泵 OFF 释放 — 等 {self.hold_sec:.1f}s")
            elif self.phase == 2:
                self._send_cmd(270, 270, 0)                          # 抬回存储，泵 OFF
                print(f"[Sucker] ★ 放箱: 抬回存储 (270,270) 泵 OFF — 等 {self.move_sec:.1f}s")
            else:
                self.active = False
                print(f"[Sucker] ★ 放箱[{self.direction}] 完成（已释放，泵 OFF）")
                return True
        return False

    # --------------------------------------------------------------------------------------
    # 状态查询
    # --------------------------------------------------------------------------------------
    def is_active(self):
        return self.active

    def is_pick_mode(self):
        return self.mode == "pick"

    def is_place_mode(self):
        return self.mode == "place"

    # 当前是否正在吸着箱子（取箱后到放箱释放前都为 True）
    def is_holding(self):
        if self.mode == "pick":
            return True               # 取箱全程吸着
        if self.mode == "place":
            return self.phase < 1     # 放箱到 phase 1(释放) 前都吸着
        return False

    # --------------------------------------------------------------------------------------
    # 内部
    # --------------------------------------------------------------------------------------
    def _setup_down_angles(self, direction):
        self.direction = direction
        if direction == "left":
            self.down_left, self.down_right = 0, 270    # 左舵机下，右舵机保持存储
        else:
            self.down_left, self.down_right = 270, 0    # 右舵机下，左舵机保持存储

    def _phase_duration(self):
        # phase 1 用 hold_sec，其余用 move_sec
        return self.hold_sec if self.phase == 1 else self.move_sec

    def _send_cmd(self, angle_left_logic, angle_right_logic, pump_on):
        angle_left_logic = max(0, min(270, angle_left_logic))
        angle_right_logic = max(0, min(270, angle_right_logic))
        angle_left_send = 270 - angle_left_logic        # 左舵机镜像

        buf = f"{angle_left_send},{angle_right_logic},{pump_on}\n"
        if self.ser is None:
            print(f"[Sucker] ★ [串口未开] 发送(逻辑): 左{angle_left_logic} 右{angle_right_logic} 泵{pump_on}")
            return
        try:
            self.ser.write(buf.encode("ascii"))
        except Exception as e:
            print(f"[Sucker] ★ 吸盘串口写入失败: {e}")


# ========================================================================================
# 主程序
# ========================================================================================
def now_sec(t0):
    """从 t0 起算的墙钟秒数"""
    return time.monotonic() - t0


def run_action(sc, t0):
    """用 50Hz 墙钟把一个动作跑完（和 navigation_dog 的 timer 节拍一致），返回真实耗时"""
    start = now_sec(t0)
    interrupted = False
    while sc.is_active():
        try:
            sc.update(now_sec(t0))
        except KeyboardInterrupt:
            interrupted = True
            break
        time.sleep(0.02)   # 50Hz
    return now_sec(t0) - start, interrupted


def main():
    # ---- 参数（全部可省，默认与 navigation_dog 一致）----
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
    move_sec = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
    hold_sec = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5

    # ---- 打印参数 ----
    print("============================================================")
    print("  ★ 吸盘 + 气泵控制器 — 硬件版交互测试")
    print("============================================================")
    print(f"  串口    : {port} @ {baudrate} bps")
    print(f"  move_sec: {move_sec:.2f}s  hold_sec: {hold_sec:.2f}s")
    print("============================================================")

    # ---- 打开串口（真实硬件）----
    sc = SuckerController(move_sec, hold_sec)
    if not sc.open(port, baudrate):
        print(f"\n★ 串口打开失败: {port}")
        print("  1) 检查设备是否存在: ls /dev/ttyUSB*")
        print(f"  2) 给权限:           sudo chmod 666 {port}")
        return 1

    # ---- ⚠️ 安全确认 ----
    print(f"\n⚠️  即将驱动真实舵机和气泵（STM32 @ {port}）")
    print("    确认吸盘机构无阻挡、泵气路正常后输入 y 继续，其它键退出: ", end="")
    try:
        line = input()
    except EOFError:
        print("已取消，退出。")
        sc.close()
        return 0
    if not line or (line[0] != "y" and line[0] != "Y"):
        print("已取消，退出。")
        sc.close()
        return 0

    # ---- 进入安全初始态 ----
    print("\n[初始化] ", end="")
    sc.home()   # 归位到存储位 (270,270) 泵 OFF

    # ---- 交互菜单 ----
    quit_flag = False
    while not quit_flag:
        print("\n----- 菜单 -----")
        print("  h  归位 (270,270,0)")
        print("  1  取箱 left    2  取箱 right")
        print("  3  放箱 left    4  放箱 right")
        print("  q  退出")
        print("> ", end="")

        try:
            line = input()
        except EOFError:
            # stdin 关闭（Ctrl+D），按退出处理
            break
        if not line:
            continue

        t0 = time.monotonic()   # 每个动作重置零点
        cmd = line[0]

        if cmd in ("h", "H"):
            sc.home()
            print("  -> 已归位 (270,270,0)")
        elif cmd == "1":
            print("\n[取箱 left] 启动...")
            sc.start_pick("left", now_sec(t0))
            dt, intr = run_action(sc, t0)
            print(f"  -> 取箱 left {'被中断' if intr else '完成'}，真实耗时 {dt:.2f}s")
        elif cmd == "2":
            print("\n[取箱 right] 启动...")
            sc.start_pick("right", now_sec(t0))
            dt, intr = run_action(sc, t0)
            print(f"  -> 取箱 right {'被中断' if intr else '完成'}，真实耗时 {dt:.2f}s")
        elif cmd == "3":
            print("\n[放箱 left] 启动...")
            sc.start_place("left", now_sec(t0))
            dt, intr = run_action(sc, t0)
            print(f"  -> 放箱 left {'被中断' if intr else '完成'}，真实耗时 {dt:.2f}s")
        elif cmd == "4":
            print("\n[放箱 right] 启动...")
            sc.start_place("right", now_sec(t0))
            dt, intr = run_action(sc, t0)
            print(f"  -> 放箱 right {'被中断' if intr else '完成'}，真实耗时 {dt:.2f}s")
        elif cmd in ("q", "Q"):
            quit_flag = True
        else:
            print(f"  未知命令 '{cmd}'")

    # ---- 退出路径：归位 + 关泵 + 关串口 ----
    print("\n[SIGINT] 安全退出..." if not quit_flag else "")
    print("\n[退出] ", end="")
    sc.home()   # 归位 + 泵 OFF
    sc.close()
    print("  -> 串口已关闭，再见。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # 兜底：动作进行中 Ctrl+C 已被 run_action 捕获，这里兜菜单等待时
        print("\n[SIGINT] 收到中断信号，退出。")
        sys.exit(0)
