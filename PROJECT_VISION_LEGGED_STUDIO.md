# Legged Studio 项目愿景

**产品版本**：0.5.0
**更新日期**：2026-09-02  
**文档定位**：当前产品事实、使用主线与后续边界

## 产品定位

Legged Studio 是面向足式机器人强化学习的本地桌面/Web 工作台。它把机器人模型验证、MJLab 训练配置、训练监控和 MuJoCo 交互仿真放到统一控制面，并为后续 CLI、评估和部署适配保留稳定的 JSON 契约。

0.5.0 的主线机器人是 Unitree Go2、Go2W 与 ZEX-W：训练使用隔离的 native MJLab worker，基础交互仿真使用 MuJoCo。控制面本身不导入 Torch、Warp 或 MuJoCo-Warp。

## 当前用户流程

桌面启动器打开后不会自动安装环境或启动服务。用户可以在启动器中选择端口和 GPU/CPU 配置，点击“配置运行环境”后才下载固定版本的运行时；配置完成后点击启动，服务通过 `/health` 校验成功才开放 Web 操作。

Web 工作台目前聚焦五个功能区：

1. **首页**：显示服务、运行时、适配器和资产状态。
2. **验证**：检查 Robot Contract、场景参数和 Go2/Go2W 资产。
3. **训练配置**：选择 MJLab 与 PPO，调整环境、算法参数及奖励项的启用状态和权重。
4. **训练**：创建/停止 native MJLab worker，查看真实日志、进度和 metrics 曲线。
5. **仿真**：通过 MuJoCo 进行基础遥控、地图切换和导航会话入口。

## 已实现能力

- FastAPI 控制面、Electron 桌面启动器和可配置本地端口。
- Go2/Go2W Robot Contract、资产清单和基础验证接口；验证页可导入用户自己的 URDF/MJCF 与相对 mesh 资源，保存到工作区并生成 Contract 草稿，preset 仅作为快捷模板。
- 首页支持导出/导入项目 ZIP 包，包内可携带机器人资产、Contract、MJLab training recipe 和 MuJoCo 场景。
- 唯一训练框架为 native MJLab；当前注册并可运行的算法为 PPO。
- MJLab worker 的运行时预检、训练任务状态、日志、metrics 和 artifact 索引。
- MuJoCo 基础仿真会话，支持 flat、rough、stairs、warehouse 地图及基础/导航模式数据契约。
- 导入资产可在 MuJoCo 仿真下选择和运行；native MJLab 训练仍只对已有机器人专属任务映射的 Go2/Go2W 开放。
- Web 与桌面启动器采用接近 MJLab Play/Viser 的白色、浅灰、蓝色控件风格。
- 训练配置支持 JSON 导入/导出，导出的配置可作为后续 CLI 的输入。
- Windows Online 7z 打包脚本，以及按需配置 Python、Torch、MJLab 的流程。

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

| 组件 | 0.5.0 目标版本 |
| --- | --- |
| Python | 3.12.13 |
| uv | 0.11.8 |
| Torch | 2.11.0+cu128（GPU）或 2.11.0+cpu |
| MJLab | 1.6.0 |
| MuJoCo / MuJoCo-Warp | 3.11.0 |

Online 包不内置完整 Torch/MJLab 安装，仅携带 uv、CPython 基础文件和固定源码快照；用户点击配置后才安装依赖。国内环境默认使用清华 PyPI 和上海交通大学 PyTorch 镜像，仍需用户自行提供兼容的 NVIDIA 驱动。

## 后续路线

优先完成 GPU 短 smoke 与长训练验收、Go2/Go2W 的评估和导航闭环、ONNX 数值一致性验证，再扩展通用导航任务、URDF-Studio 3D 工作区、UniLab/RoboLab adapter、CLI 和人工确认的实机部署包。每项扩展都必须先通过同一 Robot/Scenario/Policy 契约和可复现测试。

## 事实源

- [QUADRUPED_ASSET_INVENTORY.json](./QUADRUPED_ASSET_INVENTORY.json)
- [QUADRUPED_ASSET_INVENTORY.md](./QUADRUPED_ASSET_INVENTORY.md)
- [README.md](./README.md)
- [docs/DISTRIBUTION.md](./docs/DISTRIBUTION.md)
- [docs/DESKTOP_SETUP.md](./docs/DESKTOP_SETUP.md)
