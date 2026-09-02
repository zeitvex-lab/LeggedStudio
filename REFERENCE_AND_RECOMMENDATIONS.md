# Legged Studio 参考清单与实施建议

**产品版本**：0.4.0  
**更新日期**：2026-09-02  
**依据**：[PROJECT_VISION_LEGGED_STUDIO.md](./PROJECT_VISION_LEGGED_STUDIO.md)

本文把 `C:\Users\31560\Documents\00_open` 中收集的项目按“当前已接入、实现参考、后续适配”分类。存在源码或资产只证明参考价值，不等于 Legged Studio 已支持或已完成 L4 闭环。

## 当前产品证据

| 证据级别 | 含义 | 0.4.0 结论 |
| --- | --- | --- |
| L1 | 文件、资产或声明存在 | 只能证明候选来源 |
| L2 | 已读取源码、配置或测试 | 可以说明静态行为 |
| L3 | 本机定向测试或接口探测 | 只对当前环境成立 |
| L4 | 训练、导出、仿真/部署链路完整通过 | 才能宣称闭环支持 |

当前已验证的是控制面单元测试、MJLab 适配器测试、Python/JS 编译检查、发布检查、健康接口、地图接口和浏览器页面 smoke。GPU 长训练、ONNX 数值 replay、复杂导航、实机控制和非 Go2/Go2W 机器人仍未完成 L4 验收。

## 已接入的主线

### `legged_studio`

项目已有统一 FastAPI 控制面、Electron 启动器、五功能 Web Workbench、MJLab 训练 worker、MuJoCo 仿真 API、Go2/Go2W 契约和 Windows Online 打包流程。训练与控制面通过进程边界隔离，仿真仍保留 MuJoCo。

### `mjlab_new/mjlab`

这是当前唯一的训练主线和 Play/Viser 视觉参考。其 manager-based 环境、runner、Torch/Warp/MuJoCo-Warp 依赖应继续放在 `adapters/mjlab` 的锁定环境中，不复制第二套 `mjlab` 目录。0.4.0 只把 PPO 标记为可运行算法。

### `uni_rl/unitree_rl_mjlab`

这是 Go2 任务扩展和资产映射的源码来源。当前 worker 已围绕 Go2/Go2W 接入；新增任务必须通过 Robot Contract、预检和独立 smoke。

## Web 与交互参考

| 项目 | 借鉴内容 | 当前边界 |
| --- | --- | --- |
| `urdf_tool/URDF-Studio` | URDF/MJCF 解析、资源检查、未来模型编辑器 | 当前仅作为验证和集成参考 |
| `auto_web/ReinforceUI-Studio` | 训练控制台、任务状态、指标曲线 | 已转化为本项目训练页的数据需求 |
| `references_1000framesai` | 基础仿真遥控、地图和导航交互 | 只借鉴流程，不作为整体视觉基线 |
| `auto_web/RL-Factory` | 模块化训练配置和实验管理 | 奖励/算法字段仍以 MJLab recipe 为准 |

Web 视觉基线采用 MJLab Play/Viser 的浅色工作区：白色或浅灰场景、蓝色主操作、灰色边框和紧凑浮层。训练配置与仿真页面保持分离。

## 后续适配参考

| 项目 | 适合复用的内容 | 接入条件 |
| --- | --- | --- |
| `lain_job/RoboLab` | PolicyArtifact、工作流、部署抽象和 Web 任务组织 | 先完成契约字段对齐与许可证确认 |
| `unilab_new/UniLab` | Sim2Sim、CPU 仿真和后续 adapter 结构 | 不改变当前 MJLab 主线，单独隔离环境 |
| `rc_old/RC_WheelLeg/.../rc_mjlab` | 轮足任务、关节/动作映射和部署约束 | 先新增 Robot Contract fixture 和 smoke |
| `references_1000framesai` | 地图任务与导航交互 | 需要明确复杂地图规划和终止条件 |

Isaac Gym、Isaac Lab、RoboGauge、MATRiX 等不属于 0.4.0 默认后端。它们可以提供算法、仿真或部署参考，但不能在文档或 UI 中被写成当前已支持能力。

## 契约与复用原则

1. Robot Contract 是模型、关节顺序、观测、动作、控制频率和资产哈希的唯一入口。
2. Scenario Contract 统一地图、命令、随机种子、扰动和终止条件。
3. PolicyArtifact 必须记录 recipe、输入输出布局、normalizer、依赖锁和验证结果。
4. 控制面只编排任务，不直接 import 重型训练依赖；MJLab worker 负责训练执行。
5. 新增算法、机器人或地图先提供可失败的 preflight 和短 smoke，再接入 Web。
6. 源码、模型、mesh 和第三方 SDK 在确认许可证前只保留路径、哈希和引用，不复制进可分发包。

## 推荐验收顺序

```text
Go2/Go2W asset validation
  -> MJLab PPO short smoke (CPU/GPU)
  -> live logs and metrics
  -> MuJoCo basic replay
  -> evaluation/navigation contract checks
  -> ONNX/export numerical validation
  -> manually approved deployment package
```

当前最有价值的工程工作是补齐 GPU smoke/长训练证据、真实评估与导航任务、ONNX 数值一致性和 CLI 调用层，而不是并行引入新的训练框架。每次发布都应运行根项目与 `adapters/mjlab` 测试、`release:check`、编译检查及浏览器 smoke，并在文档中记录实际结果。
