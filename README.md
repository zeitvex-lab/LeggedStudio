# Legged Studio

**腿足机器人强化学习工作室** —— 覆盖「资产盘点 → 模型检查 → RL 训练 → 策略导出 → sim2sim 验证 → 部署打包」全流程的全栈工具。

- 版本：`0.45.0`（见 `VERSION`）
- 许可：MIT
- 作者：zeitvex

---

## 它能做什么

| 环节 | 能力 |
|---|---|
| 资产管理 | 内置 14 个标准化机器人包（宇树 Go1/Go2/Go2W/B2/G1、云深处 Lite3/M20、逐际 TRON1 三形态、自研 ZEX-W 轮足、Wuji 五指灵巧手等），统一契约描述；随仓附带 14 机型参考资源库 [`00_resources/`](00_resources/README.md) |
| 模型检查 | URDF/MJCF 校验、3D 可视化检查器、契约合规校验 |
| RL 训练 | 通过隔离子进程调用 MJLab（MuJoCo Warp + PyTorch）训练后端，PPO / off-policy 算法，训练任务创建、监控、事件流 |
| 策略导出 | 导出 ONNX 部署策略，导出门禁（export gate）校验 |
| sim2sim 验证 | 浏览器内直接跑 MuJoCo WASM + ONNX Runtime Web，完全离线验证策略 |
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
│ Schema/校验/ │  │ 15 机器人包  │   │ PPO / off-policy           │
│ 角色解析      │  │ + 资产清单   │   │ ──► ONNX 导出              │
│ （零依赖）    │  └─────────────┘   └───────┬───────────────────┘
└──────────────┘                            │ policy.onnx + 部署元数据
                                            ▼
                        web/sim2sim（浏览器 WASM 验证）
                        ──► deploy_pack 部署包 ──► 真机
```

**数据流主线**：机器人包（`assets/robots` + contract v3）→ 工作台 3D 检查 → 训练创建（training API → training_manager → mjlab launcher → 隔离 worker）→ ONNX 导出（export gate 校验）→ 浏览器 sim2sim 验证 → 部署包打包。

---

## 目录结构

```
legged_studio/
├── electron/launcher/     # Electron 桌面壳（主进程 + preload + 启动器 UI）
├── backend/               # FastAPI 控制面（纯控制面，不含训练栈）
│   ├── training/          # 训练 API 子包（create/monitor/artifacts/events/schema）
│   ├── terrain_gen/       # 地形生成（MJCF XML 输出）
│   └── *_api.py           # deploy/export/evaluation/navigation/terrain 等路由
├── contracts/             # 稳定数据契约（JSON Schema + Pydantic 模型，零仿真依赖）
├── adapters/              # 训练后端插件层
│   └── mjlab/             # 当前唯一实现：MJLab 训练后端（隔离 venv）
├── assets/robots/         # 14 个标准化机器人包（契约 + MJCF/URDF + 训练配置）
├── web/                   # 纯静态前端（无构建），由 FastAPI 挂载到 /web
│   └── sim2sim/           # 浏览器内 sim2sim（MuJoCo WASM + ONNX Runtime Web）
├── scripts/               # 启动器、CLI、Windows 运行时下载与打包脚本
├── tools/                 # 离线工具链（URDF 校验/转 MJCF、策略转换、契约代码生成、移植准入审计）
├── packaging/             # electron-builder 两种发行变体配置
├── docs/                  # 产品文档（桌面程序 / Web 程序）
├── 00_know/               # 知识库与决策文档（盘点 / 标准 / 方案 / 专题报告）→ 00_know/README.md
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
| CI | 腾讯云 CNB：Python 语法、契约漂移检查、单测、openapi 契约冒烟、无头 CPU sim2sim 基线门禁、移植准入审计、前端 vendor 冒烟 |
| 云原生开发 | 根 `Dockerfile` + `.cnb.yml` 的 `vscode` 事件，一键起环境（控制面依赖 + Chromium + **mjlab CPU 训练栈**全固化，浏览器 sim2sim 开箱可用）→ `docs/cloud-dev.md` |

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

仓库页面点 **「Legged Studio 开发」** 即进入在线环境，依赖、Chromium 与 **CPU 训练栈**
已固化在镜像里，后端自动在 `0.0.0.0:8765` 起来，浏览器 sim2sim 可直接看、可直接截图调试。
详见 [`docs/cloud-dev.md`](docs/cloud-dev.md)。

### CPU 训练链路（无 GPU 也能跑真训练）

mjlab 官方支持 CPU（`cpu` extra），本仓库把它接成完整链路：容器/本地进环境即可训练，
不需要 GPU 额度。

```bash
# 训练栈自检 + 64 envs × 20 iters 真实 PPO + 报告断言
bash scripts/cpu_training_smoke_gate.sh

# 需要重新供应训练 venv 时（幂等）
bash scripts/provision_cpu_training.sh
```

训练栈落点集中在 `contracts/path_bootstrap.py`（`LEGGED_STUDIO_MJLAB_VENV` 可覆盖），
体检 L0 给出三态：`cuda`（正式训练）/ `cpu-only`（仿真与冒烟）/ `unavailable`（先供应环境）。

### 测试

```powershell
npm test           # 后端 unittest（控制面纯逻辑测试）
npm run test:obs   # 浏览器观测构建器的 node 单测
```

浏览器 E2E（确定性回放 + 截图，需要 Playwright）：

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt
playwright install chromium
pytest tests/e2e -v
```

无头 CPU sim2sim 验收（47 条策略，对照基线只拦新增退化）：

```bash
python tools/sim2sim_headless.py --seconds 3 \
  --baseline tools/baselines/sim2sim_headless_baseline.json
```

CPU 训练冒烟门禁（64 envs × 20 iters 真实 PPO，需已供应训练栈）：

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

- [知识库索引](00_know/README.md) —— 愿景与路线 / 资产调研 / 参数标准 / B 组专题四组文档的导航
- [参考资源库](00_resources/README.md) —— 按来源项目组织的参考资源、项目 × 机型矩阵与省略登记
- [资源模型重构方案](00_know/重构方案_RobotAsset资源模型与实施路线.md) —— RobotAsset 5 资源模型与 M0–M5 落地路线
- [B8 移植准入报告](00_know/B8_移植准入报告.md) —— 训练/仿真的移植准入规则（须有上游训练源码佐证）+ 14 机型审计矩阵

---

## 设计要点

1. **分层隔离**：contracts（零依赖）→ 控制面（轻量 FastAPI）→ 训练栈（隔离 venv 子进程）→ 浏览器验证（WASM），训练栈崩溃不影响控制面。
2. **契约驱动**：机器人、策略产物、部署、训练配置全部由 `contracts/` 下的 JSON Schema 定义，全项目单一事实源，CI 有契约漂移检查。
3. **插件化训练后端**：`adapters/backend_adapter.py` 定义 `BackendAdapter` Protocol（env/runner/exporter 三入口），可扩展接入 IsaacGym / UniLab / RoboLab 等其他训练栈。
4. **完全离线闭环**：浏览器 sim2sim 的 MuJoCo WASM、ONNX Runtime、Three.js 全部本地 vendor，训练 → 导出 → 验证全流程无需联网。
