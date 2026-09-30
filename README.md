# Legged Studio

**腿足机器人强化学习工作室** —— 一款把腿足机器人**从模型到实机的整条链路收进一个产品**的桌面 + 浏览器工作台：资产管理 → 模型检查与契约校准 → RL 训练 → 策略导出 → **基础仿真** → **高级仿真** → 部署打包，全程使用者不需要懂命令行。

产品对外是三种形态、**同一份后端能力**：桌面壳负责运行时供应与后端生命周期，Web 工作台是全部业务界面（含浏览器内 sim2sim），CLI 面向自动化与 CI；三者共用同一份接口契约（详见下文「整体架构」与「详细文档」）。

- 版本：`0.63.11`（见 `VERSION`；`pyproject.toml` / `package.json` 同源，核对命令见 `tools/doc_reality_check.py`）
- 许可：MIT
- 作者：zeitvex

---

## 它能做什么

| 环节 | 能力 |
|---|---|
| 资产管理 | 内置 8 个标准化机器人包（四足：宇树 Go1/Go2/B2、云深处 Lite3；轮足：云深处 M20、宇树 Go2W/B2W、自研 ZEX-W），统一契约描述；**2026-09-23 族架构收敛**：每族一套通用架构，非四足/轮足机型不再保留；随仓附带参考资源库 [`00_resources/`](00_resources/README.md)（按来源项目组织，含项目×机型矩阵与机型反查） |
| 模型检查 | URDF/MJCF 校验、3D 可视化检查器、契约合规校验 |
| RL 训练 | 通过隔离子进程调用 MJLab（MuJoCo Warp + PyTorch）训练后端，PPO / off-policy 算法，训练任务创建、监控、事件流；**族级 Kit + 通用装配**（2026-09-24~27）：同族机型共用一份技能实现（`adapters/mjlab/kits/{quadruped,wheel_leg}_kit/`），新机型 + 标准 MJCF 即可开训族级技能（装配表 `registry/families/*.json#skill_catalog` + 通用装配器 `adapters/mjlab/family_skill_builder.py`，验收器 `tools/validate_family_skill_assembly.py`）；训练资产由包声明（`robot_package.json` 的 `model.training_path`）；效果口径判据机器（`registry/effect_criterion.json` + `tools/effect_criterion.py`，同档同预算同度量） |
| 策略导出 | 导出 ONNX 部署策略，导出门禁（export gate）校验 |
| 基础仿真 | 浏览器内直接跑 MuJoCo WASM + ONNX Runtime Web（完全离线），播放包内声明的策略（加载即校验 ONNX metadata）；另有服务端无头基准/验收口径（`tools/sim2sim_headless.py` + baseline 门禁）作为同一件事的 CI 判据 |
| 高级仿真 | 在基础仿真之上叠加：传感器坞（里程/IMU/测距/深度/高度扫描/LiDAR/点云/RGB，可外挂）；Scenario（World × Mode × Sensors × CommandSource × Checks，浏览器与服务端跑**同一份**计划）；导航闭环（`?nav=<map>`，服务端 A*/Dijkstra 规划 + 浏览器跟随，到达判据单一真值 `registry/arrival_criteria.json`）；感知分层 A 类（`route=obs`，策略吃传感器）/ B 类（`route=external`，RL 只负责运动）。导航闭环**链路可用**（7 路线零链路缺陷；到达率瓶颈在策略侧，见 `00_know/05` §1.2 诚实边界） |
| 物理真值 / 契约校准 | 8 包 MJCF 由契约固化（`tools/bake_mjcf_physics.py`）+ 校验器守门（`tools/validate_mjcf_contract.py`）+ 族 MJCF 约定门禁（`tools/audit_family_mjcf.py`：规范化基准 + 逐台偏离登记，登记了又与实测一致也判红）；训练/验收/浏览器三方物理口径同源，"不许训一套跑另一套" |
| 部署 | 部署契约校验 + 部署包打包，衔接真机 sim2real |

---

## 整体架构

项目由四个严格隔离的层组成，核心原则是：**控制面永远不 import 训练栈（torch/mjlab）**，训练栈运行在独立 venv 子进程中，通过 JSON 协议通信。

```
┌────────────────────────────────────────────────────────────┐
│  Electron 桌面壳  (electron/launcher/)                      │
│  main.js ──IPC── preload.js ──contextBridge── renderer.js  │
│    │ 负责后端生命周期、端口、托盘、进度条、运行时下载          │
└────┼───────────────────────────────────────────────────────┘
     │ spawn: python -m uvicorn backend.api_complete:app
     ▼ HTTP 127.0.0.1:8765
┌────────────────────────────────────────────────────────────┐
│  FastAPI 控制面  (backend/api_complete.py)                  │
│  ├─ /web/*      静态挂载 ──► web/ 工作台 SPA + sim2sim      │
│  ├─ /api/training/*  训练任务编排 ──► training_manager.py   │
│  ├─ /api/{export,deploy,evaluation,simulation,navigation,   │
│  │   terrain,models,pretrained,health,project,settings,     │
│  │   perception,map_editor}                                 │
│  └─ 中间件：COOP/COEP（启用 SharedArrayBuffer）、MIME 修正   │
└────┼──────────────────┬───────────────────┬────────────────┘
     │ import           │ import            │ spawn 隔离 venv 子进程
┌────▼─────────┐  ┌─────▼───────┐   ┌───────▼───────────────────┐
│ contracts/   │  │ assets/     │   │ adapters/mjlab/ worker     │
│ 数据契约      │  │ robots/     │   │ MJLab + torch(cu128/cpu)   │
│ Schema/校验/ │  │ 8 机器人包   │   │ PPO / off-policy           │
│ 角色解析      │  │ + 资产清单   │   │ ──► ONNX 导出              │
│ （零依赖）    │  └─────────────┘   └───────┬───────────────────┘
└──────────────┘                            │ policy.onnx + 部署元数据
                                            ▼
                        web/sim2sim（基础仿真 / 高级仿真）
                        ──► deploy_pack 部署包 ──► 真机
```

**数据流主线**：机器人包（`assets/robots` + contract v3）→ 工作台检查与参数校准（电机参数卡 / 契约固化与校验）→ 训练创建（training API → training_manager → mjlab launcher → 隔离 worker）→ ONNX 导出（export gate 校验）→ **基础仿真**（浏览器 sim2sim + 无头基准/验收）→ **高级仿真**（传感器坞 + Scenario：地图/航点 + `CommandSource: planner\|perception` + 到达判据，`/api/navigation/plan` 装配、浏览器跟随）→ 部署包打包。

---

## 目录结构

```
legged_studio/
├── electron/launcher/     # Electron 桌面壳（主进程 + preload + 启动器 UI）
├── backend/               # FastAPI 控制面（纯控制面，不含训练栈）
│   ├── training/          # 训练 API 子包（create/monitor/artifacts/events/schema）
│   ├── terrain_gen/       # 地形生成（MJCF XML 输出）
│   ├── *_api.py           # deploy/export/evaluation/navigation/terrain 等路由
│   └── package_*.py       # 机器人包与模型准入的领域服务（索引/同步/记录/准入，路由只做薄壳）
├── contracts/             # 稳定数据契约（JSON Schema + Pydantic 模型，零仿真依赖）
├── adapters/              # 训练后端插件层
│   └── mjlab/             # 当前唯一实现：MJLab 训练后端（隔离 venv）
├── assets/robots/         # 8 个标准化机器人包（契约 + MJCF/URDF + 训练配置；2026-09-23 族架构收敛）
├── web/                   # 纯静态前端（无构建），由 FastAPI 挂载到 /web
│   └── sim2sim/           # 浏览器内 sim2sim（MuJoCo WASM + ONNX Runtime Web）
├── scripts/               # 启动器、CLI、Windows 运行时下载与打包脚本
├── tools/                 # 离线工具链（URDF 校验/转 MJCF、策略转换、契约代码生成、移植准入审计）
├── packaging/             # electron-builder 两种发行变体配置
├── docs/                  # 产品文档（桌面程序 / Web 程序）
├── 00_know/               # 知识库与决策文档（定位 / 规划 / 参考项目 / 参数标准 / 任务清单 / 统一架构方案）→ 00_know/README.md
└── 00_resources/          # 参考资源库（按来源项目组织的只读底座）→ 00_resources/README.md
```

> `00_` 前缀 = **资料类目录**（非运行时加载）：`00_know/` 是"为什么这么做"，
> `00_resources/` 是"依据在哪"，两者都不参与打包，也不被 `backend/` 直接 import。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 桌面壳 | Electron 28 + electron-builder 24（Windows portable / Linux AppImage） |
| 后端控制面 | Python 3.12（钉死）+ FastAPI + Uvicorn + Pydantic v2 + MuJoCo 3.11.0，uv 管理依赖 |
| 训练后端（隔离） | MJLab 1.6.0（MuJoCo Warp）+ PyTorch（cu128/cpu）+ BAM 执行器模型 |
| Web 前端 | 纯 HTML/CSS/ES Module JS，无构建步骤；Three.js 本地 vendor |
| 浏览器 sim2sim | MuJoCo WASM（pthread）+ ONNX Runtime Web 1.23.2 + Three.js，全部离线 vendor |
| 数据契约 | JSON Schema ×8 + 生成的 Pydantic 模型 |
| 资产准入 | 移植准入审计（训练/仿真须有 00_resources 上游训练源码佐证，包自包含与策略↔onnx 一致性检查），见 `tools/audit_porting_admission.py` |
| CI | 腾讯云 CNB：Python 语法、契约漂移检查、单测（backend 全量 139 模块）、openapi 契约冒烟、无头 CPU sim2sim 基线门禁、移植准入审计、Capability Pack 校验、**族架构审计**（`audit_families` + 族 MJCF 约定 + 逐档案上游参考对照）、**文档数字对账**、前端 vendor 冒烟 |
| 云原生开发 | **CNB 默认镜像** + `.cnb.yml` 的 `vscode` 事件，一键起环境（依赖与 **mjlab CPU 训练栈**在启动阶段按需供应，浏览器 sim2sim 开箱可用）→ `docs/cloud-dev.md` |
| 开发期 MCP | `.cnb/mcp/servers.json` 11 条（通用 6 + 机器人专用 5）+ `tools/mcp/` 4 个自研 server（契约 / MuJoCo / onnx / 资源库，零新增依赖）→ `.cnb/mcp/README.md` |

---

## 快速开始

### 环境要求

- Node.js（Electron 28）
- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- Windows 10/11（主开发平台）或 Linux
- **正式训练建议 NVIDIA GPU**（MJLab 上游要求 GPU）；无独显时可用 **CPU profile** 完成仿真与最小训练冒烟——训练栈的 `device: auto` 会自动回退 CPU，但 CPU 吞吐低约一个量级。启动器「配置环境 · 计算设备」可在 GPU/CPU profile 间切换，**CPU 配置长期保留**

### 开发模式

```powershell
# 安装依赖
npm install
uv sync

# 一键启动（Electron 桌面壳，自动拉起后端）
npm start
# 或 Windows 双击
start.bat
```

启动后自动打开桌面启动器，后端就绪后进入工作台 `http://127.0.0.1:8765/web/workbench.html`。

### 云原生开发（免配置在线环境）

仓库页面点 **「Legged Studio 开发」** 即进入在线环境（**CNB 默认镜像**，自带 WebIDE 与
CodeBuddy），依赖、Chromium 与 **CPU 训练栈**在环境启动时按需供应（幂等短路复用），
后端自动在 `0.0.0.0:8765` 起来，浏览器 sim2sim 可直接看、可直接截图调试；
环境还会打印 **MCP 工具链**配置路径。
详见 [`docs/cloud-dev.md`](docs/cloud-dev.md)。

### 发布（自动上传 GitHub）

`main` 的 push 会把分支与 tag **镜像到 GitHub**（逐 sha 比对，无变更即跳过）；
**当前唯一开发分支是 `feat/family-arch`**（2026-09-24 起的族架构主线；`main` 保留收敛前的逐机型思路，两线不合并——2026-09-28 用户裁决）；
`v*` 的 tag_push 还会在**本仓与 GitHub 两侧**各建一个 Release。凭据只从密钥仓库
[`zeitvex/github-secrets`](https://cnb.cool/zeitvex/github-secrets/-/blob/main/github-secrets.yaml)
经 `imports` 注入，不落工作区文件；执行体是
[`adapters/github/mirror.py`](adapters/github/mirror.py)（只用标准库）。
手动演练 `python -m adapters.github.mirror --check`，详见 [`docs/cloud-dev.md`](docs/cloud-dev.md)。

### CPU 训练链路（无 GPU 也能跑真训练）

mjlab 官方支持 CPU（`cpu` extra），本仓库把它接成完整链路：容器/本地进环境即可训练，
不需要 GPU 额度。

```bash
# 训练栈自检 + 16 envs × 5 iters 真实 PPO + 报告断言
# （规模可用 SMOKE_NUM_ENVS / SMOKE_ITERS 覆盖，默认档只守"回路通不通"）
bash scripts/cpu_training_smoke_gate.sh

# 需要重新供应训练 venv 时（幂等）
bash scripts/provision_cpu_training.sh
```

训练栈落点集中在 `contracts/path_bootstrap.py`（`LEGGED_STUDIO_MJLAB_VENV` 可覆盖），
体检 L0 给出三态：`cuda`（正式训练）/ `cpu-only`（仿真与冒烟）/ `unavailable`（先供应环境）。

**CPU 冒烟的实测包络（2026-09-22 实测，别拿它当 GPU 用）**：门禁默认档（16×5）单 profile
**≈23 s**；`tools/validate_training_smoke.py --robot unitree_go2 --mode train --num-envs 16
--iters 5` 跑**全 18 个 go2 profile**（含 jump/backflip/dreamwaq/cts/ts/him/parkour 与蒸馏
runner）**7:55，18 ok / 0 skipped / 0 failed**；128×20 **6:13**（≈18 s/iter，CPU 随 envs
近似线性）。⇒ **能干的**：回路验证与**移植冒烟**（改完能建 env、能跑 PPO、reward 有限、
`time_outs` 已接线）；**干不了的**：1024–2048×250 质量档（线性外推是小时级，仍需 GPU）。

### 测试

```powershell
npm test           # 后端 unittest（控制面纯逻辑测试，全量 139 个 test_*.py）
npm run test:obs   # 浏览器观测构建器的 node 单测
npm run check:docs # 文档数字 vs 仓库实测对账（版本号/包数/策略数/资源库项目数）
```

浏览器 E2E（确定性回放 + 截图，需要 Playwright）：

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt
playwright install chromium
pytest tests/e2e -v
```

无头 CPU sim2sim 验收（包内声明的策略全量，当前 42 条可执行，对照基线只拦新增退化）：

```bash
python tools/sim2sim_headless.py --seconds 3 \
  --baseline tools/baselines/sim2sim_headless_baseline.json
```

CPU 训练冒烟门禁（默认 16 envs × 5 iters 真实 PPO，需已供应训练栈）：

```bash
bash scripts/cpu_training_smoke_gate.sh
```

### 打包发行

```powershell
npm run build:portable            # Windows portable（在线下载运行时）
npm run build:online:win          # 完整打包 + 校验
npm run build:portable:embedded   # 内嵌运行时版（完全离线）
npm run build:linux               # Linux AppImage
```

---

## 参考资源库（`00_resources/`）

以**来源项目为单位**的原始资源取证库，作为 `assets/robots/` 归一化资产包的上游证据底座
（一个来源项目 = 一个目录 `00_resources/<project>/`，原样保留该项目的目录结构与组织思想）：

| 处置 | 内容 |
|---|---|
| 保留 | 源码 / 配置 / 文档 / 数据 / URDF·xacro·MJCF / **推理策略文件（.onnx·.pt·.pth·.engine·.ckpt·.safetensors）** |
| 省略 | 3D 网格与 CAD、点云与 ROS 录包、归档、可执行库与二进制、图像/音视频/字体、日志、>20MB 大文件 |
| 占位 | 被省略文件在**原目录**留 `_OMITTED.md`（文件名 / 体积 / 类型 / 源路径），需要时按源路径回 `00_open/` 取用 |
| 索引 | 根 `README.md`（项目清单 · 项目×机型矩阵 · 机型反查）＋ 各项目 `README.md`（有什么 · 能帮什么 · 关联机型）＋ `_index.json` |

- 定位：**只读参考底座**，`00_resources/<project>/<rel>` 与 `00_open/<project>/<rel>` 逐级对应（不做适配）；
  `assets/robots/<id>/` 才是按 contract v3 收敛后的可执行版本，两者机型 ID 一一对应但不可混用。
- 机型归属通过索引表达（项目 README + 机型反查表），**不再按机型复制多份**。
- 同步脚本：[`tools/sync_resources.py`](tools/sync_resources.py)（`--clean` / `--only <project>` / `--dry-run` / `--kb-only`）。
- 规范与索引：[`00_resources/README.md`](00_resources/README.md) ｜ [`00_resources/_SPEC.md`](00_resources/_SPEC.md)

---

## 详细文档

**产品文档**（面向使用者）：

- [桌面程序（Electron 启动器）](docs/desktop-app.md) —— 桌面壳架构、后端生命周期管理、IPC 接口、运行时供应、打包发行
- [Web 程序（工作台 + sim2sim）](docs/web-app.md) —— FastAPI 路由结构、工作台页面、浏览器内 sim2sim 验证器、API 一览

**知识库与决策文档**（面向维护者，索引见 [`00_know/README.md`](00_know/README.md)）：

- [知识库索引](00_know/README.md) —— 6 份关键文档的导航 + 阅读路径 + 归档说明
- [项目定位](00_know/01_项目定位.md) —— 为什么做 / 给谁做 / 做成什么 / 哪里不做 + **定位裁决块**（主叙事 / 第一用户 / 生态姿态 / 3–6 月锚点）
- [项目规划](00_know/02_项目规划.md) —— 怎么落地（上游对齐、功能地图、四层架构、模块与路径、关键流程、门禁、阶段计划、指标）
- [参考项目与资源](00_know/03_参考项目与资源.md) —— 官方源克隆清单、跨源对照方法、MJCF 字段级差异、高级仿真切片
- [参数真值标准](00_know/04_参数真值标准.md) —— 每个参数只有一个家；现役 8 机型来源对照与选定规则（已删 6 机型对照保留作历史）
- [任务清单](00_know/05_任务清单.md) —— 现在什么状态 + 下一步做什么（现状锚点 + 主战场队列 + 活跃与挂账 + DoD；**2026-09-28 重排后只含活清单**，历史 166 行与进度流水在归档 08/09）
- [统一架构方案](00_know/06_统一架构方案.md) —— 系统一页架构 + 统一什么 / 不统一什么 / 为什么（族架构设计与实证、教程锚点表）
- [参考资源库](00_resources/README.md) —— 按来源项目组织的参考资源、项目 × 机型矩阵与省略登记
- 历史文档（已归档，只读）：[`00_know/90_归档/`](00_know/90_归档/) —— 参考项目评估、调研盘点、B 系列专题报告、重构方案 + **任务清单历史（08 阶段桶与队列 / 09 进度流水，2026-09-28 移入）**

---

## 设计要点

1. **分层隔离**：contracts（零依赖）→ 控制面（轻量 FastAPI）→ 训练栈（隔离 venv 子进程）→ 浏览器验证（WASM），训练栈崩溃不影响控制面。
2. **契约驱动**：机器人、策略产物、部署、训练配置全部由 `contracts/` 下的 JSON Schema 定义，全项目单一事实源，CI 有契约漂移检查。
3. **插件化训练后端**：`adapters/backend_adapter.py` 定义 `BackendAdapter` Protocol（env/runner/exporter 三入口），可扩展接入 IsaacGym / UniLab / RoboLab 等其他训练栈。
4. **完全离线闭环**：浏览器 sim2sim 的 MuJoCo WASM、ONNX Runtime、Three.js 全部本地 vendor，训练 → 导出 → 验证全流程无需联网。
5. **多输入 / 递归策略的部署契约**：本体观测之外的外部输入（历史缓冲、深度、命令、递归隐状态、episode 首帧标志）在**包内契约 `aux_inputs` 里逐项声明**（名 / 形状 / `produced_by` 来源），验收器与浏览器按声明喂入、按声明回传；遇到**导出器命名不可依赖**的产物（如 mjswan 的 `l_kwargs_*`）改按**位置槽表**映射（`contract.onnx_slots`），张量名一律不作为语义。
