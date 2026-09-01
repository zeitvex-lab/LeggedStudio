# Legged Studio 当前状态

**更新时间**：2026-08-31  
**阶段**：Phase 0 - 资产工作台/API  
**状态**：后端、Contract 和 Web 工作台已验证；Electron GUI 待人工验收

## 已完成

- 只读 inventory API：健康检查、摘要、筛选、family 查询和静态工作台
- 浏览器资产工作台：107 条相关记录、82 个机器人本体、28 个 family
- Robot Contract/AssetRecord Pydantic 模型和 S/M/L 边界校验
- Electron 默认启动 `backend/app.py:8000` 并检查 `/api/health`
- Python 运行时锁定 `>=3.12,<3.13`
- backend 单元测试 5/5、Contract selfcheck、FastAPI/stdlib HTTP smoke、JS 语法检查通过

## 复用路线

| 产品能力 | 复用来源 | 当前边界 |
|---|---|---|
| 资产解析/3D | `urdf_tool/URDF-Studio` | 待做 adapter；不自研 XML parser/viewer |
| Go2 训练 | `mjlab_new/mjlab` | 待 Python 3.12 独立 worker smoke |
| Workflow/Artifact | `lain_job/RoboLab` | 提取契约和事件语义，不整包复制 |
| Sim2Sim/评估 | UniLab、RoboGauge | Phase 2 独立 adapter |
| 部署安全 | Microduck、Unitree deploy | 复用生命周期/映射原则，不泛化专属 tensor |

## 待完成

- Electron 窗口、进程退出和端口冲突的人工 GUI 验收
- 冻结 Go2 Robot Contract YAML 与跨映射测试
- Python 3.12 MJLab 64-env/5-iteration smoke、ONNX export 和 ORT replay
- URDF Studio parser/viewer adapter
- mesh 质量 worker 与几何 fixture

Python 3.13 目前没有进入交付基线：Microduck RL 明确要求 `<3.13`，且 MJLab/Torch/Warp 组合尚未完成 3.13 全链路验证。
