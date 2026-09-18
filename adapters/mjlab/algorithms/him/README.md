# HIM (Hybrid Internal Model) Plugin

Registry key: `him`

## Upstream provenance

- **Source**: UniLab `him_ppo`（HIMLoco 谱系的 UniLab 清洁实现）
  （仓库内参考副本：`00_resources/unilab_new/UniLab/src/unilab/algos/him_ppo/`）。
- **License**: Apache-2.0（`00_resources/unilab_new/UniLab/LICENSE`）。
- **提取范围**: `actor_critic.py` / `estimator.py` / `storage.py` / `algorithm.py`
  全部纯 torch 核心；UniLab 侧 `runner.py`（hydra/env 训练循环）未提取，
  runner 侧接入为后续轮次（见下）。

## What's inside

| File | Contents |
| --- | --- |
| `actor_critic.py` | `HIMActorCritic`（估计器速度/latent 拼接 actor + 特权 critic，提取原件） |
| `estimator.py` | `HIMEstimator`（速度估计 + sinkhorn-kmeans 交换预测 latent）、`get_activation`、`sinkhorn`（提取原件） |
| `storage.py` | `HIMRolloutStorage`（含 `next_privileged_observations` 的时序缓冲，提取原件） |
| `algorithm.py` | `HIMPPO`（自足 PPO update，提取原件） |
| `models.py` | 家族模型面（对提取原件的 re-export） |
| `config.py` | `HimAlgorithmConfig` 超参 schema（默认值逐项对齐 UniLab 构造器） |
| `__init__.py` | `HIMPlugin`（插件协议实现）+ 模块级 `PLUGIN` 单例 |

## Plugin protocol

`HIMPlugin` 实现 `adapters.mjlab.algorithms.base.AlgorithmPlugin`：

- `build_actor_critic(obs_dim, action_dim, cfg)` → `HIMActorCritic`
  （`obs_dim` 必须是 `one_step_obs_dim`（默认 45）的整数倍——历史观测约定）；
- `build_storage(cfg)` → `HIMRolloutStorage`（家族原生 storage，含交换预测所需的
  next-privileged 槽位）；
- `build_optimizer(params, cfg)` → Adam（默认 lr 1e-3，与 `HIMPPO` 一致）；
- `export_onnx(path, model=None)` → 部署契约 `obs_history -> actions` 的确定性
  ONNX（`act_inference` 路径：estimator 前向 + actor 均值）。

## Runner integration status

纯 torch 核心已注册、可按名解析与自证导出；接入 mjlab/RSL-RL runner 循环
（rsl_rl 侧 actor 包装 + profile 绑定）为下一轮工作，当前 `variants` 指向
提取核心类本身。
