# 云原生开发环境

点仓库页面的 **「Legged Studio 开发」** 按钮，即可获得一个开箱即用的在线开发环境：

- 依赖（`backend/requirements.txt` + `onnxruntime`）已固化在镜像里，**每次进入都不用重新配环境**；
- Chromium + Playwright 预装，浏览器 sim2sim 可直接看、可直接截图；
- **CPU 训练链路已就绪**：mjlab 的 `cpu` extra 装在镜像内的隔离 venv
  （`/opt/legged-studio/mjlab-cpu/.venv`），进环境就能真跑训练，无需等 torch 下载；
- 后端在 `0.0.0.0:8765` 自动拉起。

## 入口与预览地址

| 用途 | 地址 |
|---|---|
| 工作台 | `${CNB_VSCODE_PROXY_URI/\{\{port\}\}/8765}/web/workbench.html` |
| sim2sim | `${CNB_VSCODE_PROXY_URI/\{\{port\}\}/8765}/web/sim2sim/index.html` |
| API 文档 | `${CNB_VSCODE_PROXY_URI/\{\{port\}\}/8765}/docs` |

`CNB_VSCODE_PROXY_URI` 形如 `https://xxx-{{port}}.cnb.run`，把 `{{port}}` 换成 `8765`。
也可以在 WebIDE 的 **PORTS** 面板手动添加 `8765` 端口映射。

> 服务必须监听 `0.0.0.0`（不能是 `127.0.0.1`），否则预览 URL 打不开。
> 后端已按此启动，无需手工调整。

## 环境结构

```
Dockerfile                       # 唯一环境事实源：云原生开发与 CI 共用同一镜像
.cnb.yml  $: vscode              # 启动流程：起后端 + 打印预览地址（不做重复安装）
.cnb.yml  .docker-dev-image      # 上述镜像的 docker.build 配置（含 by 文件清单）
.cnb/settings.yml                # 入口按钮名称 / CPU 核数 / 自动打开 WebIDE
scripts/provision_cpu_training.sh  # CPU 训练 venv 供应（镜像构建与本地同一脚本）
scripts/cpu_training_smoke_gate.sh # CPU 训练冒烟门禁（CI 与本地同一命令）
```

依赖与浏览器都在镜像层，`stages` 里**不放安装命令**，所以进入环境是秒级的。

### 改 Dockerfile 时别忘 `by` 清单

CNB 的 `docker.build` **只把 Dockerfile 与 `by` 列出的文件放进构建上下文**
（官方文档：未出现在 `by` 列表中的文件不会被 COPY 进镜像）。所以：

- Dockerfile 里每加一条 `COPY <repo 内文件>`，都必须把该文件加进
  `.cnb.yml` 的 `.docker-dev-image.by`，否则构建报 `"<path>": not found`；
- `by` 路径相对**仓库根**（不是 Dockerfile 所在目录）。

漏加 `by` 的表现是 `Prepare` 阶段直接失败（空上下文），而不是进容器后才报错。

## 浏览器验证（浏览器是刚需）

`?debug=1` 会暴露一套调试 API，供人肉排查与自动化截图调试复用：

| API | 作用 |
|---|---|
| `window.__sim2simDebug.state()` | 模型/几何/状态的完整快照 |
| `window.__sim2simDebug.sample()` | 单帧物理+策略状态（基座高度、姿态、指令） |
| `window.__sim2simDebug.fastForward(seconds)` | 同步快进仿真（墙钟远快于实时） |
| `window.__sim2simDebug.setPaused(bool)` | 暂停/恢复渲染循环 |
| `window.__probe` | 渲染循环持续写入的骨盆高度/动作探针 |

确定性回放：`?replay=vx,vy,wz&seed=N` —— 同一策略 + 模型 + seed
在任何机器上回放出同一条轨迹，因此**截图可以直接当回归判据**。

### E2E 测试

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt
playwright install chromium
pytest tests/e2e -v
```

用例覆盖：页面加载 + 调试探针可用、确定性回放两次采样一致、回放 2 秒不摔并落截图
（截图写到 `workspace/e2e-screenshots/`，可直接读图判断策略行为）。

## CPU 训练链路

没有 GPU 也能把训练跑起来：**mjlab 官方支持 CPU**（有 `cpu` extra / `FORCE_CPU`
测试开关），本仓库把它接成了完整链路。

### 一键跑冒烟

```bash
# 训练栈自检 + 64 envs × 20 iters 真实 PPO + 报告断言
bash scripts/cpu_training_smoke_gate.sh
# 报告：workspace/validation/cpu-training-smoke.json
```

通过时输出形如：

```
torch=2.13.0+cpu cuda_available=False MUJOCO_GL=disabled
[OK ] unitree_go2/go2-velocity-flat -> ok
CPU 训练冒烟通过：1 profile, rewards=[3.167]
```

判据有三条，缺一不算通过：rollout 的 reward **有限**、跑了 N 轮真实 PPO、
`time_outs` 已接线（否则 GAE 会把超时当终止，critic 系统性低估长 episode）。

### 本地/容器供应训练 venv

镜像里已装好；在别处（本地 Linux、别的容器）需要自己供应时：

```bash
bash scripts/provision_cpu_training.sh
# 等价于在 adapters/mjlab 下 uv sync --extra cpu --no-dev
```

供应是**幂等**的：已存在且能导入 `mjlab` 的 venv 会直接复用（`FORCE=1` 强制重装）。

### 环境变量（训练栈落点只有一处定义）

| 变量 | 作用 |
|---|---|
| `LEGGED_STUDIO_MJLAB_VENV` | 训练 venv **目录**（镜像里指向 `/opt/...`，避免被仓库 bind mount 覆盖） |
| `LEGGED_STUDIO_MJLAB_PYTHON` / `LEGGED_STUDIO_TRAIN_PYTHON` / `LEGGED_STUDIO_RUNTIME_PYTHON` | 直接指定解释器（优先级最高，桌面启动器沿用此约定） |
| `MUJOCO_GL=disabled` | 无显示环境下 MuJoCo 不初始化 GL 上下文（镜像已预设） |

这些解析集中在 `contracts/path_bootstrap.py` 的 `adapter_venv_dir()` / `adapter_python()`，
控制面、启动器、工具链都从这里取——不再各自硬编码 `adapters/mjlab/.venv`。

### 与 GPU 的关系

| 形态 | `device=auto` 落点 | 适用 |
|---|---|---|
| `cuda` | `cuda` | 正式训练（4096 envs、CUDA Graph） |
| `cpu-only` | `cpu` | 仿真 / 最小训练冒烟（64–256 envs，几分钟量级） |
| `unavailable` | —— | 训练栈没装，先跑供应脚本 |

体检（`/api/health/layers`）的 L0 就是这三态，不再只给一个"有没有 GPU"的布尔：
`cpu-only` 的处置是"能跑但建议 GPU"，`unavailable` 的处置是"先去供应环境"。

## 与 CI 的关系

云原生开发与云原生构建底层是同一套引擎，这里共用根 `Dockerfile`，
所以「开发环境里能跑通的」和「CI 里跑的」是同一套依赖，不会出现环境漂移。

| CI 任务 | 内容 |
|---|---|
| `backend-test` | 语法、契约漂移、单测、**openapi 契约冒烟**、移植准入、Pack 校验 |
| `headless-sim2sim-gate` | 47 条策略的 CPU 无头验收，对照基线只拦**新增退化** |
| `cpu-training-smoke` | CPU 训练冒烟门禁：64 envs × 20 iters 真实 PPO + 报告断言 |
| `frontend-check` | web JS 语法 + vendor 资产冒烟 |

基线文件：`tools/baselines/sim2sim_headless_baseline.json`。
仓库现存 3 条既存失败（go2 特技/跑酷量化判据未过）已记录在基线里，
门禁只守「不许新增失败」。刷新基线：

```bash
python tools/sim2sim_headless.py --seconds 3 --write-baseline tools/baselines/sim2sim_headless_baseline.json
```
