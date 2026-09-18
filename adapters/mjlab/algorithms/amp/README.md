# AMP (Adversarial Motion Prior) Plugin

Registry key: `amp`

## Upstream provenance

- **Source**: LeggedGym-Ex go2 AMP 变体（`00_resources/LeggedGym-Ex`，
  对应训练档案 `go2-amp-cts.json` / `go2-amp-dreamwaq.json` / `go2-amp-ts.json`），
  并参考 mjlab AMP 实现（`00_resources/AMP_mjlab`，G1 谱系）。
- **License**: BSD-3-Clause（`00_resources/LeggedGym-Ex/LICENSE`）；
  `00_resources/AMP_mjlab` vendored 副本无顶层 LICENSE（其 rsl_rl 谱系为
  BSD-3-Clause）。取证口径如实写入 `AmpPlugin.license`。
- **迁移链**: 源算法类原居 `assets/robots/unitree_go2/training/source/local_tasks/learning/{algorithms,models}.py`，
  现迁入本目录；`local_tasks` 留薄 re-export 以保持 entrypoint 兼容。

## What's inside

| File | Contents |
| --- | --- |
| `models.py` | `AmpDiscriminator`（转移级判别器 + LSGAN 损失 + 梯度惩罚 + 塑形奖励） |
| `algorithms.py` | `AmpAlgorithm`（独立判别器更新器）、`AmpPPO`（AMP 组合进共享 PPO 运行时） |
| `config.py` | `AmpAlgorithmConfig` 超参 schema |
| `__init__.py` | `AmpPlugin`（插件协议实现）+ 模块级 `PLUGIN` 单例 |

## Plugin protocol

- `build_actor_critic(obs_dim, action_dim, cfg)` → `AmpDiscriminator`
  （本家族的“模型”即判别器；输入宽度为 AMP 状态维 31）；
- `build_storage(cfg)` → `Go2AmpReplayBuffer`（家族原生存储；`as_rollout`
  可切换为 `Go2RolloutStorage`）；
- `build_optimizer(params, cfg)` → 判别器 Adam（1e-4）；
- `export_onnx(path, model=None)` → `(amp, next_amp) -> logit` 判别器打分
  ONNX（可复用于 sim2sim 奖励整形审计）。

## Composition semantics

AMP 是**组合型**插件：`AmpCtsPPO` / `AmpDreamWaQPPO` / `AmpTeacherStudentPPO`
分别是 cts / dreamwaq / distill 家族混入 AMP 之后的变体（`uses_amp=True`，
1M 回放缓冲，判别器学习率跟随算法学习率）。注册表 variants 一并登记。

## Source-compatible details worth keeping

- 判别器输入为 `(state, next_state)` 拼接，LeakyReLU + 最小二乘目标
  （专家 +1 / 策略 -1），梯度惩罚权重 10；
- 塑形奖励 `0.02 * coef * clamp(1 - 0.25*(logit-1)^2, min=0)`；
- 运行均值方差归一器裁剪到 ±10，统计量随 checkpoint 持久化；
- 专家数据经 `GO2_MOTION_DIR` 显式 opt-in（缺失时保留有限冒烟路径）。
