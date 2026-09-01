# Python 版本决策

**更新时间**：2026-08-31  
**当前决策**：Legged Studio 控制面与 MVP MJLab adapter 统一使用 Python 3.12.x（`>=3.12,<3.13`）

## 为什么选 3.12

- 本机开发环境已验证为 Python 3.12.2。
- Microduck RL 项目的锁定范围是 `>=3.12,<3.13`，其 smoke/export 经验可直接作为对照。
- 当前 MJLab 接受 3.12；控制面 FastAPI/Pydantic 测试已在 3.12 通过。
- 3.12 能让控制面和首个 Go2/MJLab adapter 使用同一主版本，同时仍保持进程隔离。

## 为什么暂不统一到 3.13

本地 ComfyUI 的 Python 3.13.11 只能证明便携运行时可分发，不能证明 MJLab、MuJoCo Warp、Torch、BAM 和导出链兼容。当前 Microduck RL 组合明确排除了 3.13；其中 BAM 体现的是 `<3.13` 上界，并不单独要求 Python 必须是 3.12。因此 3.13 只能作为实验矩阵，不能替换当前产品基线。

3.13 并非被否决：当前 `mjlab_new/mjlab` 的 `.python-version` 已是 3.13，包声明支持 `>=3.10,<3.14`。真正的阻断来自我们要参考的 Microduck/BAM 组合，而不是 MJLab 核心。后续可以为“当前 MJLab + Go2”单独建立 3.13 lock，与 3.12 基线做相同 smoke 对比。

提升到 3.13 前必须在独立环境完成：依赖锁解析、MJLab 64-env/5-iteration smoke、ONNX export、ORT replay、控制面测试以及 Windows 打包测试。全部通过后再修改 `pyproject.toml`，不能只改文档版本号。

## 多后端原则

“统一 3.12”只适用于控制面和 MVP 主线，不意味着所有历史后端共用一个环境。RoboGauge 仍用 Python 3.11 adapter，Isaac Gym legacy 仍用 3.8 adapter，Isaac Lab 使用 vendor 环境。各 adapter 只通过版本化 JSON、Artifact 和日志事件与控制面通信。

## 事实源

```toml
requires-python = ">=3.12, <3.13"
```

版本范围以 `pyproject.toml` 为机器事实源；本文解释决策，不重复维护依赖锁。
