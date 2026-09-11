#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监听 Xbox 手柄，每次按下 A 键 → 先杀掉旧的 real_motor_controller / dog_policy_test_12
进程 → 在新终端窗口启动 real_motor_controller → 等 5 秒 → 在另一个新终端窗口启动
dog_policy_test_12。

★ 用途：狗子倾倒保护后，按 A 一键重启恢复。
★ 可重复触发：每次倾倒按 A 都会重新走一遍流程。

用法（在 himdog 目录下）:
    source install/setup.bash
    python3 src/dog_policy_test/scripts/launch_policy_on_a.py

可选参数:
    python3 launch_policy_on_a.py [js设备] [延迟秒] [按键索引]

    js设备   默认自动探测 /dev/input/js*（一般 js0）
    延迟秒   默认 5（两条命令之间的间隔）
    按键索引 默认 0（A 键）

注意:
  - 恢复期间（杀进程 + 倒数 + 启动）会忽略新的 A 键，走完才能再次触发。
  - A 键同时被 xbox_input_node / dog_policy_test_12 使用，这里独立读手柄，
    只用来触发重启，互不影响。
"""

import glob
import os
import struct
import subprocess
import sys
import time

# ==================== 可直接改的配置 ====================
BUTTON_INDEX = 0          # 0 = A 键
DELAY_SEC = 5             # real_motor_controller 起来后，等几秒再起 dog_policy_test_12

# 两条命令（各自在一个新的 gnome-terminal 窗口里执行）
CMD_MOTOR = (
    "cd ~/himdog && "
    "source install/setup.bash && "
    "ros2 run dog_control real_motor_controller"
)
CMD_POLICY = (
    "cd ~/himdog && "
    "source install/setup.bash && "
    "ros2 run dog_policy_test dog_policy_test_12 --ros-args "
    "--params-file ./src/dog_policy_test/config/policy_params_12.yaml"
)

# 恢复时要先杀掉的旧进程（按命令行匹配，避免重复节点抢电机/话题）
KILL_NAMES = ["real_motor_controller", "dog_policy_test_12"]
# =======================================================

# Linux joystick 事件: time(u32) value(i16) type(u8) number(u8)
JS_EVENT_FMT = "<IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FMT)   # 8
JS_EVENT_BUTTON = 0x01


def find_js_device(hint=None):
    if hint and os.path.exists(hint):
        return hint
    devs = sorted(glob.glob("/dev/input/js*"))
    if not devs:
        sys.exit("找不到手柄设备 /dev/input/js* —— 插好手柄后重试，"
                 "或把设备路径作为第一个参数传入，例如 python3 launch_policy_on_a.py /dev/input/js0")
    return devs[0]


def kill_old_processes():
    """杀掉旧的 real_motor_controller / dog_policy_test_12，避免重复节点。"""
    for name in KILL_NAMES:
        subprocess.run(
            ["pkill", "-f", name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    time.sleep(1.0)   # 给旧进程时间退出、释放串口/话题


def spawn_terminal(title, cmd):
    """新开一个 gnome-terminal 窗口执行 cmd；命令退出后 exec bash 让窗口留着看输出。"""
    wrapped = 'echo "=== %s ==="; %s; echo "(已退出)"; exec bash' % (title, cmd)
    try:
        subprocess.Popen([
            "gnome-terminal",
            "--title=%s" % title,
            "--", "bash", "-c", wrapped,
        ])
        print("  [新窗口] %s" % title)
    except FileNotFoundError:
        print("  没找到 gnome-terminal，当前终端直接运行：%s" % cmd)
        os.system(cmd)


def do_recovery(delay):
    """完整恢复流程：杀旧 → 起电机 → 等 delay 秒 → 起策略。"""
    print("\n>>> [恢复] 杀掉旧进程 ...")
    sys.stdout.flush()
    kill_old_processes()

    print(">>> [恢复] 启动 real_motor_controller")
    sys.stdout.flush()
    spawn_terminal("real_motor_controller", CMD_MOTOR)

    print(">>> [恢复] 等待 %d 秒 ..." % delay)
    sys.stdout.flush()
    for i in range(int(delay), 0, -1):
        print("    %d..." % i)
        sys.stdout.flush()
        time.sleep(1)

    print(">>> [恢复] 启动 dog_policy_test_12")
    sys.stdout.flush()
    spawn_terminal("dog_policy_test_12", CMD_POLICY)

    print(">>> [恢复] 完成，等待下一次 A 键 ...\n")
    sys.stdout.flush()


def main():
    device = find_js_device(sys.argv[1] if len(sys.argv) > 1 else None)
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else DELAY_SEC
    btn = int(sys.argv[3]) if len(sys.argv) > 3 else BUTTON_INDEX

    print("手柄设备: %s" % device)
    print("等待按下 A 键(button %d)触发恢复 ……（可重复触发，Ctrl+C 退出）" % btn)
    print("流程: 杀旧进程 → real_motor_controller → 等 %.0f 秒 → dog_policy_test_12" % delay)
    sys.stdout.flush()

    prev_pressed = False
    recovering = False
    try:
        with open(device, "rb") as f:
            while True:
                chunk = f.read(JS_EVENT_SIZE)
                if len(chunk) < JS_EVENT_SIZE:
                    continue
                _t, value, etype, number = struct.unpack(JS_EVENT_FMT, chunk)
                if not (etype & JS_EVENT_BUTTON) or number != btn:
                    continue
                pressed = (value == 1)
                # 上升沿 + 当前没在恢复中 → 触发
                if pressed and not prev_pressed and not recovering:
                    recovering = True
                    do_recovery(delay)
                    recovering = False
                prev_pressed = pressed
    except KeyboardInterrupt:
        print("\n退出。")
    except PermissionError:
        sys.exit("没有读 %s 的权限。解决：sudo usermod -aG input $USER 然后重新登录，"
                 "或直接 sudo 运行本脚本。" % device)


if __name__ == "__main__":
    main()
