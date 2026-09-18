# CTS (Concurrent Teacher-Student) Plugin

Registry key: `cts`

## Upstream provenance

- **Source**: LeggedGym-Ex go2 CTS/TS 任务（并发教师-学生框架）
  （仓库内参考副本：`00_resources/LeggedGym-Ex`，对应训练档案声明
  `assets/robots/unitree_go2/training/profiles/go2-cts.json` 的 `source` 字段）。
- **License**: BSD-3-Clause（`00_resources/LeggedGym-Ex/LICENSE`，
  Copyright (c) 2024 Yasen Jia）。
- **迁移链**: 源算法类原居 `assets/robots/unitree_go2/training/source/local_tasks/learning/{algorithms,models}.py`，
  现迁入本目录；`local_tasks` 留薄 re-export 以保持 entrypoint 兼容。

## What's inside

| File | Contents |
| --- | --- |
| `models.py` | `CtsActorCritic`（源 ActorCriticCTS 等价实现）、`CtsActorModel` / `CtsCriticModel` / `CtsStudentActorModel`（RSL-RL 侧条件 actor/critic） |
| `algorithms.py` | `CtsAlgorithm`（独立更新器）、`CtsPPO` / `AmpCtsPPO`（基于共享 `Go2AuxiliaryPPO` 的 mjlab 训练类） |
| `config.py` | `CtsAlgorithmConfig` 超参 schema（默认值逐项对齐源任务常量） |
| `__init__.py` | `CtsPlugin`（插件协议实现）+ 模块级 `PLUGIN` 单例 |

## Plugin protocol

`CtsPlugin` 实现 `adapters.mjlab.algorithms.base.AlgorithmPlugin`：

- `build_actor_critic(obs_dim, action_dim, cfg)` → `CtsActorCritic`
  （`cfg` 可携带 `privileged_dim` / `critic_dim` / `history_dim` 家族维度）；
- `build_storage(cfg)` → `Go2RolloutStorage`；
- `build_optimizer(params, cfg)` → Adam（默认 lr 1e-3）；
- `export_onnx(path, model=None)` → 部署契约 `(actor, history) -> actions`
  的确定性 ONNX（学生编码器路径——源 `act_inference` 从不部署特权教师）。

## Source-compatible details worth keeping

- 教师/学生编码器各为 `(512, 256) -> 32` 的 L2 归一化潜空间；
- PPO 分组加权：教师 3/4、学生 1/4 分组等权（见 `CtsPPO.update`）；
- 蒸馏损失权重 0.1、熵系数 0.01（`CtsAlgorithm.update`）；
- AMP 组合（`AmpCtsPPO`）复用 31 维判别器状态与 1e-3 学习率。
