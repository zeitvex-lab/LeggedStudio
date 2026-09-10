# Web 程序（FastAPI 控制面 + 工作台 + 浏览器 sim2sim）

Web 程序是 Legged Studio 的核心功能层，由两部分组成：

1. **FastAPI 控制面后端**（`backend/`）—— 提供全部 `/api/*` 接口，并静态托管前端
2. **纯静态 Web 前端**（`web/`）—— 无构建步骤的工作台 SPA + 浏览器内 sim2sim 验证器

两者运行在同一个进程里（Uvicorn，默认 `127.0.0.1:8765`），前端通过同域 `fetch` 调用 API，不存在跨域问题。

## 总体结构

```
┌──────────────────────────────────────────────────────────┐
│  浏览器                                                   │
│  ├─ /web/workbench.html   主工作台 SPA（hash 路由）       │
│  ├─ /web/sim2sim/         浏览器内 sim2sim 验证器         │
│  └─ /web/*.html           训练/部署/评估/资产等独立页面    │
└──────────┬───────────────────────────────────────────────┘
           │ HTTP（同源 fetch /api/*）
┌──────────▼───────────────────────────────────────────────┐
│  FastAPI 应用 (backend/api_complete.py)                   │
│  ├─ 中间件：CORS 全开放                                   │
│  │          BrowserSimulationIsolationMiddleware          │
│  │          （COOP/COEP → SharedArrayBuffer；MIME 修正）  │
│  ├─ /        → 302 到 /web/workbench.html#home            │
│  ├─ /web/*   → StaticFiles(web/, html=True)               │
│  └─ /api/*   → 各功能路由（可选栈缺失时优雅降级不注册）     │
└──────────────────────────────────────────────────────────┘
```

## 后端：FastAPI 控制面

入口：`backend/api_complete.py`（ASGI app 为 `backend.api_complete:app`）。

### 关键设计

- **纯控制面**：永不 import 训练栈（torch/mjlab）。训练通过 `training_manager` spawn 隔离 venv 子进程执行。
- **优雅降级**：MuJoCo 仿真等可选依赖缺失时，对应路由不注册而不是报错。
- **COOP/COEP 中间件**：对 `/web/sim2sim` 路径加 `Cross-Origin-Opener-Policy` / `Cross-Origin-Embedder-Policy` 头，启用 `SharedArrayBuffer`（MuJoCo pthread WASM 必需）；同时强制 `.mjs/.wasm` 的正确 MIME 类型（修复 Windows 注册表坑）。

### API 路由一览

| 前缀 | 模块 | 职责 |
|---|---|---|
| `/api/training` | `backend/training/{create,monitor,artifacts,events,schema}.py` | 训练任务创建、监控、产物、事件流、recipe schema |
| `/api/export` | `export_api.py` + `export_gate.py` | 策略导出 ONNX + 导出门禁校验 |
| `/api/deploy` | `deploy_api.py` + `deploy_pack.py` | 部署包打包 |
| `/api/evaluation` | `evaluation_api.py` | 策略评估 |
| `/api/simulation` | `simulation_api.py` | 服务端 MuJoCo 仿真（可选栈） |
| `/api/navigation` | `navigation_api.py` + `map_editor_api.py` | 导航/路径规划与地图编辑 |
| `/api/models` | `model_api.py` | 模型资产管理 |
| `/api/pretrained` | `pretrained_api.py` | 预训练策略管理 |
| `/api/terrain` | `terrain_api.py` + `terrain_gen/` | 地形生成（输出 MJCF XML） |
| `/api/health` | `health_api.py` + `health_cards.py` | 健康检查与能力卡片 |
| `/api/project` | `project_api.py` | 项目管理 |
| `/api/settings` | `settings_api.py` | 设置 |
| `/api/perception` | `perception_observations.py` | 感知观测配置 |

## 前端：工作台与独立页面

前端是**纯 HTML/CSS/ES Module JavaScript，无构建步骤**，直接由 FastAPI 静态托管。Three.js 等依赖全部本地 vendor，完全离线可用。

### 主工作台（workbench）

`web/workbench.html` + `workbench.js`（约 59KB）+ `workbench.css`（约 40KB）构成主 SPA，使用 **hash 路由**组织完整工作流：

```
#home → 机器人包库 → 3D 检查 → 训练创建 → 训练监控 → 仿真 → 部署
```

所有 API 调用都是 `fetch(window.location.origin + '/api/...')`，与同域后端交互。

### 功能页面

| 页面 | 作用 |
|---|---|
| `dashboard` | 总览仪表盘 |
| `training_create` / `training_list` / `training_monitor` | 训练创建（大表单，含 recipe schema 驱动）、任务列表、实时监控 |
| `deploy` | 部署包配置与打包 |
| `evaluation` | 策略评估 |
| `artifacts` | 训练产物浏览 |
| `assets` | 机器人资产浏览 |
| `navigation_editor` | 导航地图编辑 |
| `urdf-viewer.js` | Three.js URDF/MJCF 3D 检查器 |

### 附属工具：urdf-viewer（可选）

`web/urdf-viewer/` 是一个独立的 React 18 + Vite + @react-three/fiber 小工具，仅在需要开发 3D 检查器增强功能时使用，不影响主工作台（主工作台用的是无构建版 `urdf-viewer.js`）。

## 浏览器 sim2sim（web/sim2sim/）

这是项目最有特色的部分：**把整个 sim2sim 验证搬进了浏览器**，无需安装任何东西。

### 架构

```
┌─ web/sim2sim/ ────────────────────────────────────────────┐
│ app.js（约 206KB）  应用主逻辑                             │
│  ├─ MuJoCo WASM（pthread 构建）   ← vendor/mujoco.js+wasm│
│  │    物理仿真，靠 SharedArrayBuffer 多线程                │
│  ├─ ONNX Runtime Web 1.23.2       ← vendor/onnxruntime-web│
│  │    加载 policy.onnx 跑策略推理                          │
│  ├─ Three.js                    ← vendor/three.js         │
│  │    场景渲染                                              │
│  └─ obs/observation_builders.js                           │
│       观测构建器（与训练侧对齐，带 node 单测）               │
│                                                           │
│ assets/go2/   Go2 全套 MJCF 场景：flat / stairs / slope / │
│               race_track 等 13 种地形                      │
│ models/       内置预训练策略 ONNX（如 go2_moe_cts_…164k）   │
└───────────────────────────────────────────────────────────┘
```

### 工作原理

1. 加载 MJCF 场景 XML + meshes 到 MuJoCo WASM，创建物理世界。
2. 加载 ONNX 策略到 ONNX Runtime Web。
3. 每个控制周期：从 MuJoCo 读取状态 → `observation_builders.js` 构建观测向量（与训练侧严格对齐）→ ONNX 推理 → 动作写回 MuJoCo → 步进物理 → Three.js 渲染。
4. 因为观测构建器与训练契约一致，浏览器里走通即代表 sim2sim 链路可信。

### 为什么需要 COOP/COEP

MuJoCo 的 pthread 版 WASM 依赖 `SharedArrayBuffer`，浏览器要求页面处于跨域隔离环境（`Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy: require-corp`）。后端的 `BrowserSimulationIsolationMiddleware` 专门为 `/web/sim2sim` 路径注入这些响应头。

### 离线闭环

所有 vendor 库（mujoco.wasm、onnxruntime-web、three.js）全部本地打包，训练 → 导出 ONNX → 浏览器验证全流程**无需联网**。

## 观测构建器单测

```powershell
npm run test:obs   # node web/sim2sim/obs/observation_builders.test.mjs
```

保证浏览器侧观测构建与契约定义不发生漂移。

## 本地开发（不启动 Electron）

Web 层可以脱离桌面壳独立开发调试：

```powershell
uv sync
uv run python -m uvicorn backend.api_complete:app --host 127.0.0.1 --port 8765 --reload
```

然后浏览器访问 `http://127.0.0.1:8765/`（自动跳转工作台）。前端改动刷新即生效（无构建），后端 `--reload` 自动重启。
