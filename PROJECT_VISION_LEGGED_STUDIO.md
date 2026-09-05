# Legged Studio 项目愿景

**产品版本**：0.6.1
**更新日期**：2026-09-05  
**文档定位**：当前产品事实、使用主线与后续边界

## 产品定位

Legged Studio 是面向足式机器人强化学习的本地桌面/Web 工作台。它把机器人模型验证、MJLab 训练配置、训练监控和 MuJoCo 交互仿真放到统一控制面，并为后续 CLI、评估和部署适配保留稳定的 JSON 契约。

0.6.1 的主线机器人是 Unitree Go2、ZEX-W 与 MicroDuck：训练使用隔离的 native MJLab worker，
浏览器 sim2sim 已按实机合同验证三台机器人的策略部署（Go2 行走、ZEX-W 站立行驶、MicroDuck 全网格加载）。
控制面本身不导入 Torch、Warp 或 MuJoCo-Warp，页面加载也不会触发训练探针。

## 当前用户流程

桌面启动器打开后不会自动安装环境或启动服务。用户可以在启动器中选择端口和 GPU/CPU 配置，点击“配置运行环境”后才下载固定版本的运行时；配置完成后点击启动，服务通过 `/health` 校验成功才开放 Web 操作。

Web 工作台目前聚焦五个功能区：

1. **首页**：显示服务、运行时、适配器和资产状态。
2. **验证**：检查 Robot Contract、场景参数和 Go2/ZEX-W 资产，机器人页提供惯量盒可视化、质量/惯量表和分段电机参数卡（Kp/Kd/力矩/速度限制）。
3. **训练配置**：五分类模块化编辑器，支持框架选择（MJLab 可用、UniLab 规划中）、精选参数卡片与覆盖完整配置树的专家模式（dot-path 覆盖），基于统一的配置内省架构。
4. **训练**：wandb 风格监控视图——三段式概览侧栏、指标小倍数网格与检查点面板；可创建/停止 native MJLab worker 并查看真实日志。
5. **仿真**：通过 MuJoCo 进行基础遥控（键盘 WASD + QE 已验证）、地图切换和导航会话入口。

03/04 页面作为工作台壳的内嵌视图运行，与首页共享同一导航框架。

## 已实现能力

- FastAPI 控制面、Electron 桌面启动器和可配置本地端口。
- Go2/ZEX-W Robot Contract、资产清单和基础验证接口；验证页可导入用户自己的 URDF/MJCF 与相对 mesh 资源，保存到工作区并生成 Contract 草稿，preset 仅作为快捷模板。
- 首页支持导出/导入项目 ZIP 包，包内可携带机器人资产、Contract、MJLab training recipe 和 MuJoCo 场景。
- 唯一训练框架为 native MJLab；当前注册并可运行的算法为 PPO。
- MJLab worker 的运行时预检、训练任务状态、日志、metrics 和 artifact 索引。
- MuJoCo 基础仿真会话，支持 flat、rough、stairs、warehouse 地图及基础/导航模式数据契约。
- 导入资产可在 MuJoCo 仿真下选择和运行；当前产品主线以 Go2 与 ZEX-W 的 Robot Package 和训练 profile 为验收对象。
- Web 与桌面启动器采用接近 MJLab Play/Viser 的白色、浅灰、蓝色控件风格。
- 训练配置支持 JSON 导入/导出，导出的配置可作为后续 CLI 的输入。
- Windows Online 7z 打包脚本，以及按需配置 Python、Torch、MJLab 的流程。
- 浏览器 sim2sim 按实机部署合同对齐三台机器人：逐腿+轮关节布局、默认姿态、PD/低通参数与 ONNX 输入输出顺序一一对应，并内置各机器人地形场景。
- 控制面与训练路径解耦：页面加载不再触发 torch 探针；训练启动时才探测并缓存运行时状态。
- 机器人工作台性能优化：Web 资源 ETag 协商缓存、碰撞网格懒加载、网格并行拉取与快速解析。
- 训练配置/训练监控页面重构：五分类模块化配置编辑器（精选参数卡片 + 专家模式 dot-path 覆盖）、
  wandb 风格监控视图（概览侧栏、指标小倍数网格、检查点面板）、日志过滤。
- 统一配置内省架构（`adapters/mjlab/config_introspect.py` + `adapters/mjlab/param_registry.py`）：
  完整配置树由 adapter 自身推导，不再有源码黑盒；CLI、API 与前端共用同一套覆盖机制
  （`/api/training/config-preview` 与 `/api/training/profile-schema` 端点）。

## 明确的边界

- SAC、TD3 在算法注册表中保留扩展字段，但当前 native MJLab 不可用。
- MuJoCo 用于交互仿真，不作为训练后端；训练必须走 native MJLab。
- ONNX 导出、数值一致性 replay、复杂导航规划、实机控制和安全门禁尚未达到完整 L4 验收。
- URDF-Studio 目前作为验证和后续 3D 编辑集成的参考，不把其完整编辑器冒充为已集成功能。
- UniLab、RoboLab、RC_WheelLeg 和其他机器人仅作为后续 adapter、契约和部署参考。

## 架构约束

```text
Electron launcher
  -> FastAPI control plane (Python 3.12, lightweight)
     -> contracts / assets / task supervisor
     -> MuJoCo simulation API
     -> isolated MJLab adapter process (Torch, Warp, MuJoCo-Warp, RSL-RL)
```

所有跨进程数据都应通过版本化 JSON 结构传递。Robot Contract 描述模型、关节、观测、动作和控制频率；Scenario Contract 描述地图、随机种子、命令与终止条件；PolicyArtifact 记录训练配置、输入输出布局、依赖和验证结果。现有实现逐步落地这些契约，未实现字段不得被 UI 标记为已完成。

## 版本运行时

| 组件 | 0.6.1 目标版本 |
| --- | --- |
| Python | 3.12.13 |
| uv | 0.11.8 |
| Torch | 2.11.0+cu128（GPU）或 2.11.0+cpu |
| MJLab | 1.6.0 |
| MuJoCo / MuJoCo-Warp | 3.11.0 |

Online 包不内置完整 Torch/MJLab 安装，仅携带 uv、CPython 基础文件和固定源码快照；用户点击配置后才安装依赖。国内环境默认使用清华 PyPI 和上海交通大学 PyTorch 镜像，仍需用户自行提供兼容的 NVIDIA 驱动。

## 后续路线

优先完成 GPU 短 smoke 与长训练验收、Go2/ZEX-W 的评估和导航闭环、ONNX 数值一致性验证，再扩展通用导航任务、URDF-Studio 3D 工作区、UniLab/RoboLab adapter、CLI 和人工确认的实机部署包。每项扩展都必须先通过同一 Robot/Scenario/Policy 契约和可复现测试。

## 事实源

- [QUADRUPED_ASSET_INVENTORY.json](./QUADRUPED_ASSET_INVENTORY.json)
- [QUADRUPED_ASSET_INVENTORY.md](./QUADRUPED_ASSET_INVENTORY.md)
- [README.md](./README.md)
- [docs/DISTRIBUTION.md](./docs/DISTRIBUTION.md)
- [docs/DESKTOP_SETUP.md](./docs/DESKTOP_SETUP.md)
