#!/usr/bin/env bash
#
# 供应 code-server（WebIDE 服务端），使云原生开发以**单容器模式**启动。
#
# 为什么必须做这件事（见 issue #31 与 PR 描述）：
#   CNB 云原生开发有单/双容器两种模式：开发环境容器里"没有" code-server 时，
#   平台会额外起一个 code-server 容器（双容器模式）。此时 WebIDE 实际连的是
#   code-server 容器，访问开发环境必须走"跨容器终端"（名为 CNB 的终端）。
#   我们的镜像（根 Dockerfile）只装了 openssh-server/chromium/训练栈，没有
#   code-server -> 每次点「云原生开发」都进双容器模式，终端长时间停在
#   「连接到 CNB 容器中...」，且插件/Debug 等能力也受限。
#
#   把 code-server 装进镜像层 = 单容器模式：终端直连开发容器，秒进；
#   训练 venv、根 Dockerfile 里的工具与 WebIDE 在同一个容器内。
#
# 本脚本同时被两处消费：
#   1. Dockerfile（构建期）：把 code-server 固化进镜像层；
#   2. CI 门禁（.cnb.yml）：构建完镜像后断言 `code-server --version` 可执行，
#      防止 Dockerfile 层被误删后悄悄退回双容器模式（回归哨兵）。
#
# 幂等：已存在可执行的 code-server 时直接复用（--version 自检），除非 FORCE=1。
#
# 用法：
#   bash scripts/provision_code_server.sh
# 环境变量：
#   FORCE               1 = 强制重装
#   CODE_SERVER_VERSION 指定版本（默认让官方安装脚本取 stable）
set -euo pipefail

FORCE="${FORCE:-0}"
CODE_SERVER_BIN="$(command -v code-server || true)"

if [ "$FORCE" != "1" ] && [ -n "$CODE_SERVER_BIN" ] && "$CODE_SERVER_BIN" --version >/dev/null 2>&1; then
    echo "[code-server] 已就绪（复用）：$("$CODE_SERVER_BIN" --version)"
    exit 0
fi

# 官方安装脚本（文档：云原生开发 FAQ / 自定义开发环境）。
# 走官方脚本而非写死 URL：它会按发行版挑合适的扩展名与依赖。
if [ -n "${CODE_SERVER_VERSION:-}" ]; then
    echo "[code-server] 安装指定版本 $CODE_SERVER_VERSION"
    curl -fsSL https://code-server.dev/install.sh | sh -s -- --version "$CODE_SERVER_VERSION"
else
    echo "[code-server] 安装 stable"
    curl -fsSL https://code-server.dev/install.sh | sh
fi

# 自检：装完必须能执行，否则构建期就失败（不要把问题留给运行时）。
if ! command -v code-server >/dev/null 2>&1; then
    echo "[code-server] 安装后仍找不到 code-server，安装失败" >&2
    exit 1
fi
echo "[code-server] 安装完成：$(code-server --version)"
