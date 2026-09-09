# Legged Studio

Legged Studio 是一个面向足式机器人强化学习的本地桌面/Web 工作台：机器人资产验证、MJLab 训练配置与监控、MuJoCo 交互仿真、浏览器 sim2sim 策略回放，全部通过版本化 JSON 契约（Robot / Scenario / Policy）串成可追溯链路。

Version `0.17.0` 发布 **16 个机器人包 / 55 个训练 profile**：Unitree Go2（12 profiles，含技能任务与深度 parkour）、Go2-W、G1（5 profiles，含 AMP 与 DeepMimic 动作跟踪）、A1、A2、B2、B2-W、H1-2、ZEX-W、MicroDuck（18 profiles）、Wuji Hand、Agibot D1、Deeprobotics Lite3、Deeprobotics M20（含 DreamWaQ）、LimX TRON1 Point/Sole-Foot。

已内化的训练体系：Go2 技能任务（jump/backflip/handstand/spring-jump/trot/dreamwaq/walk-these-ways）与 G1 舞蹈权重包、DeepMimic 跟踪任务（60 clips 动作库）、M20 DreamWaQ、Lite3/M20 官方奖励配方、PIE 深度感知 parkour（106×60 深度相机楼梯运动）。外部训练源（LLoco/AMP/Instinct/wuji-mjlab/unitree_rl_mjlab 等）已全部内化为包内本地任务库，无外部依赖。

**文档**：文档导航见 [docs/README.md](docs/README.md)。产品愿景见 [docs/PRODUCT_VISION.md](docs/PRODUCT_VISION.md)；系统架构与真实能力边界见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)；桌面程序见 [docs/DESKTOP_APP.md](docs/DESKTOP_APP.md)；Web 工作台见 [docs/WEB_APP.md](docs/WEB_APP.md)；机器人包建包/训练/验收的完整工程约定见 [docs/ROBOT_PACKAGE.md](docs/ROBOT_PACKAGE.md)。

## 快速开始

```powershell
npm ci
npm start
```

启动器打开是只读的：点 **Configure Runtime** 安装 GPU profile 到用户数据目录，再点 **Start** 启动后端并打开 Web 工作台（详见 [docs/DESKTOP_APP.md](docs/DESKTOP_APP.md)）。

构建发布：

```powershell
npm ci
npm run release:check
npm run build:online:win      # 推荐：Windows Online 7z 包
npm run build:portable        # Windows 便携 EXE
npm run build:portable:embedded  # 嵌入式 CUDA 大包（数 GB）
```

Linux AppImage 需在 Linux 主机/CI 上 `npm run build:linux`。产物写入 `dist/`；Online 包目录名为 `Legged-Studio-0.17.0-Windows-Online`。嵌入式运行时暂存于 `build/embedded-runtime`（Git 忽略）；CUDA 载荷超过 NSIS 上限，故刻意不用单 EXE。

## 目录职责（哪些能删、哪些不能）

| 目录/文件 | 职责 | 可否删除 |
| --- | --- | --- |
| `backend/` | FastAPI 控制面（`api_complete.py`）+ 各 API 子模块 + 测试 | 源码，勿删 |
| `contracts/` | Robot/Scenario/Policy 契约模型、校验器、fixture | 源码，勿删 |
| `adapters/mjlab/` | 隔离的 MJLab 训练适配器（独立 venv：Torch/Warp/RSL-RL） | 源码，勿删；`adapters/mjlab/.venv` 可删可重建 |
| `assets/robots/` | 内置机器人包（MJCF、网格、契约、训练 profile、仿真配置） | 源码，勿删 |
| `web/` | Web 工作台与浏览器 sim2sim（含 `vendor/` 离线三方库） | 源码，勿删 |
| `electron/` | 桌面启动器 | 源码，勿删 |
| `scripts/` | 发布检查、打包、运行时配置、CLI、生成器 | 源码，勿删 |
| `tools/` | 外部工具链包装：全量训练验证器（`validate_training_smoke.py` + `_smoke_one.py`，128 envs × 30 步批量校验 55 profiles）、URDF→MJCF 转换、动作库转换 | 源码，勿删 |
| `packaging/` | electron-builder 嵌入式/Online 两个配置 | 源码，勿删 |
| `docs/` | 产品愿景 + 桌面/Web 程序说明 + 工程约定 | 源码，勿删 |
| `contracts/fixtures/` | 契约测试样本 | 源码，勿删 |
| `.venv/` | 控制面 Python 环境 | 可删，`uv sync` 重建 |
| `node_modules/` | Electron 构建依赖 | 可删，`npm ci` 重建 |
| `workspace/` | 用户工作区：导入的包、训练产物、策略 | 运行时数据，删了丢训练历史 |
| `dist/` `build/` | 打包产物（Git 忽略） | 随时可删，重新构建即得 |
| `uv.lock` `package-lock.json` | 依赖锁 | 勿删 |
| `start.bat` | Windows 一键启动脚本 | 便捷入口 |
| `VERSION` | 当前发布版本号（release:check 校验一致性） | 勿删 |

## 架构

```text
Electron launcher（薄壳：生命周期/端口/运行时配置）
  -> FastAPI control plane（Python 3.12，轻量：backend/api_complete.py）
     -> contracts / assets / task supervisor
     -> MuJoCo simulation API（交互仿真，仅此用途）
     -> isolated MJLab adapter process（训练 worker：Torch、Warp、MuJoCo-Warp、RSL-RL）
```

核心约束：

- **控制面永远不导入训练栈**。Torch/Warp/MuJoCo-Warp 只存在于隔离的 adapter 进程/环境；页面加载不触发 torch 探针，训练启动时才探测并缓存运行时状态。
- **契约驱动**：跨进程数据一律走版本化 JSON。Robot Contract 是模型/关节序/观测/动作/控制频率的唯一入口；禁止在 UI、训练器和部署脚本中重复维护关节顺序或观测布局。
- **一个契约，两个入口**：Web 工作台与 `scripts/legged_studio_cli.py` 调同一组 HTTP 路由，语义天然一致。
- **训练后端唯一**：native MJLab（PPO 为唯一注册可运行算法；AMP/DreamWaQ/DeepMimic 跟踪以"任务 + 自定义 runner"形式实现）；MuJoCo 只做交互仿真。SAC/TD3 保留注册字段但不可运行；UniLab/RoboLab 为未来 adapter。
- **机器人差异走数据，不走特判**：训练入口统一为 55 个训练 profile（`entrypoints.env/runner/runner_class` 延迟加载，三种实现来源——generic builder / 精简本地源 / local_tasks 全框架——共用同一入口）；浏览器差异（地形、机身高度等）应入包配置，代码内 per-robot 分支是待清理的技术债（见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §7）。

### 配置内省

训练配置不是源码黑盒：`adapters/mjlab/config_introspect.py` + `param_registry.py` 从 adapter 自身推导完整配置树，CLI、API 与前端共用同一套 dot-path 覆盖机制（`/api/training/config-preview`、`/api/training/profile-schema`）。

## 测试与发布检查

```powershell
npm test               # uv run python -m unittest discover -s backend
npm run release:check  # 版本一致性 + 18 项必需资源 + extraResources
```

adapter 侧测试在 `adapters/mjlab/test_*.py`（其 venv 内运行）。

## 能力边界（诚实声明）

- 已验证：控制面单测、MJLab adapter 测试、16 机器人浏览器 sim2sim 全量编译通过（55/55 训练 profile 冒烟验证）、键盘遥控、CUDA 选择（RTX 4060 验证环境）、02 界面碰撞体可视化（视觉降透明让内部碰撞透出）、ONNX 导出数值一致性强制 gate（维度 + 数值回放 <1e-5，失败即删产物，`backend/export_gate.py`）、契约 v3 构型/角色/armature（`contracts/schema/robot-contract-3.0` + `role_resolver`）。
- 近期落地：左侧六功能区 + 顶部工作流进度条的工作台（`web/workbench.html`）、设置区（迁入桌面启动器「系统设置」，由 `backend/settings_api.py` 支撑：GPU profile 切换/重装、端口、Python 覆盖、镜像源、工作区清理）、训练观测/动作映射板（`training_create.html`：标准观测库→策略输入槽位，维度自动校验，专家模式 dot-path）、交互式导航地图编辑器（`web/navigation_editor.html`：画障碍/设航点→A*/Dijkstra 自动求路）、感知观测项通用抽象（`backend/perception_observations.py`：足端接触→高度场→深度相机 PIE 106×60）、导航评估写回策略档案（`navigation_api.py::_record_navigation_evaluation`）、导航感知-决策闭环（`adapters/mjlab/nav_avoidance.py` 反应式避障势场）、GPU 长训回归基线（`validate_training_smoke.py --mode longtrain`）、契约 v2/v3 收敛 loader（`contracts/contract_loader.py`）、sys.path 统一收敛（`contracts/path_bootstrap.py`）、app.js 观测构造器独立模块（`web/sim2sim/obs/observation_builders.js`）、export_api torch 懒加载、仓库自包含修复。
- 未闭环（L4）：GPU 长训练**实际验收跑通**（ 基线工具已就绪）、复杂导航**在线实跑**（已实现地图障碍感知避障闭环，深度相机实时决策端到端仍需训练栈环境验证）、实机控制与安全门禁。
- Online 包不内置 Torch/MJLab：仅携带 uv、CPython 引导文件与固定源码快照，用户点 Configure Runtime 后才安装。国内默认清华 PyPI + 上海交大 cu128 镜像；NVIDIA 驱动用户自备。
- 完整能力分级（已验证 / 已内化 / 规划中）与已知技术债清单见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §8 与 §7。

## 运行时版本（0.17.0）

Python 3.12.13 · uv 0.11.8 · Torch 2.11.0+cu128（GPU）/ +cpu · MJLab 1.6.0（快照 b517e0c）· Unitree 扩展 1425b15 · MuJoCo/MuJoCo-Warp 3.11.0
