# Legged Studio 云原生开发环境
#
# 单一环境事实源：云原生开发（.cnb.yml 的 vscode 事件）与 CI 共用同一镜像，
# 保证「本地开发看到的」和「CI 跑的」是同一套依赖，杜绝环境漂移。
#
# 消费方（.cnb.yml 的 `docker.build`）必须与本文件配套声明 `by` 清单：
# CNB 只把 Dockerfile 与 `by` 列出的文件放进构建上下文，未列出的文件在
# COPY 时会报 "not found"（本次 CI 失败的根因）。`by` 路径相对仓库根，
# 因此本文件放在仓库根、`by` 写 backend/... 等仓库内路径最直观。
# 清单见 .cnb.yml 的 `.docker-dev-image` 锚点（云原生开发/CI 三处共用）。
#
# 设计要点：
#   - **必须装 code-server**（WebIDE 服务端）：开发环境容器里没有 code-server 时，
#     CNB 会退回"双容器模式"，终端停在「连接到 CNB 容器中...」、插件能力受限
#     （见 .cnb.yml 的 vscode 段与 docs.cnb.cool/zh/workspaces/double-container.md）。
#     装进镜像 -> 单容器模式 -> 进环境秒连开发容器。
#   - CodeBuddy Web 入口：镜像内装 codebuddy（>= 2.137.0）后自动出现在云开发入口页。
#   - 基础镜像 = **Ubuntu 24.04 LTS**（noble）。此前是 python:3.12-bookworm
#     （Debian 12），Ubuntu 24.04 的 python3 官方源就是 **3.12**，因此
#     apt 直装即可满足 pyproject.toml 的 >=3.12,<3.13 与
#     /api/system/environment 的 python_target_match，无需 PPA / 源码编译。
#   - 控制面依赖（backend/requirements.txt）与 CI 完全一致；onnxruntime 是
#     tools/sim2sim_headless.py CPU 验收器的运行时依赖，一并固化。
#   - Playwright + Chromium 预装进入镜像层：浏览器是刚需（看 sim2sim / 截图调试），
#     装进镜像后每次进环境都是现成的，不再重装。
#   - **CPU 训练链路**（ARG INSTALL_CPU_TRAINING，默认开）：用 adapters/mjlab
#     的 cpu extra 在仓库外装一份训练 venv，容器里就能真跑「建 env → rollout →
#     N 轮 PPO」。与 GPU 机器共用同一份 uv.lock，只换 torch 轮子来源
#     （pytorch-cpu index），因此 device=auto 会稳定落 cpu。
#     体积约 2 GB；只要控制面时用 --build-arg INSTALL_CPU_TRAINING=0。
FROM ubuntu:24.04

# APT 包名迁移说明（bookworm → noble）。**已对 noble 的 apt 索引逐项核对**
# （dists/noble{-updates}/{main,universe}/binary-amd64/Packages），改了三处：
#   - libgl1-mesa-glx  → 24.04 已**删除**（两个源都查不到），改为 libgl1 + libglx-mesa0；
#   - libglib2.0-0     → 24.04 因 time_t 64 位过渡**改名 libglib2.0-0t64**（旧名查不到，
#                        不换包会在 apt 阶段直接 configure 失败，而不是运行期才出错）；
#   - libglew2.2 / libosmesa6 → 名字不变，但只在 universe，故 keep 现状。
# python3 在 noble 是 3.12.3（`python3.12` 包版本 3.12.3-1），符合 >=3.12,<3.13。
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright \
    # 无显示环境：MuJoCo 不需要 GL 上下文，避免容器缺 EGL/OSMesa 时报错。
    MUJOCO_GL=disabled \
    # CPU 训练 venv 落点（仓库外）：避免被 bind mount 覆盖，仓库代码只消费它。
    LEGGED_STUDIO_MJLAB_VENV=/opt/legged-studio/mjlab-cpu/.venv

# 系统层：python3（24.04 官方源即 3.12）+ venv + pip、git/ssh（WebIDE 需要）、
# 中文字体（截图里会渲染中文页面）、图形/媒体库（MuJoCo + Chromium 无头运行所需）。
#
# 注意用的是 `python3` 而非 PATH 里的 `python`：Ubuntu 不提供 `python` 别名，
# 而 backend 与 tools 的调用口径是 `python -m ...`（CI 与本镜像同一口径），
# 因此显式建 /usr/local/bin/python → python3 软链，避免两套解释器命令漂移。
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev python3-pip \
        git openssh-server curl wget unzip ca-certificates \
        build-essential pkg-config \
        libgl1 libglx-mesa0 libegl1 libglib2.0-0t64 libglew2.2 libosmesa6 \
        fonts-noto-cjk fonts-dejavu-core \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && python --version \
    && rm -rf /var/lib/apt/lists/*

# 控制面依赖先装（单独一层，backend/requirements.txt 不变则不失效）
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && pip install --no-cache-dir --break-system-packages \
         onnxruntime httpx playwright pytest pytest-playwright

# 浏览器固化进镜像（含系统依赖），开发环境与 E2E 秒起
RUN playwright install --with-deps chromium

# ---------------------------------------------------------------------------
# Node.js 底座（code-server / codebuddy / MCP 的 npx 共同前提）
# ---------------------------------------------------------------------------
# noble 官方源的 nodejs 是 18.x，且下方「开发期 MCP 工具链」段用的 NodeSource 22.x
# 会与 apt 版互相覆盖，因此这里**统一用 NodeSource 22.x 装一次**，两段共用。
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version

# uv：与 adapters/mjlab/uv.lock 对齐（版本同 scripts/provision_windows_runtime.ps1）。
ARG UV_VERSION=0.11.8
RUN curl -fsSL "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh \
    && install -m 0755 /root/.local/bin/uv /usr/local/bin/uv \
    && uv --version

# ---------------------------------------------------------------------------
# WebIDE 服务端（code-server）+ CodeBuddy Web
# ---------------------------------------------------------------------------
# 为什么在镜像层装（而不是让平台补容器）：
#   CNB 云原生开发按"开发环境容器里有没有 code-server"判定单/双容器模式。
#   本镜像没装时走双容器模式，WebIDE 连的是 code-server 容器，要在开发容器里
#   干活得切"跨容器终端"（名为 CNB），表现为终端长时间停在「连接到 CNB 容器中...」。
#   装进镜像后走单容器模式，终端直连开发容器，且 WebIDE 能直接看到镜像里的
#   训练 venv、mujoco、chromium。
COPY scripts/provision_code_server.sh /opt/legged-studio/scripts/
RUN FORCE=1 bash /opt/legged-studio/scripts/provision_code_server.sh \
    && code-server --version

# CodeBuddy Web：镜像里装了 >= 2.137.0 的 codebuddy 才会在云开发入口页出现该入口。
# 装失败不影响 WebIDE（单容器模式只依赖 code-server），因此不阻断构建。
RUN npm install -g @tencent-ai/codebuddy-code@latest 2>/dev/null \
    && (codebuddy --version || echo "[image] codebuddy 版本未知") \
    || echo "[image] codebuddy 安装失败 -> CodeBuddy Web 入口不可用（WebIDE 不受影响）"

# ---------------------------------------------------------------------------
# 开发期 MCP 工具链（`.cnb/mcp/servers.json` 的 11 条，见 .cnb/mcp/README.md）
# ---------------------------------------------------------------------------
# 只装 runner（node/npx 与 uvx），**不预装各 server 本体**：MCP server 是
# 开发期按需拉取的工具，固化进镜像会让「控制面镜像」与「工具链」两个关注点
# 耦合，还会拖慢每次进环境。node/npm 已在上方 Node.js 底座段装好，这里只做
# npx runner 自检。
RUN npx -y @modelcontextprotocol/server-filesystem --help >/dev/null 2>&1 || true

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
