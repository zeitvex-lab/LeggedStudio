#!/usr/bin/env bash
set -euo pipefail

SHELL_FOLDER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "SHELL_FOLDER: $SHELL_FOLDER"

pushd "$SHELL_FOLDER/../../../bin" >/dev/null || exit

# 配置 mqtt broker ip
export MQTT_BROKER_IP=${MQTT_BROKER_IP:-"127.0.0.1"}

# 框架默认会写到 ${AGIBOT_HOME}/agibot 下；在开发容器里通常没有 /agibot 权限
export AGIBOT_HOME="${AGIBOT_HOME:-/tmp}"

# 配置中的 mqtt broker ip，可根据实际情况修改
RMW_LIBRARY_PATH="$(pwd)/librmw_fastrtps.so" LD_LIBRARY_PATH="./:${LD_LIBRARY_PATH:-}" ./demo5 --cfg_file_path=cfg_demo5_config.yaml

popd  || exit
