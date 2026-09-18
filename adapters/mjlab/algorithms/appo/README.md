# APPO (Asymmetric Asynchronous PPO, IMPACT-style) Plugin

Registry key: `appo`

## Upstream provenance

- **Source**: UniLab `appo`（IMPACT, Luo et al. 2020 风格的异步非对称 PPO）
  （仓库内参考副本：`00_resources/unilab_new/UniLab/src/unilab/algos/appo/`，1701 行）。
- **License**: Apache-2.0（`00_resources/unilab_new/UniLab/LICENSE`）。
- **提取范围（~700 行核心）**: `learner.py`（`APPOLearner`：V-trace 重要性采样
  修正 + target network 软更新 + 自适应 KL 学习率；`vtrace_advantages`）、
  `models.py`（`APPOActor` 本体观测 actor / `APPOCritic` 特权观测 critic，
  非对称 actor-critic + `EmpiricalNormalization` / `GaussianDistribution`
  最小纯 torch 实现）。
- **未提取（属训练链/IPC，下轮接）**: `runner.py` / `worker.py`（子进程
  rollout 采集）、`staging.py`（`RolloutStagingPool` 有界缓冲）、`runtime.py`。

## What's inside

| File | Contents |
| --- | --- |
| `learner.py` | `APPOLearner`、`vtrace_advantages`（提取原件） |
| `models.py` | `APPOActor`、`APPOCritic`、`EmpiricalNormalization`、`GaussianDistribution`（提取原件） |
| `algorithms.py` | 家族算法面（对提取原件的 re-export） |
| `config.py` | `AppoAlgorithmConfig` 超参 schema（默认值逐项对齐 UniLab 构造器） |
| `__init__.py` | `AppoActorCritic`（非对称组合包装）+ `AppoPlugin`（插件协议实现）+ `PLUGIN` 单例 |

## Plugin protocol

`AppoPlugin` 实现 `adapters.mjlab.algorithms.base.AlgorithmPlugin`：

- `build_actor_critic(obs_dim, action_dim, cfg)` → `AppoActorCritic`
  （组合包装：proprio `APPOActor` + 特权 `APPOCritic`；`cfg` 可携带
  `critic_dim` —— 非对称观测维本是 APPO 的设计点）；
- `build_storage(cfg)` → 共享 `Go2RolloutStorage`（UniLab 侧异步
  staging/worker 未提取，先给适配器侧标准容器）；
- `build_optimizer(params, cfg)` → Adam（默认 lr 1e-3，与 `APPOLearner` 一致）；
- `export_onnx(path, model=None)` → 部署契约 `actor_obs -> actions` 的确定性
  ONNX（actor 均值头）。

## Runner integration status

纯 torch 核心已注册、可按名解析与自证导出；异步采集链（worker/staging/runtime）
与 profile 绑定为下一轮工作。
