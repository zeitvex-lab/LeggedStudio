# 桌面程序说明（Electron Launcher）

Legged Studio 桌面程序是一个刻意的薄启动器：打开是只读的，不创建目录、不安装依赖、不启动服务；所有环境配置和服务启动都是用户显式点击后的动作。它负责生命周期与工作区管理，业务功能全部在 Web 工作台（见 [WEB_APP.md](WEB_APP.md)）。

## 程序结构

```text
electron/launcher/
  main.js        # 主进程：路径解析、Python 探测、运行时配置、后端启动/停止、健康校验
  preload.js     # contextBridge 暴露受控 IPC API（settings/runtime/backend 通道）
  renderer.js    # 启动器 UI 逻辑
  index.html     # 启动器窗口（端口/GPU/CPU/镜像源、工作区清理、Configure Runtime、Start）
  styles.css
```

关键常量（`main.js`）：默认后端端口 `8765`（设置范围 1024–65535）、下载运行时版本 `windows-cuda-2026.09`、期望 API schema `legged-studio-api-1`。

## 路径解析（开发 vs 打包）

| 目标 | 开发模式 | 打包模式 |
| --- | --- | --- |
| 项目根 | 仓库根 | exe 同级目录或 `resources` 根 |
| 后端入口 | `backend/api_complete.py` | `app/backend/api_complete.py`（多候选回退） |
| Python | `runtime/python` 下的便携版 | 打包内 `runtime/python` 或用户数据目录 |
| MJLab 源码快照 | `../mjlab_new/mjlab`（兄弟目录） | `runtime/mjlab_source` |
| 清单 | 上级目录 `QUADRUPED_ASSET_INVENTORY.json` | `app/QUADRUPED_ASSET_INVENTORY.json` |

开发模式判定：`NODE_ENV=development` 或 `!app.isPackaged`（`npm start` / `npm run dev`）。

## 启动流程（每次都经过健康校验）

1. **打开启动器**：只读。读取设置（端口、计算设备、Python 覆盖路径），不写任何东西。
2. **配置运行环境（Configure Runtime）**：下载固定的运行时 profile 到 Electron 用户数据目录（不是程序目录）。GPU profile 安装 `torch==2.11.0+cu128`，CPU profile 安装 `+cpu` 版本。Online 包已内置 uv、CPython 3.12.13 基础文件和 MJLab/Unitree 源码快照，整个配置过程不需要访问 GitHub；国内默认走清华 PyPI 和上海交大 cu128 镜像。
3. **启动控制面（Start control plane）**：创建可写的用户数据目录 → 探测 Python（必须 3.12，启动器**永不回退系统 Python**，除非设置里显式覆盖）→ 校验 fastapi/uvicorn/pydantic → 启动 Uvicorn（`backend.api_complete:app`）→ 轮询 `/health` 直到通过身份校验（`app_id=legged-studio` 且 `api_schema=legged-studio-api-1`）→ 才开放 Web 按钮。
4. **打开 Web 工作台**：加载 `http://127.0.0.1:<port>/`。

端口被其他服务占用会被拒绝；无关服务不会因端口匹配被误认成本程序（有身份校验兜底）。桌面退出时后端进程随之终止，不残留失控子进程。

## 桌面设置（原 Web 设置区已迁入）

桌面启动器的「系统设置」页统一承载运行环境与工作区配置：

- **控制平面地址**：本机回环地址，不对外暴露。
- **Python 运行时**：探测绑定 Python 版本与依赖完整性。
- **Windows 运行环境**：一键下载配置（GPU/CPU Torch + MJLab），经运行时管线安装到用户数据目录。
- **计算设备**：GPU（cu128）/ CPU（+cpu）profile 切换，保存后重装运行时生效。
- **包镜像源**：清华 PyPI + 上海交大 cu128（默认）/ 上海交大 / 官方源；保存后重装运行时生效。
- **服务端口**：默认 `8765`，接受 1024–65535 的整数，启动前在设置里改。
- **Python 路径覆盖**（可选）：文件选择器指定；留空则始终用项目捆绑的便携 Python。不支持的版本会在 pip 运行前被拒绝。
- **工作区目录**：初始化日志、输出与文档目录。
- **工作区清理**：删除可再生成的暂存/导入缓存（导入暂存、导出暂存、缓存目录）；训练历史与已导入的 packages/ 不受影响。
- **项目路径**：打开项目根目录。

上述镜像源、工作区清理等通过后端 settings API（`backend/settings_api.py`）持久化。

## 打包与发布

构建前置：Node.js 18+，`npm ci`，然后 `npm run release:check`（校验 VERSION/package.json 一致性、18 个必需资源、extraResources 完整性）。

| 目标 | 命令 | 产物 |
| --- | --- | --- |
| Windows 便携版 | `npm run build:portable` | `dist/` 下的 portable EXE |
| Windows Online 7z（推荐分发形态） | `npm run build:online:win` | `dist/Legged-Studio-0.17.0-Windows-Online.7z`（目录同名，非 win-unpacked） |
| Windows 嵌入式 CUDA 版 | `npm run build:portable:embedded` | `dist/embedded-win/win-unpacked` + `dist/Legged-Studio-0.17.0-Windows-CUDA.7z` |
| Linux AppImage | 在 Linux 主机/CI 上 `npm run build:linux` | AppImage + 目录包 |

嵌入式版本先经 `stage:runtime:win` 把独立 CPython 3.12、CUDA Torch（cu128）、MJLab 1.6.0、Unitree 扩展暂存到 `build/embedded-runtime`（Git 忽略）。不做单 EXE：CUDA/MJLab 载荷超过 NSIS 内存映射输入上限，这是刻意的。运行时配置完成后程序目录保持小体积，可替换升级而不删已下载环境。

打包内容边界（`package.json` extraResources）：backend、contracts、`assets/robots`、docs、web、adapters（排除 .venv/缓存）、tools、scripts、VERSION、资产清单。**不打包** `node_modules`、`.venv`、workspace、var、任何训练运行时——Torch/MJLab 一律按需安装（嵌入式目标除外）。

## 运行时版本（0.17.0）

| 组件 | 版本 |
| --- | --- |
| Python | 3.12.13 |
| uv | 0.11.8 |
| Torch | 2.11.0+cu128（GPU）/ 2.11.0+cpu |
| MJLab | 1.6.0（源码快照 b517e0c） |
| Unitree 扩展 | 1425b15 |
| MuJoCo / MuJoCo-Warp | 3.11.0 |

NVIDIA 显卡驱动始终由用户自备；程序不安装驱动。

## 故障排查

用启动器的 Console 页看确切错误。常见原因：镜像网络被墙、缺 NVIDIA 驱动、端口被占用、运行时未配置。所有依赖后端的按钮在对应 API 请求返回已验证结果之前保持禁用。
