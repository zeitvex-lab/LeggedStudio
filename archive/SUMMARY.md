# Legged Studio 工作摘要

**更新时间**：2026-08-31

Legged Studio 已建立 Phase 0 只读控制面：统一 inventory、资产 API、浏览器工作台、Electron 壳和 Robot Contract 基础模型。运行时锁定 Python 3.12.x；3.13 仅进入后续兼容性验证。

## 已验证

- 107 条四足相关记录、82 个机器人本体、28 个 family 可加载与筛选
- backend 单元测试 5/5
- FastAPI 与标准库 HTTP fallback smoke
- Contract selfcheck 和 S/M/L 边界
- Web/Electron JavaScript 语法

## 尚未完成

- Electron GUI 生命周期人工验收
- Go2 完整 Robot Contract 和跨训练/仿真/部署映射
- MJLab 64-env/5-iteration 训练、ONNX export、ORT replay
- URDF Studio parser/viewer adapter
- mesh 质量 worker、Windows 便携打包、Sim2Sim 和实机测试

## 实施主线

资产能力复用 URDF Studio，Go2 训练复用 MJLab，Workflow/Artifact 语义参考 RoboLab。UniLab 与 RoboGauge 延后为独立 adapter；Microduck 和 Unitree deploy 只提供部署生命周期、映射及数值回放参考。控制面不承载这些框架的依赖。
