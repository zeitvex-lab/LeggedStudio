#!/usr/bin/env bash
set -e

if [ ! -e /dev/ttyACM0 ]; then
  echo "/dev/ttyACM0 不存在"
  exit 1
fi

sudo chmod 666 /dev/ttyACM0
echo "已设置 /dev/ttyACM0 权限为 666"
source install/setup.bash
ros2 launch dm_imu dm_imu.launch.py 
