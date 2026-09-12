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
FROM python:3.12-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

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

WORKDIR /workspace
