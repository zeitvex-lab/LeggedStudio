#!/bin/bash
# ============================================================
# 监听 Xbox 手柄，每次按下 A 键 → 杀旧进程 → 启动
# real_motor_controller → 等 5 秒 → 启动 dog_policy_test_12。
#
# ★ 用途：狗子倾倒保护后，按 A 一键重启恢复。可重复触发。
#
# 用法（在 himdog 目录下）:
#     source install/setup.bash
#     bash src/dog_policy_test/scripts/launch_policy_on_a.sh
#
# 可选参数:
#     bash launch_policy_on_a.sh [js设备] [延迟秒] [按键索引]
#     js设备   默认自动探测 /dev/input/js*（一般 js0）
#     延迟秒   默认 5
#     按键索引 默认 0（A 键）
# ============================================================

# ==================== 可直接改的配置 ====================
BUTTON_INDEX=0          # 0 = A 键
DELAY_SEC=5             # real_motor_controller 起来后，等几秒再起 dog_policy_test_12
KILL_NAMES="real_motor_controller dog_policy_test_12"   # 恢复时先杀的旧进程
SESSION="dog"           # tmux 会话名（两条命令分别放在两个窗口里）
LOG_DIR="$HOME/himdog/logs"   # 节点输出日志目录（另开终端 tail -f 实时看模型/高度等信息）
# =======================================================

# ---- 参数解析 ----
JS_DEV="${1:-}"
[ -n "$2" ] && DELAY_SEC="$2"
[ -n "$3" ] && BUTTON_INDEX="$3"

# ---- 检测手柄设备 ----
if [ -z "$JS_DEV" ]; then
  for d in /dev/input/js*; do
    [ -e "$d" ] && JS_DEV="$d" && break
  done
fi
if [ -z "$JS_DEV" ]; then
  echo "找不到手柄设备 /dev/input/js* —— 插好手柄后重试，"
  echo "或把设备路径作为第一个参数传入，例如：bash launch_policy_on_a.sh /dev/input/js0"
  exit 1
fi

echo "手柄设备: $JS_DEV"
echo "等待按下 A 键(button $BUTTON_INDEX)触发恢复 ……（可重复触发，Ctrl+C 退出）"
echo "流程: 杀旧进程 → real_motor_controller → 等 ${DELAY_SEC}s → dog_policy_test_12"
echo ""
echo "查看节点输出（另开一个 SSH/终端）:"
echo "  实时看日志:   tail -f ~/himdog/logs/dog_policy_test_12.log   ← 模型信息/高度都在这"
echo "  或进 tmux:    tmux attach -t ${SESSION}（Ctrl+B 0/1 切窗口，Ctrl+B D 脱离）"
echo ""

# ---- 杀掉旧进程，避免重复节点抢电机/话题 ----
kill_old() {
  for name in $KILL_NAMES; do
    pkill -f "$name" 2>/dev/null
  done
  sleep 1   # 给旧进程时间退出、释放串口/话题
}

# ---- 把命令丢进 tmux 窗口运行 ----
# 用 tmux 是因为 SSH/纯命令行环境下没有图形桌面，gnome-terminal 开不了窗口。
# 而且节点跑在 tmux 里，SSH 断了也不会死，随时 tmux attach 回来看输出。
# 额外把输出 tee 到日志文件，方便另开终端 tail -f 实时看（模型信息/高度等）。
spawn_term() {
  local title="$1" cmd="$2"
  local log="$LOG_DIR/${title}.log"
  # 2>&1 合并 stderr；tee 不带 -a，每次重启覆盖，日志只保留本次运行输出
  local wrapped="cd ~/himdog && source install/setup.bash && $cmd 2>&1 | tee $log; echo '(已退出)'; exec bash"
  # 第一个窗口用 new-session 建会话，后续窗口用 new-window
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux new-window -t "$SESSION" -n "$title" "$wrapped"
  else
    tmux new-session -d -s "$SESSION" -n "$title" "$wrapped"
  fi
  echo "  [tmux 窗口] $title  (日志: $log)"
}

# ---- 完整恢复流程 ----
recover() {
  echo ">>> [恢复] 杀掉旧进程 ..."
  kill_old
  mkdir -p "$LOG_DIR"   # 确保日志目录存在
  # 顺手把旧的 tmux 会话关掉（里面装着旧节点窗口），干净重来
  tmux kill-session -t "$SESSION" 2>/dev/null

  echo ">>> [恢复] 启动 real_motor_controller"
  spawn_term "real_motor_controller" \
    "cd ~/himdog && source install/setup.bash && ros2 run dog_control real_motor_controller"

  echo ">>> [恢复] 等待 ${DELAY_SEC} 秒 ..."
  local i
  for ((i=DELAY_SEC; i>0; i--)); do
    echo "    $i ..."
    sleep 1
  done

  echo ">>> [恢复] 启动 dog_policy_test_12"
  spawn_term "dog_policy_test_12" \
    "cd ~/himdog && source install/setup.bash && ros2 run dog_policy_test dog_policy_test_12 --ros-args --params-file ./src/dog_policy_test/config/policy_params_12.yaml"

  echo ">>> [恢复] 完成，等待下一次 A 键 ..."
  echo ""
}

# ---- tmux 可用性检查（SSH/纯命令行环境靠 tmux 开窗口，没图形桌面）----
if ! command -v tmux >/dev/null 2>&1; then
  echo "没装 tmux，无法后台开窗口。请先安装: sudo apt install tmux"
  exit 1
fi

# ---- 权限检查 ----
if [ ! -r "$JS_DEV" ]; then
  echo "没有读 $JS_DEV 的权限。"
  echo "解决: sudo usermod -aG input \$USER 然后重新登录，或直接 sudo 运行本脚本。"
  exit 1
fi

# ---- 主循环：读 js0 二进制事件，监听 A 键上升沿 ----
# Linux joystick 事件结构(8 字节):
#   time(u32, byte0-3) value(i16 LE, byte4-5) type(u8, byte6) number(u8, byte7)
#   type & 0x01 = 按键事件；value=1 按下 / 0 松开；number=按键索引
prev=0
while true; do
  # 每次读一个 8 字节事件
  line=$(dd if="$JS_DEV" bs=8 count=1 2>/dev/null | od -An -tu1)
  [ -z "$line" ] && { sleep 0.2; continue; }

  set -- $line
  # $1..$8 = byte0..byte7
  b4="$5"; b5="$6"; type="$7"; number="$8"

  [ "$number" -eq "$BUTTON_INDEX" ] || continue
  (( type & 1 )) || continue        # 只处理按键事件

  # value = b4 + b5*256 （little-endian i16，按下=1）
  v=$(( b4 + b5*256 ))
  [ "$v" -ge 32768 ] && v=$(( v - 65536 ))

  # 上升沿：松开(0) → 按下(1)，触发恢复
  # recover() 是同步执行的，期间 dd 没在读，自然忽略新的 A 键
  if [ "$v" -eq 1 ] && [ "$prev" -eq 0 ]; then
    recover
  fi
  prev="$v"
done
