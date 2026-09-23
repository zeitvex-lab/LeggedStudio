# 云原生开发环境

点仓库页面的 **「Legged Studio 开发」** 按钮，即可获得一个开箱即用的在线开发环境：

- 镜像 = **CNB 默认镜像 `cnbcool/default-dev-env`**（`.cnb.yml` 里不写 `docker.image` /
  `docker.build`）。平台侧维护，自带 code-server（单容器模式）、CodeBuddy Web
  与 WebIDE 的 CodeBuddy 插件、Python 3.12、Node 22、uv、git-lfs、zsh、cnb-cli；
- 控制面依赖（`backend/requirements.txt` + `onnxruntime`）与 **CPU 训练 venv**
  由启动阶段按需供应（**import 探测幂等**，第二次进环境短路成秒级校验）；
- Playwright Chromium 按版本标记对齐（版本随 `playwright` 包自动对齐，不合就重装），
  浏览器 sim2sim 可直接看、可直接截图；
- **CPU 训练链路进环境即可用**：mjlab 的 `cpu` extra 装在仓库外的隔离 venv
  （`/opt/legged-studio/mjlab-cpu/.venv`）；
- 后端在 `0.0.0.0:8765` 自动拉起。

> **为什么不再自建镜像**（2026-09-22 决定，见 issue #44）：根 `Dockerfile` 那份自建镜像
> 是**一长串问题的来源**——code-server 装不进去就退回双容器模式（终端停在「连接到 CNB
> 容器中...」）、CodeBuddy 插件不再自动注入（右键没有 AI 助手）、基础镜像 apt 包名随
> 发行版迁移（bookworm→noble 已踩过一次）、改一次 `by` 清单就整体重建。
> 换成平台默认镜像后这些面直接消失，代价只有"进环境时供应一次依赖"。

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
.cnb.yml  （无 docker.build）     # 开发环境镜像=默认镜像；依赖在启动阶段供应
.cnb.yml  .dev-env-bootstrap     # 依赖供应：控制面 pip 包 + libosmesa + 训练 venv（CI/开发共用锚点）
.cnb.yml  syntax-check           # CI 语法门禁：不装 pip 包，独立 pipeline，与单测并发
.cnb.yml  .main-env              # CI 单测/审计门禁：python:3.12 底座 + 现装依赖
.cnb.yml  $: vscode              # 启动流程：供应依赖 + 自检 + 起后端 + 打印预览地址
.cnb/settings.yml                # 入口按钮名称 / CPU 核数 / 自动打开 WebIDE
.cnb/mcp/servers.json            # 开发期 MCP 工具链（11 条，见 .cnb/mcp/README.md）
tools/mcp/                       # 4 个自研 MCP server（契约 / MuJoCo / onnx / 资源库）
adapters/github/mirror.py        # 发布：自动上传 GitHub（分支 / 标签 / Release，逐 sha 幂等）
.cnb.yml  .github-mirror         # 该同步的流水线锚点（main.push + main.tag_push）
scripts/provision_cpu_training.sh  # CPU 训练 venv 供应（CI 与本地同一脚本）
scripts/cpu_training_smoke_gate.sh # CPU 训练冒烟门禁（CI 与本地同一命令）
```

### 镜像与依赖来源

镜像就是 **CNB 默认镜像**（`cnbcool/default-dev-env`）—— `.cnb.yml` 里**没有任何**
`docker.image` / `docker.build` 声明，平台兜底即默认镜像：

- 自带 code-server + ssh → **单容器模式**（WebIDE 直连开发容器，终端不会卡在
  「连接到 CNB 容器中...」）；
- 自带 CodeBuddy Web 入口与 WebIDE 的 CodeBuddy 插件（`Tencent-Cloud.coding-copilot`），
  **无需**再手工补装；
- Python 3.12（uv 提供）、Node 22、`uv`、`git-lfs`、`zsh`、`cnb-cli`、`skills` 齐备。

Python 版本要求（`pyproject.toml` 的 `>=3.12,<3.13` 与 `/api/system/environment` 的
`python_target_match`）由默认镜像的 3.12 满足；镜像里 `python` 与 `python3` 都指向 3.12。

**不固化的东西**（都改由启动阶段供应，见下节）：

| 依赖 | 供应方式 | 复用 |
|---|---|---|
| 控制面（`backend/requirements.txt` + `httpx`/`onnx`/`onnxruntime`） | `pip install --break-system-packages` | import 探测幂等（已装即短路） |
| CPU 训练 venv（mjlab cpu extra） | `scripts/provision_cpu_training.sh`（幂等） | 落在 `/opt/...`（仓库外，不被 bind mount 覆盖） |
| Playwright Chromium | `playwright install --with-deps chromium` | 版本标记文件（不合则重装） |
| 离屏渲染软件 GL（`libosmesa6`） | `apt-get install`（尽力而为，失败不判红） | —— |

### 启动阶段做了什么

`.cnb.yml` 的 `vscode` 段有三个 stage：

1. `dev-env-bootstrap` — 供应控制面依赖、Chromium、训练 venv（**全部幂等**）；
2. `assert-default-env` — 自检默认镜像的关键能力：`code-server` 必须存在（否则会退回
   双容器模式，直接判失败）；`codebuddy` / CodeBuddy 插件 / `uv` / `git-lfs` 缺失只告警；
3. `start-control-plane` — 起后端、打印预览地址与 MCP 自检结果。

依赖供应与 CI 共用同一个锚点（`.dev-env-bootstrap`），因此
「开发环境里能跑通的」和「CI 里跑的」仍是同一套依赖，不会出现环境漂移。

### 发布：自动上传 GitHub（镜像）

本仓（CNB）是开发主仓，GitHub 侧保留一份**可直接克隆**的公开副本。同步由流水线自动完成：

| 事件 | 做什么 |
|---|---|
| `main` 的 **push** | 把 `main` 与本地 tag 镜像到 GitHub（**逐 sha 比对，无变更即跳过**） |
| `v*` 的 **tag_push** | 同上 + 在**本仓与 GitHub 两侧**各建一个 Release |

- 触发配置：`.cnb.yml` 的 `.github-mirror` 锚点（`main.push` 与 `main.tag_push` 各挂一次）；
- 执行体：[`adapters/github/mirror.py`](../adapters/github/mirror.py) —— **只用标准库**
  （`urllib` + git CLI），所以"上传失败"里不会混进"依赖装不上"两种原因；
- 凭据：`imports` 引**密钥仓库** [`zeitvex/github-secrets`](https://cnb.cool/zeitvex/github-secrets/-/blob/main/github-secrets.yaml)，
  只以环境变量形式注入，不落到工作区文件；`GITHUB_TOKEN` 仅经 `http.extraheader` 传给 git
  （不进 `.git/config`、不进 argv），输出侧一律脱敏。

```yaml
# github-secrets.yaml（密钥仓库里，Web 界面编辑）
GITHUB_USER: "your-github-username"
GITHUB_TOKEN: "ghp_xxxxxxxxxxxxxxxxxxxx"
# 可选：镜像到别的仓库（缺省 = $GITHUB_USER/LeggedStudio）
# GITHUB_REPO: "owner/repo"
# 可选：镜像分支白名单，逗号分隔（缺省 = main）
# GITHUB_MIRROR_BRANCHES: "main,release/v1.0"
```

**边界（如实声明）**：只覆盖 git 层（commit / branch / tag / Release 说明）；GitHub 侧的
仓库设置、Actions、Issues、LFS 大文件**不在范围内**。空仓库会被拒绝（`git push` 对空仓会把
远端默认分支设成第一个被推的分支）。**没配密钥不算失败**：脚本打印 `SKIPPED` 并 exit 0 ——
本地与 PR 上本来就拿不到密钥（`imports` 只对 `push` / `tag_push` 生效），判据是"配了就同步"。

手动演练（不写任何东西）：

```bash
python -m adapters.github.mirror --check     # 只报告会同步哪些 ref
python -m unittest adapters.github.test_github_mirror    # 14 项契约测试
```

### MCP 工具链（开发期，不预装本体）

默认镜像已提供 `npx` / `uvx` 两个 runner，本项目**不预装各 MCP server 本体**
（它们是按需拉取的开发期工具，固化进环境会让"控制面依赖"和"工具链"两个关注点耦合）。
清单与选型理由见 [`../.cnb/mcp/README.md`](../.cnb/mcp/README.md)，共 11 条：

- 通用系 6：`filesystem` / `git` / `github` / `fetch` / `playwright` / `sqlite`
  （其中 `playwright` 最刚需——本仓所有 sim2sim 结论都是浏览器实测得出的）；
- 机器人专用系 5：`tensorboard` + 4 个**自研** server
  （`mujoco` / `onnx` / `resources` / `contracts`，实现在 `tools/mcp/`）。

自研 server 只用 `mujoco` / `onnxruntime` / 标准库，**不增依赖**，因此
`backend/requirements.txt` 无需改动（`mujoco` / `onnxruntime` 已在其中）。自检：

```bash
python -m unittest backend.test_mcp_servers -v          # 声明 + 4 个 server 自检 + 真调用
python -m tools.mcp.contracts_server --selftest         # 单条 server 的工具表
python -m tools.mcp.contracts_server                    # stdio 起服务（JSON-RPC）
```

MCP 只装 `npx` / `uvx` runner，server 本体按需拉取；这与"控制面依赖在启动阶段供应"的分工一致。

### WebIDE 里的 CodeBuddy（AI 助手）从哪来

**默认镜像自带的**，不需要仓库做任何事：

| 入口 | 依赖 | 表现 |
|---|---|---|
| CodeBuddy Web | 镜像内有 `codebuddy` 命令（>= 2.137.0） | 云开发入口页多一个浏览器入口 |
| CodeBuddy IDE 插件 | 镜像预装 open-vsx 扩展 `Tencent-Cloud.coding-copilot` | WebIDE 编辑器内可用，有右键 AI 助手 |

> 历史坑（已随自建镜像一起退场）：改用自定义根 `Dockerfile` 后，默认镜像里的这份
> 预装**不会自动注入**，表现为「插件没了、右键没有 AI 助手」。当时的修法是自己在
> Dockerfile 里 `code-server --install-extension`。现在回到默认镜像，问题面不复存在。
> 启动期自检仍会打印两者状态（插件缺失只告警不失败）。

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

> **口径边界（2026-09-16 收口，见任务清单 A5）**：冒烟门禁能跑 ⇒ **产品内**训练路径也能跑，
> 两者现在同口径。曾经的落差与修法值得留档：`/api/training/create` 的就绪判据一度是
> `exists ∧ manager_env_available ∧ runtime.available`（前两项描述 **mjlab 源码 checkout**），
> 而镜像只固化了训练 venv、没有 `vendor/mjlab`，于是容器内点"开始训练"恒
> **501 `native MJLab adapter is not ready`**。
>
> 根因不是"缺源码树"而是**判据过严**：`mjlab==1.6.0` 是 `adapters/mjlab/pyproject.toml`
> 钉住的依赖（PyPI 装进隔离 venv），**源码树只是可选遮蔽层**（开发 checkout 覆盖已安装版本），
> `native_worker` 对它也只是 `_ensure_on_path(source/"src")`（路径不存在即 no-op）。
> 现在就绪判据以**运行时探测为唯一硬证据**，报告里给出 `source_mode`：
>
> | `source_mode` | 含义 | 就绪 |
> |---|---|---|
> | `checkout` | 源码树完整（`src/mjlab/envs/manager_based_rl_env.py` + `src/mjlab/rl/runner.py`） | ✓ |
> | `installed_package` | **没有**源码树，用已安装的 mjlab 发行版（容器/服务端常态） | ✓ |
> | `checkout_incomplete` | 源码树存在但残缺 —— 会遮蔽已安装版本，比"没有"更危险 | ✗ fail-closed |
> | `unavailable` | 候选解释器都装不出 torch/mjlab（真依赖缺失） | ✗ fail-closed |
>
> 因此容器内**不需要任何环境变量**即可训练；`LEGGED_STUDIO_MJLAB_SOURCE` 仍可用（见下表），
> 只是从"必需"降为"可选覆盖"。

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
| `LEGGED_STUDIO_MJLAB_SOURCE` | mjlab **源码树**（**可选**遮蔽层：不设则用 venv 里已安装的发行版；残缺的 checkout 会被判未就绪，见上方边界与 A5） |

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

云原生开发与云原生构建底层是同一套引擎，这里共用**默认镜像 + 同一个依赖供应锚点**
（`.cnb.yml` 的 `.dev-env-bootstrap`），所以「开发环境里能跑通的」和「CI 里跑的」
是同一套依赖，不会出现环境漂移。

差别只在缓存：开发环境依赖装一次后靠**幂等短路**复用（第二次进环境是秒级校验）；
CI runner 每次现装（换来的是依赖版本零漂移 —— 改了 `requirements.txt` 立刻生效，
不存在"镜像层还是旧依赖"的滞后）。

> 云开发**不声明 `docker.volumes`**：该字段在流水线里合法，但在 `vscode` 事件下平台
> 会拒绝（`不允许的字段 "docker.volumes"`）。缓存复用改由平台节点卷 + 幂等供应共同保证。

### CI 结构：按「依赖形态」拆成三段，互不拖累

历史上 `push` 只有一条 `backend-test`，里面把 `syntax-check`（零依赖）和 `unit-tests`
（要 pip 装 20+ 包）**串在同一个 python:3.12 容器**里 —— 短门禁必须等长门禁的容器
准备与依赖安装。现在按「这一步到底需要什么」拆开：

| Pipeline | 镜像 | 规模 | 内容 |
|---|---|---|---|
| `syntax-check` | `python:3.12` | 平台默认（不声明 `cpus` ⇒ 8 核 / 16 GiB） | `py_compile` + 契约产物漂移；**不装任何 pip 包** |
| `backend-test` / `backend-test-pr` | `python:3.12` | 平台默认 | 单测、**openapi 契约冒烟**、移植准入、Pack 校验、全部审计工具 |
| `cpu-training-smoke`（+PR 侧） | 默认 runner + `dev-env-bootstrap` 供应 | 平台默认 | CPU 训练冒烟：16 envs × 5 iters 真实 PPO + 报告断言；**仅训练相关路径变更才触发**（`ifModify`，见 `.cpu-training-paths`） |
| `headless-sim2sim-gate` | 默认 runner + `dev-env-bootstrap` 供应 | 平台默认 | 包内声明策略全量的 CPU 无头验收（当前 42 条可执行），对照基线只拦**新增退化** |
| `frontend-check` | `node:20` | 平台默认 | web JS 语法 + vendor 资产冒烟 |

三条要点：

- **`syntax-check` 单独成 pipeline，与 `backend-test` 并发**：此前语法检查与单测串在
  同一个容器里，短门禁要等长门禁的容器与依赖。拆开后 push 的墙钟 ≈
  `max(syntax, unit-tests)`，而不是两者串行相加（单测仍是长板）。
- **默认 CI runner 没有 python**（实测 `python` / `python3` 均 127）—— 除依赖由
  `.dev-env-bootstrap` 现装的 `cpu-training-smoke` / `headless-sim2sim-gate` 外，
  凡要跑 Python 的 job 都必须显式声明 `docker.image: python:3.12`。该镜像与云原生
  开发的默认镜像同版，但只作**运行底座**：依赖仍在 stage 里现装，因此不引入
  「镜像层里是旧依赖」的漂移面。
- **`runner.cpus` 与配额**：**配置里一律不声明 `runner.cpus`**，吃平台默认
  （`cnb:arch:amd64` ⇒ 8 核 / 16 GiB；内存由固定公式 `cpus × 2 GB` 推导，没有独立
  `memory` 字段）。要注意「不声明」不等于「不花额度」：构建的 Prepare 阶段按
  `cpus × 5min` 从根组织**预冻结**核时，8 核 = 0.67 核时/次，额度不足就直接驳回，
  **与依赖装不装得上无关**（报错落点却会指向 stage 链第一段）。
  2026-09-22 期间曾因根组织额度见底把 `cpus` 一路降到平台下限 1 核，随后已整段回退
  ——那是为躲临时额度设的地板价，不是任何门禁的真实需求，1 核会让单测 / 训练冒烟 /
  无头验收这些吃 CPU 的 stage 变成明显的长板。
  若再遇到 `insufficient for pre-freezing`：**先找根组织管理员提额**，不要又把降核
  当常规手段（降核 + 串行都试过，1 核仍被驳，见 PR #47/#48）。

> 网络与 `apt`：`syntax-check` 不装依赖；`backend-test` 与 `cpu-training-smoke`
> 仍各自 `apt-get install libosmesa6`（best-effort，装不上只影响渲染用例，会 self-skip）。
> 改成 `docker.build` 预装能省这几秒，但会把依赖重新固回镜像层，与本仓「默认镜像 +
> 启动时供应」的方向相悖，故保持现状。

基线文件：`tools/baselines/sim2sim_headless_baseline.json`。
仓库现存 3 条既存失败（go2 特技/跑酷量化判据未过）已记录在基线里，
门禁只守「不许新增失败」。刷新基线：

```bash
python tools/sim2sim_headless.py --seconds 3 --write-baseline tools/baselines/sim2sim_headless_baseline.json
```
