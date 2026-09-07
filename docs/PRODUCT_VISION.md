# Legged Studio 产品愿景

Legged Studio 是面向足式机器人强化学习的本地桌面/Web 工作台。它把模型资产验证、Robot Contract、训练配置、训练监控和 MuJoCo 交互仿真放到同一条可追溯链路中，目标是从一个 URDF/MJCF 文件开始，得到可复现的训练与验证结果，并为后续 CLI、评估和部署适配保留稳定的 JSON 契约（Robot / Scenario / Policy）。

本文档是唯一的产品级愿景。桌面程序说明见 [DESKTOP_APP.md](DESKTOP_APP.md)，Web 工作台见 [WEB_APP.md](WEB_APP.md)，机器人包工程约定见 [ROBOT_PACKAGE.md](ROBOT_PACKAGE.md)。

## 用户入口

桌面启动器刻意保持轻薄：打开是只读的，不创建目录、不安装依赖、不启动服务。用户选择端口与 GPU/CPU 配置后点击"配置运行环境"，固定版本的运行时才下载到 Electron 用户数据目录；点击启动后，后端必须通过 `/health` 身份校验（`app_id=legged-studio`）才开放任何 Web 操作。

## 闭环工作流

1. **模型验证**：选择版本化机器人包，检查 URDF/MJCF、关节映射、质量和控制频率；机器人页提供惯量盒可视化、质量/惯量表和分段电机参数卡（Kp/Kd/力矩/速度限制）。可导入用户自己的 URDF/MJCF 与相对 mesh 生成 Contract 草稿，preset 仅作为快捷模板。
2. **训练配置**：五分类模块化编辑器，支持框架选择（MJLab 可用、UniLab 规划中）、精选参数卡片与覆盖完整配置树的专家模式（dot-path 覆盖），基于统一的配置内省架构。
3. **训练**：创建/停止隔离的 native MJLab worker，在 wandb 风格监控页查看概览侧栏、指标小倍数网格、检查点面板与真实日志；训练产物写入用户工作区。
4. **仿真**：MuJoCo 交互遥控（键盘 WASD + QE 已验证）、地图切换、导航会话入口，以及浏览器 sim2sim 视图。
5. **导出与部署准备**：生成 ONNX、PolicyArtifact 和部署配置；真实机器人上电、放行和执行始终需要人工确认。

训练配置页与监控页作为工作台壳的内嵌视图运行，与首页共享同一导航框架。

## 当前发布状态（0.9.0）

0.9.0 发布八个机器人包：Unitree Go2、ZEX-W、MicroDuck、Unitree G1、Unitree Go2-W、Unitree A2、Wuji Hand、Unitree H1_2。训练使用隔离的 native MJLab worker（唯一可运行算法为 PPO）；浏览器 sim2sim 已按实机部署合同对齐已发布机器人（关节布局、默认姿态、PD/低通参数、ONNX 输入输出顺序一一对应）。控制面本身不导入 Torch、Warp 或 MuJoCo-Warp，页面加载不触发训练探针。

0.9.0 同时落地：Go2 的技能任务（rear-stand、jump、handstand）与 A2/G1/H1_2 的 velocity 任务全部内化为包内本地任务库（`training/source/`，无外部训练源依赖）、逐关节 armature/frictionloss 的契约化（贯穿验收、浏览器与配置链路）、桌面工具链可复用的 MjSpec 场景构建器（`adapters/mjlab/scene_builder.py`），以及浏览器与桌面 replay 的控制步对齐工具（`adapters/mjlab/replay_diff.py`）。H1_2 的 velocity 训练 profile 已就绪，出策略后其姿态保持即从当前预期的趴地行为恢复为主动平衡站立。

## 产品边界

- MVP 保持 Go2 + MJLab/PPO + 本地 MuJoCo 评估；其他后端通过 adapter 接入，绝不把训练栈导入控制面。
- Robot Contract、PolicyArtifact 和 Scenario Contract 是跨模块的事实来源，禁止在 UI、训练器和部署脚本中重复维护关节顺序或观测布局。
- 能力声明必须区分候选、已验证、已闭环；SAC、TD3 在注册表保留扩展字段但当前不可运行。
- MuJoCo 仅作为交互仿真引擎，永远不是训练后端。
- ONNX 导出、数值一致性 replay、复杂导航规划、实机控制和安全门禁尚未达到完整 L4 验收。
- UniLab、RoboLab、RC_WheelLeg 仅作为后续 adapter、契约和部署参考。

## 架构约束

```text
Electron launcher
  -> FastAPI control plane (Python 3.12, lightweight)
     -> contracts / assets / task supervisor
     -> MuJoCo simulation API
     -> isolated MJLab adapter process (Torch, Warp, MuJoCo-Warp, RSL-RL)
```

所有跨进程数据都通过版本化 JSON 结构传递。Robot Contract 描述模型、关节、观测、动作和控制频率；Scenario Contract 描述地图、随机种子、命令与终止条件；PolicyArtifact 记录训练配置、输入输出布局、依赖和验证结果。未实现的字段不得被 UI 标记为已完成。

## 版本运行时

| 组件 | 0.9.0 目标版本 |
| --- | --- |
| Python | 3.12.13 |
| uv | 0.11.8 |
| Torch | 2.11.0+cu128（GPU）或 2.11.0+cpu |
| MJLab | 1.6.0（源码快照 b517e0c） |
| Unitree 扩展 | 1425b15 |
| MuJoCo / MuJoCo-Warp | 3.11.0 |

Online 包不内置完整 Torch/MJLab 安装，仅携带 uv、CPython 基础文件和固定源码快照；用户点击配置后才安装依赖。国内环境默认使用清华 PyPI 和上海交通大学 PyTorch 镜像，NVIDIA 驱动仍需用户自行提供。

## 后续路线

优先完成 GPU 短 smoke 与长训练验收、Go2/ZEX-W 的评估和导航闭环、ONNX 数值一致性验证，再扩展通用导航任务、URDF-Studio 3D 工作区、UniLab/RoboLab adapter、CLI 和人工确认的实机部署包。每项扩展都必须先通过同一 Robot/Scenario/Policy 契约和可复现测试。

## 验收标准

- 双击桌面程序不会自动写入或安装；点击启动才是唯一触发。
- 后端健康检查通过后，Web 工作台可直接进入模型验证、训练、仿真和评估页面。
- 同一份 Robot Contract 能被验证、训练、评估和导出流程共同读取。
- 训练停止、失败和桌面退出后不残留失控的子进程，日志和产物可定位。
