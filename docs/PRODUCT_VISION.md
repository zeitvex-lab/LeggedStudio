# Legged Studio 产品愿景

Legged Studio 是面向足式机器人强化学习的本地桌面/Web 工作台。它把模型资产验证、Robot Contract、训练配置、训练监控和 MuJoCo 交互仿真放到同一条可追溯链路中，目标是从一个 URDF/MJCF 文件开始，得到可复现的训练与验证结果，并为后续 CLI、评估和部署适配保留稳定的 JSON 契约（Robot / Scenario / Policy）。

文档导航见 [README.md](README.md)；系统架构与真实能力边界见 [ARCHITECTURE.md](ARCHITECTURE.md)。

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

0.9.0 发布 **16 个机器人包 / 55 个训练 profile**：Unitree Go2（含 6 个技能任务与深度 parkour）、Go2-W、G1（含 AMP 与 DeepMimic 动作跟踪）、A1、A2、B2、B2-W、H1-2、ZEX-W、MicroDuck、Wuji Hand、Agibot D1、Deeprobotics Lite3、Deeprobotics M20（含 DreamWaQ）、LimX TRON1 Point/Sole-Foot。训练使用隔离的 native MJLab worker（唯一可运行算法为 PPO）；浏览器 sim2sim 已按实机部署合同对齐（关节布局、默认姿态、PD/低通参数、ONNX 输入输出顺序一一对应），16 机器人全量编译通过。控制面本身不导入 Torch、Warp 或 MuJoCo-Warp。

0.9.0 同时落地：

- **训练体系完全内化**：Go2 技能任务（jump/backflip/handstand/spring-jump/trot/dreamwaq/walk-these-ways）、G1 舞蹈权重包 + DeepMimic 跟踪任务（60 clips 动作库，xyzw→wxyz 四元数、clip 时间轴拼接）、M20 DreamWaQ（DreamActor/Critic + VAE 辅助损失）、Lite3/M20 官方奖励配方、PIE 深度感知 parkour（106×60 深度相机 + 地形感知指令 + 辅助损失）。外部训练源（LLoco/AMP/Instinct/wuji-mjlab/unitree_rl_mjlab）全部内化，无外部依赖。
- **全量训练验证器**（`tools/validate_training_smoke.py`）：128 并行环境 × 30 步 rollout 批量校验全部 profile，子进程隔离防 sys.path 污染；配合每日 4:00 定时任务自动验证 + 修复失败项。
- **MJCF 标准化**：lite3/a1 用官方 mesh 重建（视觉/碰撞分离），TRON1 按 limx_dynamics 校准碰撞体，d1/go2 补齐足端碰撞球；02 界面碰撞体可视化（开碰撞时视觉降透明，内部碰撞透出）。
- **仿真修复**：16 机器人浏览器场景路径/meshdir 一致性修复，全部可正常渲染；microduck/zex-w 补 `mujoco_sim` 能力门控恢复可见。
- **CaT 约束机制与奖励技巧集**（`adapters/mjlab/cat_constraints.py`、`shared_rewards.py`）：Polyak 运行极值约束、foot_flat/feet_distance/no_fly/landing_vel 等共享奖励项。
- **契约化与桌面工具链**：逐关节 armature/frictionloss、训练 profile 入口（env/runner/runner_class）、策略元数据盖章贯穿验收与浏览器链路；MjSpec 场景构建器（`adapters/mjlab/scene_builder.py`）、浏览器与桌面 replay 控制步对齐工具（`adapters/mjlab/replay_diff.py`）。

H1_2 的 velocity 训练 profile 已就绪，出策略后其姿态保持即从当前预期的趴地行为恢复为主动平衡站立。

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

优先完成 GPU 短 smoke 与长训练验收、ONNX 数值一致性 gate（DENYLIST fail-closed 语义），再扩展导航任务、感知观测项抽象、UniLab/RoboLab adapter 与人工确认的实机部署包。每项扩展都必须先通过同一 Robot/Scenario/Policy 契约和可复现测试。

## 验收标准

- 双击桌面程序不会自动写入或安装；点击启动才是唯一触发。
- 后端健康检查通过后，Web 工作台可直接进入模型验证、训练、仿真和评估页面。
- 同一份 Robot Contract 能被验证、训练、评估和导出流程共同读取。
- 训练停止、失败和桌面退出后不残留失控的子进程，日志和产物可定位。
