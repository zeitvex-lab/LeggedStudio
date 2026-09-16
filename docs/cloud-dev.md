# 云原生开发环境

点仓库页面的 **「Legged Studio 开发」** 按钮，即可获得一个开箱即用的在线开发环境：

- 基础镜像 = **Ubuntu 24.04 LTS**（noble），Python 3.12 来自 Ubuntu 官方源（不是 PPA）；
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
.cnb.yml  $: vscode              # 启动流程：起后端 + 打印 MCP/预览地址（不做重复安装）
.cnb.yml  .docker-dev-image      # 上述镜像的 docker.build 配置（含 by 文件清单）
.cnb/settings.yml                # 入口按钮名称 / CPU 核数 / 自动打开 WebIDE
.cnb/mcp/servers.json            # 开发期 MCP 工具链（11 条，见 .cnb/mcp/README.md）
tools/mcp/                       # 4 个自研 MCP server（契约 / MuJoCo / onnx / 资源库）
scripts/provision_cpu_training.sh  # CPU 训练 venv 供应（镜像构建与本地同一脚本）
scripts/cpu_training_smoke_gate.sh # CPU 训练冒烟门禁（CI 与本地同一命令）
```

### 基础镜像与 Python 来源

`FROM ubuntu:24.04`，Python 3.12 **apt 直装**（`python3` 在 noble 官方源就是 3.12）：

- 满足 `pyproject.toml` 的 `>=3.12,<3.13` 与 `/api/system/environment` 的
  `python_target_match`（3.11 会让体检页报红）；
- 不引 deadsnakes PPA —— 避免把外部信任源引进"唯一环境事实源"，代价是多一次
  `apt-get install python3 python3-venv python3-dev python3-pip`（约 30 秒）；
- Ubuntu 不提供 `python` 别名，镜像里显式建了 `/usr/local/bin/python → python3`，
  与 CI（`python -m ...`）保持同一调用口径。

> 由 `python:3.12-bookworm`（Debian 12）迁到 `ubuntu:24.04` 时，apt 包名要跟着改：
> `libgl1-mesa-glx` 在 noble 已删除，改为 `libgl1` + `libglx-mesa0`。

### MCP 工具链（开发期，不进镜像）

镜像只装 `npx` / `uvx` 两个 runner，**不预装各 MCP server 本体**（它们是按需拉取的
开发期工具，写进镜像会让"控制面镜像"和"工具链"两个关注点耦合）。清单与选型理由见
[`../.cnb/mcp/README.md`](../.cnb/mcp/README.md)，共 11 条：

- 通用系 6：`filesystem` / `git` / `github` / `fetch` / `playwright` / `sqlite`
  （其中 `playwright` 最刚需——本仓所有 sim2sim 结论都是浏览器实测得出的）；
- 机器人专用系 5：`tensorboard` + 4 个**自研** server
  （`mujoco` / `onnx` / `resources` / `contracts`，实现在 `tools/mcp/`）。

自研 server 只用 `mujoco` / `onnxruntime` / 标准库，**不增依赖**，因此
`backend/requirements.txt` 与 `.docker-dev-image.by` 清单都不用改。自检：

```bash
python -m unittest backend.test_mcp_servers -v          # 声明 + 4 个 server 自检 + 真调用
python -m tools.mcp.contracts_server --selftest         # 单条 server 的工具表
python -m tools.mcp.contracts_server                    # stdio 起服务（JSON-RPC）
```

依赖与浏览器都在镜像层，`stages` 里**不放安装命令**，所以进入环境是秒级的。

### WebIDE 里的 CodeBuddy（AI 助手）从哪来

WebIDE 内的 CodeBuddy 插件（`Tencent-Cloud.coding-copilot`）**不会自动注入**：

- 默认镜像 `cnbcool/default-dev-env` 预装了它，所以「不写 Dockerfile」时右键有 AI 助手；
- 本项目用自定义镜像（根 `Dockerfile`）换掉了默认镜像，这份预装随之消失——
  于是出现「云原生开发里 CodeBuddy 插件没了、右键没有 AI 助手」。

因此本镜像显式执行 `code-server --install-extension Tencent-Cloud.coding-copilot`
（见 `Dockerfile` 的「CodeBuddy IDE 插件」段），装进根用户扩展目录
`/root/.local/share/code-server/extensions`，对 WebIDE 与 VSCode Remote-SSH 同时生效。
扩展源是 open-vsx（非微软官方源），ID 见
<https://open-vsx.org/extension/Tencent-Cloud/coding-copilot>。

两种 CodeBuddy 入口别混淆：

| 入口 | 依赖 | 表现 |
|---|---|---|
| CodeBuddy Web | 镜像内有 `codebuddy` 命令且 >= 2.137.0 | 云开发入口页多一个浏览器入口 |
| CodeBuddy IDE 插件 | 镜像内预装 open-vsx 扩展 | WebIDE 编辑器内可用，有右键 AI 助手 |

启动期自检（`.cnb.yml` 的 `vscode` 段）会打印两者状态：插件缺失只告警不失败。

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
# 训练栈自检 + 16 envs × 5 iters 真实 PPO + 报告断言
# 规模可用 SMOKE_NUM_ENVS / SMOKE_ITERS 覆盖
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

> **口径边界（2026-09-16 实测登记，见任务清单 A5）**：上面这条能跑通 ≠ **产品内**训练路径
> 能跑通。`/api/training/create` 的 mjlab preflight 还要求 **mjlab 源码树**存在
> （`adapters/mjlab/native_adapter.py` 的 `DEFAULT_SOURCE`，Linux 默认 `vendor/mjlab`，
> 需含 `src/mjlab/envs/manager_based_rl_env.py` 与 `src/mjlab/rl/runner.py`），而镜像里
> **只有训练 venv、没有源码树** —— 因此在容器里点"开始训练"会拿到
> **501 `native MJLab adapter is not ready`**。
>
> 想让容器内也能跑产品路径，把源码树指过去即可（**不改仓库代码**，只影响该进程）：
>
> ```bash
> # 参考资源库里那份 mjlab 恰好是 1.6.0，与 adapters/mjlab 钉的版本相同
> LEGGED_STUDIO_MJLAB_SOURCE=$PWD/00_resources/mjlab_new/mjlab \
>   python -m uvicorn backend.api_complete:app --host 127.0.0.1 --port 8766 --log-level warning
> # 再指驱动脚本：python tools/l7_first_run.py --robot <robot> --profile <profile> --port 8766
> ```
>
> 根治方式是把源码树固化进镜像层（或容器启动脚本设好该变量），登记在 A5。

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
| `LEGGED_STUDIO_MJLAB_SOURCE` | mjlab **源码树**（产品内训练 preflight 要求，镜像**未**固化 —— 见上方边界与 A5） |

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
| `headless-sim2sim-gate` | 包内声明策略全量的 CPU 无头验收（当前 47 条可执行），对照基线只拦**新增退化** |
| `cpu-training-smoke` | CPU 训练冒烟门禁：默认 16 envs × 5 iters 真实 PPO + 报告断言；**仅训练相关路径变更才触发**（`ifModify`，见 `.cnb.yml` 的 `.cpu-training-paths`） |
| `frontend-check` | web JS 语法 + vendor 资产冒烟 |

基线文件：`tools/baselines/sim2sim_headless_baseline.json`。
仓库现存 3 条既存失败（go2 特技/跑酷量化判据未过）已记录在基线里，
门禁只守「不许新增失败」。刷新基线：

```bash
python tools/sim2sim_headless.py --seconds 3 --write-baseline tools/baselines/sim2sim_headless_baseline.json
```
