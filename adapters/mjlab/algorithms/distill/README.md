# Distill (Teacher-Student) Plugin

Registry key: `distill`

## Upstream provenance

- **Source**: LeggedGym-Ex go2 CTS/TS 教师-学生框架（`00_resources/LeggedGym-Ex`，
  对应训练档案 `go2-ts.json` / `go2-ts-student.json` / `go2-amp-ts.json`）。
- **License**: BSD-3-Clause（`00_resources/LeggedGym-Ex/LICENSE`）。
- **迁移链**: 源算法类原居 `assets/robots/unitree_go2/training/source/local_tasks/learning/{algorithms,models}.py`，
  现迁入本目录；`local_tasks` 留薄 re-export 以保持 entrypoint 兼容。

## What's inside

| File | Contents |
| --- | --- |
| `models.py` | `TeacherStudentActorCritic`（地形 187 维 + 特权 74 维教师编码器 + LSTM 学生编码器）、`TeacherActorModel` / `StudentActorModel`（RSL-RL 侧条件 actor；学生带 `as_recurrent_onnx`） |
| `algorithms.py` | `TeacherStudentAlgorithm`（独立蒸馏更新器）、`TeacherStudentPPO` / `AmpTeacherStudentPPO` |
| `config.py` | `DistillAlgorithmConfig` 超参 schema |
| `__init__.py` | `DistillPlugin`（插件协议实现）+ 模块级 `PLUGIN` 单例 |

## Plugin protocol

- `build_actor_critic(obs_dim, action_dim, cfg)` → `TeacherStudentActorCritic`；
- `build_storage(cfg)` → `Go2RolloutStorage`（学生任务默认 50 步 rollout）；
- `build_optimizer(params, cfg)` → Adam（蒸馏 1e-3；教师 PPO 用 1e-5）；
- `export_onnx(path, model=None)` → `(actor, history) -> actions` 帧窗学生
  ONNX（外部三态 LSTM 契约 ``obs,h,c -> actions,he,ce`` 由
  `StudentActorModel.as_recurrent_onnx` 提供，与 runner 侧导出一致）。

## Source-compatible details worth keeping

- 教师特征 = `terrain_encoder(187->16) || privileged_encoder(74->16)`；
- 学生编码器单层 LSTM(256)（部署侧为三层变体）+ `(256,128)` 头；
- 蒸馏目标为教师特征（detach）的 MSE；
- 学生任务教师 checkpoint 经 `GO2_TS_TEACHER_CHECKPOINT` 显式 opt-in；
  `VelocityDistillationRunner` 是该家族的专用学习回路（非 PPO）。
