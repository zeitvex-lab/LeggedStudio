#!/usr/bin/env bash
# run.sh — Launch the mobile manipulation pipeline with the correct ROS environment.
#
# The interbotix_xs_modules package lives in a ROS 1 (Noetic) catkin workspace.
# It requires both ROS core and the interbotix workspace to be sourced before
# Python can import it.
#
# Usage:
#   ./run.sh                     # normal run
#   ./run.sh --show              # show arm-camera debug window
#   ./run.sh --skip_arm          # navigation only (no arm)
#   ./run.sh --iface eth0        # specify network interface

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Source ROS Noetic ────────────────────────────────────────────────────────
if [ -f /opt/ros/noetic/setup.bash ]; then
    source /opt/ros/noetic/setup.bash
else
    echo "[run.sh] ERROR: ROS Noetic not found at /opt/ros/noetic"
    exit 1
fi

# ── Source interbotix workspace ──────────────────────────────────────────────
if [ -f /home/unitree/interbotix_ws/devel/setup.bash ]; then
    source /home/unitree/interbotix_ws/devel/setup.bash
elif [ -f /home/unitree/interbotix_ws/install/setup.bash ]; then
    source /home/unitree/interbotix_ws/install/setup.bash
else
    echo "[run.sh] ERROR: interbotix workspace not found"
    exit 1
fi

echo "[run.sh] ROS_DISTRO=${ROS_DISTRO}"
echo "[run.sh] PYTHONPATH includes interbotix: $(echo $PYTHONPATH | tr ':' '\n' | grep interbotix | head -1)"

# ── Run pipeline ─────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR"
exec python3 pipeline.py "$@"
