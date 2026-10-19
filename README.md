# Legged Studio

**腿足机器人强化学习工作室** —— 一款把腿足机器人**从模型到实机的整条链路收进一个产品**的桌面 + 浏览器工作台：资产管理 → 模型检查与契约校准 → RL 训练 → 策略导出 → **基础仿真** → **高级仿真** → 部署打包，全程使用者不需要懂命令行。

产品对外是三种形态、**同一份后端能力**：桌面壳负责运行时供应与后端生命周期，Web 工作台是全部业务界面（含浏览器内 sim2sim），CLI 面向自动化与 CI；三者共用同一份接口契约。

- 版本：`0.67.0`（见 `VERSION`；`pyproject.toml` / `package.json` 同源，核对命令见 `tools/doc_reality_check.py`）
- 许可：**AGPL-3.0-only**（项目代码）；`00_resources/` 各项目保留原始许可
- 作者：zeitvex

---

## 它能做什么

| 环节 | 能力 |
|---|---|
| 资产管理 | 内置 8 个标准化机器人包（四足：宇树 Go1/Go2/B2、云深处 Lite3；轮足：云深处 M20、宇树 Go2W/B2W、自研 ZEX-W），统一契约描述；同族机型共用族 Kit 与技能装配，成员由 `morphology.id` 派生；随仓附带参考资源索引（实体在独立仓，按需拉取） |
| 模型检查与契约 | URDF/MJCF 校验、3D 可视化检查、契约 v3 合规校验、物理固化与校验（`bake_mjcf_physics` / `validate_mjcf_contract`）、族 MJCF 约定门禁 |
| RL 训练 | 隔离子进程调用 MJLab（MuJoCo Warp + PyTorch）；PPO 为默认基线，CTS / AMP / DreamWaQ / HIM / HORA / distill / APPO 以算法插件接入；族 Kit + profile 数据 + 通用装配，新机型 + 标准 MJCF 即可开训；训练任务创建、监控、事件流与复现信息 |
| 策略导出与验收 | 导出 ONNX 部署策略与部署契约；export gate；无头 sim2sim、确定性回放、效果口径（`effect_criterion`） |
| 基础仿真 | 浏览器内直接跑 MuJoCo WASM + ONNX Runtime Web（完全离线），加载即校验 ONNX metadata；服务端无头基准/验收作为同一件事的 CI 判据 |
| 高级仿真 / 任务层 | 传感器坞（里程/IMU/测距/深度/高度扫描/LiDAR/点云/RGB）；Scenario（World × Mode × Sensors × CommandSource × Checks）；导航闭环；感知分层 A 类（策略吃传感器）/ B 类（盲狗 + 外挂决策）。e2e 快进回路当前 7/7 到达；真机实时表现不外推 |
| 部署 | 部署契约校验 + 部署包打包，衔接真机 sim2real |

---

## 整体架构

项目由四个严格隔离的层组成，核心原则是：**控制面永远不 import 训练栈（torch/mjlab）**，训练栈运行在独立 venv 子进程中，通过 JSON 协议通信。

```
┌────────────────────────────────────────────────────────────┐
│  Electron 桌面壳  (electron/launcher/)                      │
│  后端生命周期 / 端口 / 托盘 / 运行时下载                     │
└────┼───────────────────────────────────────────────────────┘
     │ spawn: python -m uvicorn backend.api_complete:app
     ▼ HTTP 127.0.0.1:8765
┌────────────────────────────────────────────────────────────┐
│  FastAPI 控制面  (backend/api_complete.py)                  │
│  /web/* 静态挂载 · /api/{training,export,deploy,evaluation, │
│  simulation,navigation,terrain,models,pretrained,health,...}│
└────┼──────────────────┬───────────────────┬────────────────┘
     │ import           │ import            │ spawn 隔离 venv
┌────▼─────────┐  ┌─────▼───────┐   ┌───────▼───────────────────┐
│ contracts/   │  │ assets/     │   │ adapters/mjlab/ worker     │
│ 数据契约      │  │ 8 机器人包   │   │ MJLab + torch(cu128/cpu)   │
│ Schema/校验   │  │ + 资产清单   │   │ PPO + 算法插件             │
└──────────────┘  └─────────────┘   └───────┬───────────────────┘
                                            │ policy.onnx + 部署契约
                                            ▼
                        web/sim2sim（基础仿真 / 高级仿真）
                        ──► deploy_pack 部署包 ──► 真机
```

**数据流主线**：机器人包（`assets/robots` + contract v3）→ 工作台检查与参数校准 → 训练创建（training API → training_manager → mjlab launcher → 隔离 worker）→ ONNX 导出与导出门禁 → 基础仿真（浏览器 sim2sim + 无头基准）→ 高级仿真（传感器坞 + Scenario + 导航）→ 部署包。

---

## 目录结构

```
legged_studio/
├── electron/launcher/     # Electron 桌面壳
├── backend/               # FastAPI 控制面（不含训练栈）
│   ├── training/          # 训练 API 子包
│   └── *_api.py           # deploy/export/evaluation/navigation/terrain 等路由
├── contracts/             # 稳定数据契约（JSON Schema + Pydantic，零仿真依赖）
├── plugins/               # 插件内核（服务上下文 / 事件 / patch）
├── registry/              # 声明式注册表（plugin-registry.json：13 seam + panel 清单）
├── adapters/              # 训练后端插件层
│   └── mjlab/             # 当前实现：MJLab 训练后端（隔离 venv）
├── assets/robots/         # 8 个标准化机器人包（契约 + MJCF/URDF + 训练配置）
├── web/                   # 纯静态前端（无构建）
│   └── sim2sim/           # 浏览器内 sim2sim（MuJoCo WASM + ORT Web）
├── scripts/               # 启动器、CLI、Windows 运行时与打包脚本
├── tools/                 # 离线工具链（校验/转换/审计/验收）
├── packaging/             # electron-builder 发行配置
├── docs/                  # 产品文档（桌面程序 / Web 程序）
├── 00_know/               # 知识库与决策文档（01–07 + _manifest.json）→ 00_know/README.md
└── 00_resources/          # 参考资源索引（实体在独立仓，fetch 拉取）→ 00_resources/README.md
```

> `00_` 前缀 = **资料类目录**（非运行时加载）：`00_know/` 是"为什么这么做"，
> `00_resources/` 是"依据在哪"，两者都不参与打包，也不被 `backend/` 直接 import。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 桌面壳 | Electron 28 + electron-builder 24（Windows portable / Linux AppImage） |
| 后端控制面 | Python 3.12（钉死）+ FastAPI + Uvicorn + Pydantic v2 + MuJoCo 3.11.0，uv 管理依赖 |
| 训练后端（隔离） | MJLab 1.6.0（MuJoCo Warp）+ PyTorch（cu128/cpu），训练栈只在独立 venv 中运行 |
| Web 前端 | 纯 HTML/CSS/ES Module JS，无构建；Three.js 本地 vendor |
| 浏览器 sim2sim | MuJoCo WASM（pthread）+ ONNX Runtime Web + Three.js，全部离线 vendor |
| 数据契约 | 8 份 JSON Schema + 生成的 Pydantic 模型；`contracts/` 零仿真依赖 |
| 资产准入 | 移植准入审计（上游训练源码佐证、包自包含、策略↔ONNX 一致性） |
| CI / 门禁 | 腾讯云 CNB；契约漂移、单测、无头 sim2sim 基线、族架构、插件统一度/seam 图、文档对账等，命令见 `package.json` 与 `registry/verify/` |
| 开发期 MCP | `.cnb/mcp/servers.json` 11 条 + `tools/mcp/` 自研 server（契约 / MuJoCo / ONNX / 资源库） |

---

## 快速开始

### 环境要求

- Node.js（Electron 28）
- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- Windows 10/11（主开发平台）或 Linux
- **正式训练建议 NVIDIA GPU**；无独显时可用 CPU profile 完成仿真与最小训练冒烟，但吞吐低一个量级。CPU 配置长期保留。

### 开发模式

```powershell
npm install
uv sync

npm start          # 一键启动（Electron 桌面壳，自动拉起后端）
# 或 Windows 双击 start.bat
```

启动后自动打开桌面启动器，后端就绪后进入工作台 `http://127.0.0.1:8765/web/workbench.html`。

### 云原生开发

仓库页面点 **「Legged Studio 开发」** 即进入在线环境（CNB 默认镜像，自带 WebIDE 与 CodeBuddy），依赖、Chromium 与 CPU 训练栈在环境启动时按需供应；后端自动在 `0.0.0.0:8765` 起来。详见 [`docs/cloud-dev.md`](docs/cloud-dev.md)。

### 分支与发布

- `main` 是唯一开发线；旧 `main` 保留为 `main-legacy`（2026-10-02 分支换位）。
- `main` 的 push 会把分支与 tag 镜像到 GitHub；`v*` tag 还会在本仓与 GitHub 两侧各建一个 Release。
- 凭据只从密钥仓库注入，不落工作区文件；执行体见 [`adapters/github/mirror.py`](adapters/github/mirror.py)。

### CPU 训练链路（无 GPU 也能跑真训练）

```bash
# 训练栈自检 + 16 envs × 5 iters 真实 PPO + 报告断言
bash scripts/cpu_training_smoke_gate.sh

# 需要重新供应训练 venv 时（幂等）
bash scripts/provision_cpu_training.sh
```

CPU 档适合**回路验证与移植冒烟**；质量档训练仍建议 GPU。具体档位与预算以 `registry/effect_criterion.json` 和任务清单为准。

### 测试与验收

```powershell
npm test           # 后端 unittest
npm run test:obs   # 浏览器观测构建器 node 单测
npm run check:docs # 文档数字 + manifest/链接对账
```

浏览器 E2E（确定性回放 + 截图，需要 Playwright）：

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt
playwright install chromium
pytest tests/e2e -v
```

无头 CPU sim2sim 验收（包内声明的策略全量，当前 40 条可执行，对照基线只拦新增退化）：

```bash
python tools/sim2sim_headless.py --seconds 3 \
  --baseline tools/sim2sim_headless_baseline.json
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

以**来源项目为单位**的原始资源取证库，作为 `assets/robots/` 归一化资产包的上游证据底座：

| 处置 | 内容 |
|---|---|
| 保留 | 源码 / 配置 / 文档 / 数据 / URDF·xacro·MJCF / 推理策略文件 |
| 省略 | 3D 网格与 CAD、点云与 ROS 录包、归档、可执行库与二进制、图像/音视频/字体、日志、>20MB 大文件 |
| 占位 | 被省略文件在原目录留 `_OMITTED.md`（文件名 / 体积 / 类型 / 源路径） |
| 索引 | [`00_resources/README.md`](00_resources/README.md)（项目清单 · 项目×机型矩阵 · 机型反查）+ `_index.json` |

- 定位：**只读参考底座**；`assets/robots/<id>/` 才是按 contract v3 收敛后的可执行版本。
- **资源实体外置**：134 个项目在私有仓 `zeitvex-lab/LeggedStudio-Resources`；主仓只保留索引、`_SPEC.md`、`_index.json` 与许可索引。首次或需要时运行 `python tools/fetch_resources.py`（可 `--project` 指定）。
- 同步脚本：`tools/sync_resources.py`；规范见 [`00_resources/_SPEC.md`](00_resources/_SPEC.md)。
- **许可分层**：项目代码 AGPL-3.0-only；`00_resources/` 各项目保留原始许可。无根 LICENSE / CC BY-NC/SA 资源只作参考，不随产品再分发。

---

## 详细文档

**产品文档**：

- [桌面程序（Electron 启动器）](docs/desktop-app.md) —— 桌面壳架构、后端生命周期、IPC、运行时供应、打包发行
- [Web 程序（工作台 + sim2sim）](docs/web-app.md) —— FastAPI 路由、工作台页面、浏览器内 sim2sim、API 一览

**知识库**（面向维护者，索引见 [`00_know/README.md`](00_know/README.md)）：

- [项目定位](00_know/01_项目定位.md) —— 为什么做 / 给谁做 / 做成什么 / 哪里不做
- [项目规划](00_know/02_项目规划.md) —— 上游对齐、功能地图、架构、模块、流程、门禁、阶段计划与指标
- [参考项目与资源](00_know/03_参考项目与资源.md) —— 资源地图、跨源对照、MJCF 字段级差异、22 篇综述出处
- [参数真值标准](00_know/04_参数真值标准.md) —— 参数取值的单一真值与现役机型来源对照
- [任务清单](00_know/05_任务清单.md) —— 当前状态、队列、挂账、待决与 DoD；历史在归档 08/09/10
- [统一架构方案](00_know/06_统一架构方案.md) —— 统一边界、族层、仿真/部署、插件协议与不变式
- [腿足强化学习综述](00_know/07_腿足机器人强化学习综述.md) —— 文献版图 + 工程路径 + 证据；四足/轮足为主、人形关键路线；22 篇综述（11 基础 + 11 子方向）+ 33 条经典论文线 + LoCoWiki 补编 + `00_resources` 项目实证，覆盖任务/仿真/MDP/算法/训练系统/sim2real/演进方向
- [参考资源库](00_resources/README.md) —— 按来源项目组织的参考资源与项目 × 机型矩阵

> **文档身份**：`00_know/_manifest.json` 管理稳定 ID、别名与依赖；改名只改 manifest 并同步仓库内引用，旧名记录在 `renamed_from`，不保留旧文件。工具引用登记在 manifest 的 `tools` 字段。

---

## 设计要点

1. **分层隔离**：contracts（零依赖）→ 控制面（轻量 FastAPI）→ 训练栈（隔离 venv 子进程）→ 浏览器验证（WASM），训练栈崩溃不影响控制面。
2. **契约驱动**：机器人、策略产物、部署、训练配置由 `contracts/` 下的 JSON Schema 定义，全项目单一事实源。
3. **数据驱动装配**：机型是数据、技能是族级机制、配方是档案数据、算法是插件；加机型不写技能代码，加技能不写机型分支。
4. **完全离线闭环**：浏览器 sim2sim 的 MuJoCo WASM、ONNX Runtime、Three.js 全部本地 vendor；训练 → 导出 → 验证无需联网。
5. **一切即插件**：内核 + 13 seam + 面板清单；统一度与 seam 图门禁进 CI，新增能力按 manifest 接线。
