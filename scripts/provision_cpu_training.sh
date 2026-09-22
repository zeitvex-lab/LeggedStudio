#!/usr/bin/env bash
#
# 供应 CPU 训练链路（Linux / 云原生开发容器）。
#
# 背景：控制面永远不 import 训练栈（torch/mjlab），训练跑在
# adapters/mjlab/.venv 隔离解释器里。GPU 机器用 cu128 extra，**无 GPU 的
# 机器用 cpu extra**——同一份 uv.lock、同一个适配器工程，只是 torch 轮子
# 来源不同（pytorch-cpu index），因此 torch.cuda.is_available() 为 False 时
# 训练链路会自动落 device=cpu（native_worker 的 device=auto → cpu 回退）。
#
# 用法：
#   scripts/provision_cpu_training.sh                     # 装到 adapters/mjlab/.venv
#   LEGGED_STUDIO_MJLAB_VENV=<path> scripts/...           # 指定 venv 落点
#   LEGGED_STUDIO_ADAPTER_DIR=<dir> scripts/...           # 指定适配器工程目录（镜像构建）
#
# 幂等：已存在且可导入 mjlab 的 venv 会直接复用（除非 FORCE=1）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# 适配器工程目录：默认取仓库内路径；镜像构建时只有 pyproject/uv.lock 被 COPY 到
# /opt/legged-studio/adapter，用 LEGGED_STUDIO_ADAPTER_DIR 指向它即可。
ADAPTER_DIR="${LEGGED_STUDIO_ADAPTER_DIR:-$ROOT/adapters/mjlab}"
VENV_DIR="${LEGGED_STUDIO_MJLAB_VENV:-$ROOT/adapters/mjlab/.venv}"
# 与 scripts/provision_windows_runtime.ps1 的 uvVersion 保持一致，避免两套链路漂移。
UV_VERSION="${LEGGED_STUDIO_UV_VERSION:-0.11.8}"
UV_BIN="${LEGGED_STUDIO_UV_BIN:-}"

log() { printf '[cpu-training] %s\n' "$*"; }

# 1) 定位 uv：环境变量 > PATH > 安装到 /usr/local/bin。
#
# 注意：`LEGGED_STUDIO_UV_BIN` 是**候选**而非硬性契约。此前只看"变量非空"就
# 直接信任，于是 .cnb.yml 里写死的 `LEGGED_STUDIO_UV_BIN=/usr/local/bin/uv`
# 在**不含 uv 的底座**上（如 python:3.12 镜像）会让本脚本在第 3 步
# `"$UV_BIN" sync` 直接 `No such file or directory`（退出码 127，实测于
# PR #47 构建 cnb-p9g-1k33d6d1m-003）。改成**先验证可执行**：不可执行就回落到
# PATH 探测 / 自动安装，保证"指定的路径不存在"不再等于"直接失败"。
if [ -n "$UV_BIN" ] && [ ! -x "$UV_BIN" ]; then
    log "指定的 uv 不可执行（$UV_BIN），回落到 PATH 探测/自动安装"
    UV_BIN=""
fi
if [ -z "$UV_BIN" ]; then
    if command -v uv >/dev/null 2>&1; then
        UV_BIN="$(command -v uv)"
    else
        log "uv not found; installing uv $UV_VERSION"
        # 官方脚本优先（装到 ~/.local/bin，不依赖底座有 pip）；失败再退回 pip 安装
        # （CI 底座 python:3.12 自带 pip，是 curl 不可用时的兜底，避免单点依赖）。
        curl -fsSL "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
        UV_BIN="$(command -v uv || echo "$HOME/.local/bin/uv")"
        if [ ! -x "$UV_BIN" ]; then
            log "官方安装脚本未生效，尝试 pip install uv==$UV_VERSION"
            python3 -m pip install --quiet --break-system-packages "uv==$UV_VERSION" 2>/dev/null \
                || pip install --quiet "uv==$UV_VERSION" 2>/dev/null \
                || true
            UV_BIN="$(command -v uv || echo "")"
        fi
    fi
fi
# 自举后仍拿不到可执行的 uv 就显式失败，避免用一条 127 把根因藏进调用栈。
[ -x "$UV_BIN" ] || { log "[FAIL] 无法获得可执行的 uv（候选：$UV_BIN）"; exit 1; }
log "uv: $UV_BIN ($("$UV_BIN" --version 2>/dev/null || echo unknown))"

# 2) 幂等短路：venv 已存在且能导入训练栈就不重装。
PY="$VENV_DIR/bin/python"
if [ "${FORCE:-0}" != "1" ] && [ -x "$PY" ]; then
    if "$PY" - <<'PY' >/dev/null 2>&1
import tyro, warp, mujoco_warp, rsl_rl, mjlab  # noqa: F401
import torch
PY
    then
        log "reusing existing CPU training venv: $VENV_DIR ($("$PY" -c 'import torch;print(torch.__version__)'))"
        echo "$VENV_DIR"
        exit 0
    fi
    log "existing venv incomplete; reinstalling"
fi

# 3) 装 CPU extra（--extra cpu 把 torch 固定到 pytorch-cpu index）。
#    --no-dev：训练运行不需要 pytest/ruff 等开发组。
log "syncing mjlab cpu extra -> $VENV_DIR"
cd "$ADAPTER_DIR"
UV_PROJECT_ENVIRONMENT="$VENV_DIR" "$UV_BIN" sync --extra cpu --no-dev

# 4) 验收：训练栈可导入（native_worker 的运行时依赖集），并打印设备形态。
"$PY" - <<'PY'
import torch, warp, mujoco_warp, mjlab  # noqa: F401

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[cpu-training] torch={torch.__version__} cuda_available={torch.cuda.is_available()} -> device={device}")
PY

log "done: $VENV_DIR"
echo "$VENV_DIR"
