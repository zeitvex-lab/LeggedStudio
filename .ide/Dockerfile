# Legged Studio 云原生开发环境
#
# 单一环境事实源：云原生开发（.cnb.yml 的 vscode 事件）与 CI 共用同一镜像，
# 保证「本地开发看到的」和「CI 跑的」是同一套依赖，杜绝环境漂移。
#
# 设计要点：
#   - 必须 Python 3.12：pyproject.toml 钉的是 >=3.12,<3.13，且 /api/system/environment
#     会校验 python_target_match，3.11 会让体检页报红（见 backend/api_complete.py）。
#   - 控制面依赖（backend/requirements.txt）与 CI 完全一致；onnxruntime 是
#     tools/sim2sim_headless.py CPU 验收器的运行时依赖，一并固化。
#   - Playwright + Chromium 预装进入镜像层：浏览器是刚需（看 sim2sim / 截图调试），
#     装进镜像后每次进环境都是现成的，不再重装。
#   - **CPU 训练链路**（ARG INSTALL_CPU_TRAINING，默认开）：用 adapters/mjlab
#     的 cpu extra 在仓库外装一份训练 venv，容器里就能真跑「建 env → rollout →
#     N 轮 PPO」。与 GPU 机器共用同一份 uv.lock，只换 torch 轮子来源
#     （pytorch-cpu index），因此 device=auto 会稳定落 cpu。
#     体积约 2 GB；只要控制面时用 --build-arg INSTALL_CPU_TRAINING=0。
FROM python:3.12-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright \
    # 无显示环境：MuJoCo 不需要 GL 上下文，避免容器缺 EGL/OSMesa 时报错。
    MUJOCO_GL=disabled \
    # CPU 训练 venv 落点（仓库外）：避免被 bind mount 覆盖，仓库代码只消费它。
    LEGGED_STUDIO_MJLAB_VENV=/opt/legged-studio/mjlab-cpu/.venv

# 系统层：git/ssh（WebIDE 需要）、中文字体（截图里会渲染中文页面）、
# 图形/媒体库（MuJoCo + Chromium 无头运行所需）。
RUN apt-get update && apt-get install -y --no-install-recommends \
        git openssh-server curl wget unzip ca-certificates \
        build-essential pkg-config \
        libgl1 libegl1 libglib2.0-0 libglew2.2 libosmesa6 \
        fonts-noto-cjk fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# 控制面依赖先装（单独一层，backend/requirements.txt 不变则不失效）
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir onnxruntime httpx playwright pytest pytest-playwright

# 浏览器固化进镜像（含系统依赖），开发环境与 E2E 秒起
RUN playwright install --with-deps chromium

# uv：与 adapters/mjlab/uv.lock 对齐（版本同 scripts/provision_windows_runtime.ps1）。
ARG UV_VERSION=0.11.8
RUN curl -fsSL "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh \
    && install -m 0755 /root/.local/bin/uv /usr/local/bin/uv \
    && uv --version

# ---------------------------------------------------------------------------
# CPU 训练链路（默认装；--build-arg INSTALL_CPU_TRAINING=0 可跳过）
# ---------------------------------------------------------------------------
# 只 COPY 适配器工程的 pyproject/uv.lock 与供应脚本：业务代码改动不会让这层失效。
COPY adapters/mjlab/pyproject.toml adapters/mjlab/uv.lock /opt/legged-studio/adapter/
COPY scripts/provision_cpu_training.sh /opt/legged-studio/scripts/

ARG INSTALL_CPU_TRAINING=1
RUN if [ "$INSTALL_CPU_TRAINING" = "1" ]; then \
        LEGGED_STUDIO_UV_BIN=/usr/local/bin/uv \
        LEGGED_STUDIO_ADAPTER_DIR=/opt/legged-studio/adapter \
        FORCE=1 bash /opt/legged-studio/scripts/provision_cpu_training.sh \
        && "$LEGGED_STUDIO_MJLAB_VENV/bin/python" -c \
             "import torch, mjlab, warp, mujoco_warp; print('[image] cpu training stack', torch.__version__)" ; \
    else \
        echo "[image] INSTALL_CPU_TRAINING=0 -> skipping CPU training venv" ; \
    fi

WORKDIR /workspace
