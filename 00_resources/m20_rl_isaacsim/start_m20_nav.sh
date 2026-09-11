#!/bin/bash

# ==========================================
# M20 导航模式一键启动脚本
# ==========================================

usage() {
        cat <<'EOF'
Usage: ./start_m20_nav.sh [--headless] [--help] [-- <extra args>]

Options:
    --headless    Run without GUI; use terminal keys to control navigation.
    --help, -h    Show this help message.

Headless terminal controls (when using --headless in this terminal):
    ↑ / ↓ / ← / →    move
    n / m            yaw left / right
    k                plan + start
    g                plan only
    p                start auto
    c or Space       cancel / stop

Any extra flags after a double-dash `--` are forwarded to the Python app.
EOF
}

# 1. 初始化 ROS2 环境
echo "[Step 1] Sourcing ROS2 Jazzy workspaces..."

source ~/IsaacSim-ros_workspaces/build_ws/jazzy/jazzy_ws/install/local_setup.bash
source ~/IsaacSim-ros_workspaces/build_ws/jazzy/isaac_sim_ros_ws/install/local_setup.bash

# 2. 检查必要的路径是否存在 (可选，但推荐)
SCRIPT_PATH="scripts/reinforcement_learning/rsl_rl/m20_nav_app.py"
ONNX_PATH="exported/m20_new_policy.onnx"

HEADLESS_FLAG=""
USER_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--headless" ]; then
        HEADLESS_FLAG="--headless"
    elif [ "$arg" = "--help" ] || [ "$arg" = "-h" ]; then
        usage
        exit 0
    else
        USER_ARGS+=("$arg")
    fi
done

if [ ! -f "$SCRIPT_PATH" ]; then
    echo "错误: 找不到脚本 $SCRIPT_PATH，请在 Isaac Lab 根目录下运行此 sh"
    exit 1
fi

# 3. 启动仿真程序
echo "[Step 2] Starting M20 Navigation with Isaac Lab..."

# 建议使用 Isaac Lab 的 Python 入口以确保路径正确
# 如果你之前直接用 python 成功了，也可以保持不变PerceptionFixedObstacle-Deeprobotics-M20-v0
if [ "$HEADLESS_FLAG" = "--headless" ]; then
    echo "[Info] Running in headless mode. Use terminal keys to control navigation (see --help)."
fi
python "$SCRIPT_PATH" \
    $HEADLESS_FLAG \
    --task=PerceptionFixedObstacle-Deeprobotics-M20-v0 \
    --onnx="$ONNX_PATH" \
    --nav \
    --enable_ros2_bridge \
    --real-time \
    --goal_x 32.0 \
    --goal_y -53.0 "${USER_ARGS[@]}"

# python "$SCRIPT_PATH" \
#     --task=Flat-Deeprobotics-M20-v0 \
#     --onnx="$ONNX_PATH" \
#     --cmd_vel \
#     --enable_ros2_bridge \
#     --real-time \
