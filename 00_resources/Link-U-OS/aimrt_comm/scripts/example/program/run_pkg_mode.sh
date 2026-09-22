#!/usr/bin/env bash
set -euo pipefail

SHELL_FOLDER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "SHELL_FOLDER: $SHELL_FOLDER"

pushd "$SHELL_FOLDER/../../../bin" >/dev/null || exit

# 框架默认会写到 ${AGIBOT_HOME}/agibot 下；在开发容器里通常没有 /agibot 权限
export AGIBOT_HOME="${AGIBOT_HOME:-/tmp}"

# 兼容 build/bin + build/lib 两种布局
export LD_LIBRARY_PATH="./:../lib:${LD_LIBRARY_PATH:-}"

RMW_LIBRARY_PATH="$(pwd)/librmw_fastrtps.so" ./aimrte --cfg_file_path=../config/example/program/pkg_mode_config.yaml --process_name=pkg_demo "$@"

popd || exit
