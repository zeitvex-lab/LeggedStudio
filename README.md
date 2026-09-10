# Legged Studio

**腿足机器人强化学习工作室** —— 覆盖「资产盘点 → 模型检查 → RL 训练 → 策略导出 → sim2sim 验证 → 部署打包」全流程的全栈工具。

- 版本：`0.40.0`（见 `VERSION`）
- 许可：MIT
- 作者：zeitvex

---

## 它能做什么

| 环节 | 能力 |
|---|---|
| 资产管理 | 内置 14 个标准化机器人包（宇树 Go1/Go2/Go2W/B2/G1、云深处 Lite3/M20、逐际 TRON1 三形态、自研 ZEX-W 轮足、Wuji 五指灵巧手等），统一契约描述 |
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
├── assets/robots/         # 15 个标准化机器人包（契约 + MJCF/URDF + 训练配置）
├── web/                   # 纯静态前端（无构建），由 FastAPI 挂载到 /web
│   └── sim2sim/           # 浏览器内 sim2sim（MuJoCo WASM + ONNX Runtime Web）
├── scripts/               # 启动器、CLI、Windows 运行时下载与打包脚本
├── tools/                 # 离线工具链（URDF 校验/转 MJCF、策略转换、契约代码生成）
├── packaging/             # electron-builder 两种发行变体配置
└── 00_know/               # 知识库：机器人资产盘点、RL 训练分类知识地图
```

---

## 技术栈

| 层 | 技术 |
|---|---|
| 桌面壳 | Electron 28 + electron-builder 24（Windows portable / Linux AppImage） |
| 后端控制面 | Python 3.12（钉死）+ FastAPI + Uvicorn + Pydantic v2 + MuJoCo 3.11.0，uv 管理依赖 |
| 训练后端（隔离） | MJLab 1.6.0（MuJoCo Warp）+ PyTorch（cu128/cpu）+ BAM 执行器模型 |
| Web 前端 | 纯 HTML/CSS/ES Module JS，无构建步骤；Three.js 本地 vendor |
| 浏览器 sim2sim | MuJoCo WASM（pthread）+ ONNX Runtime Web 1.23.2 + Three.js，全部离线 vendor |
| 数据契约 | JSON Schema ×6 + 生成的 Pydantic 模型 |
| CI | 腾讯云 CNB：Python 语法、契约漂移检查、单测、前端 vendor 冒烟 |

---

## 快速开始

### 环境要求

- Node.js（Electron 28）
- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- Windows 10/11（主开发平台）或 Linux

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

### 测试

```powershell
npm test           # 后端 unittest（控制面纯逻辑测试）
npm run test:obs   # 浏览器观测构建器的 node 单测
```

### 打包发行

```powershell
npm run build:portable            # Windows portable（在线下载运行时）
npm run build:online:win          # 完整打包 + 校验
npm run build:portable:embedded   # 内嵌运行时版（完全离线）
npm run build:linux               # Linux AppImage
```

---

## 详细文档

- [桌面程序（Electron 启动器）](docs/desktop-app.md) —— 桌面壳架构、后端生命周期管理、IPC 接口、运行时供应、打包发行
- [Web 程序（工作台 + sim2sim）](docs/web-app.md) —— FastAPI 路由结构、工作台页面、浏览器内 sim2sim 验证器、API 一览

---

## 设计要点

1. **分层隔离**：contracts（零依赖）→ 控制面（轻量 FastAPI）→ 训练栈（隔离 venv 子进程）→ 浏览器验证（WASM），训练栈崩溃不影响控制面。
2. **契约驱动**：机器人、策略产物、部署、训练配置全部由 `contracts/` 下的 JSON Schema 定义，全项目单一事实源，CI 有契约漂移检查。
3. **插件化训练后端**：`adapters/backend_adapter.py` 定义 `BackendAdapter` Protocol（env/runner/exporter 三入口），可扩展接入 IsaacGym / UniLab / RoboLab 等其他训练栈。
4. **完全离线闭环**：浏览器 sim2sim 的 MuJoCo WASM、ONNX Runtime、Three.js 全部本地 vendor，训练 → 导出 → 验证全流程无需联网。
