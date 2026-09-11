#!/usr/bin/env bash
set -e

echo "开始配置 CAN 接口..."

for i in 0 1 2 3 ; do
  iface="can${i}"
  echo "------------------------------"
  echo "正在配置 ${iface}"

  if ! ip link show "${iface}" >/dev/null 2>&1; then
    echo "错误: ${iface} 不存在，跳过"
    continue
  fi

  echo "设置 ${iface} bitrate=1000000 sample-point=0.75"
  sudo ip link set "${iface}" type can bitrate 1000000 sample-point 0.75

  echo "启动 ${iface}"
  sudo ip link set "${iface}" up

  echo "当前 ${iface} 状态:"
  ip -details link show "${iface}"

  echo "${iface} 配置完成"
done

echo "------------------------------"
echo "所有 CAN 接口配置流程结束"
source install/setup.bash