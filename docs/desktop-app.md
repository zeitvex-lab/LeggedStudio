# 桌面程序（Electron 启动器）

Legged Studio 的桌面程序是一个 **Electron 28** 应用，但它本身不做任何机器人计算——它的核心职责是：**管理 Python 后端的完整生命周期**，并提供一个启动器界面让用户配置和监控后端。

## 目录结构

```
electron/launcher/
├── main.js        # 主进程（约 660 行）：后端生命周期、端口、托盘、设置、运行时下载
├── preload.js     # contextBridge：向渲染进程暴露 window.leggedStudio（30+ IPC 接口）
├── renderer.js    # 启动器 UI 逻辑
├── index.html     # 启动器页面
└── styles.css     # 启动器样式
```

入口由 `package.json` 的 `main: electron/launcher/main.js` 指定；`scripts/start-electron.js` 负责清理 `ELECTRON_RUN_AS_NODE` 环境变量后 spawn Electron。

## 架构图

```
┌─ Electron 主进程 (main.js) ──────────────────────────────┐
│                                                          │
│  ① 路径解析：dev 用项目根 / 打包用 resources/app          │
│  ② 运行时探测：嵌入式 Python 是否就绪                     │
│  ③ 端口检查：默认 8765，杀掉僵尸后端进程                  │
│  ④ spawn: python -m uvicorn backend.api_complete:app     │
│  ⑤ 轮询 /health（校验 instance ID，防止串到别人的端口）    │
│  ⑥ 系统托盘 + Windows 任务栏训练进度条                    │
│  ⑦ 退出前确认（有训练任务运行时弹对话框）                  │
│                                                          │
└──────────┬───────────────────────────────────────────────┘
           │ IPC（ipcMain.handle / event 推送）
┌──────────▼───────────────────────────────────────────────┐
│  preload.js (contextBridge)                              │
│  window.leggedStudio = {                                 │
│    backend: { start, stop, check, url, ... },            │
│    environment: { probe, setup, provisionWindows, ... }, │
│    settings: { get, set, ... },                          │
│    on: { backendLog, backendStatus, runtimeProgress }    │
│  }                                                       │
└──────────┬───────────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────────┐
│  渲染进程 (renderer.js + index.html)                      │
│  启动器 UI：环境检测 → 运行时安装 → 启动后端 → 打开工作台  │
└──────────────────────────────────────────────────────────┘
```

## 主进程职责详解

### 1. 后端生命周期管理

- **路径解析**：开发模式使用项目根目录；打包后使用 `resources/app` 下的后端代码。
- **端口管理**：默认端口 `8765`。启动前检查端口占用，发现僵尸后端进程（旧的 uvicorn）会清理。
- **启动命令**：
  ```
  python -m uvicorn backend.api_complete:app --host 127.0.0.1 --port 8765
  ```
- **健康检查**：轮询 `/health`，并校验响应中的 instance ID——确保连上的是自己启动的后端，而不是端口被其他实例占用。
- **日志流**：后端 stdout/stderr 通过 `backend-log` 事件推送到启动器界面实时显示。

### 2. Windows 运行时供应（Provisioning）

训练栈（MJLab + PyTorch）体积庞大，不随安装包分发。主进程通过 `scripts/provision_windows_runtime.ps1` 按需下载 **`windows-cuda-2026.09` 运行时**，内容包括：

- 嵌入式 Python 3.12
- MJLab 源码及隔离 venv
- unitree_rl_mjlab 扩展

支持 GPU/CPU 设备选择，内置 GPU 检测。**正式训练建议选择 GPU**；CPU profile 可用于仿真与最小训练冒烟验证（速度慢约一个量级），且长期保留、可随时切回。下载进度通过 `runtime-progress` 事件实时推送。

### 3. 系统托盘与进度条

- 系统托盘常驻，可最小化到托盘运行。
- **Windows 任务栏进度条**：每 5 秒轮询 `/api/training/list`，有训练任务运行时在任务栏图标上显示训练进度。
- **退出保护**：检测到训练任务正在运行时，关闭窗口会弹出确认对话框，防止误杀训练。

### 4. 设置持久化

设置存储在 `userData/settings.json`：

| 键 | 说明 |
|---|---|
| `autoStartBackend` | 启动应用时自动拉起后端 |
| `pythonPath` | 自定义 Python 解释器路径 |
| `backendPort` | 后端端口（默认 8765） |
| `torchDevice` | 训练设备（cuda / cpu） |

## IPC 接口一览（preload.js 暴露）

| 分组 | 接口 | 作用 |
|---|---|---|
| `backend:*` | `start` / `stop` / `check` / `url` | 后端启停与状态查询 |
| `environment:*` | `probe` / `setup` / `provision-windows` | 环境检测与运行时安装 |
| `settings:*` | `get` / `set` | 设置读写 |
| 事件流 | `backend-log` / `backend-status` / `runtime-progress` | 主进程 → 渲染进程的推送 |

## 用户流程

```
启动应用
  → 环境检测（Python / 端口 / 运行时）
  → （首次）下载嵌入式运行时，选 GPU/CPU
  → 启动后端，等待 /health 就绪
  → 进入 Web 工作台（http://127.0.0.1:8765/web/workbench.html）
  → 训练时任务栏显示进度，可最小化到托盘
  → 关闭时若有训练运行则二次确认
```

## 打包发行

两种发行变体（配置在 `packaging/`）：

| 命令 | 变体 | 说明 |
|---|---|---|
| `npm run build:online:win` | 在线版 | 安装包小，首次启动时下载运行时 |
| `npm run build:portable:embedded` | 内嵌版 | 运行时打包进安装包，完全离线可用 |
| `npm run build:linux` | Linux | AppImage |
| `npm run verify:online:win` / `verify:embedded:win` | 验证 | 发行后自动校验 |

打包时 `electron-builder` 通过 `extraResources` 把 `backend/`、`contracts/`、`assets/robots/`、`web/`、`adapters/`（排除 `.venv`）、`tools/`、`scripts/` 一并带入 `resources/app`。
