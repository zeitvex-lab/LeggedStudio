# HORA (Hybrid Omniscient Retirement Adaptation) Plugin

Registry key: `hora`

## Upstream provenance

- **Source**: UniLab `hora`（共享主干 + 特权潜变量适配的 HORA 实现）
  （仓库内参考副本：`00_resources/unilab_new/UniLab/src/unilab/algos/hora/`，3845 行）。
- **License**: Apache-2.0（`00_resources/unilab_new/UniLab/LICENSE`）。
- **提取范围（~950 行核心）**: `models.py`（`HoraSharedActorCritic` /
  `ProprioAdaptTConv` / actor-critic 包装）、`ppo.py`（`HoraPPO` + dict 观测
  `HoraRolloutStorage` + `build_hora_ppo`）、`modules.py`
  （`EmpiricalNormalization` + 最小 `GaussianDistribution`）、`distill.py`
  （`HoraLatentDistiller` stage-2 latent 对齐）。
- **未提取**（见各文件头 TODO）: AMP 演示判别器、多阶段蒸馏训练器、RND 内在
  奖励、symmetry 增强、multi-GPU / torch.compile 快路径、SAC 分支。

## What's inside

| File | Contents |
| --- | --- |
| `models.py` | `HoraSharedActorCritic`（共享主干核心）、`HoraActorModel` / `HoraCriticModel`（提取原件） |
| `ppo.py` | `HoraPPO`、`HoraRolloutStorage`、`build_hora_ppo`（提取原件） |
| `modules.py` | `EmpiricalNormalization`、`GaussianDistribution`（提取原件） |
| `distill.py` | `HoraLatentDistiller`、`HoraDistillConfig`（提取原件） |
| `algorithms.py` | 家族算法面（对提取原件的 re-export） |
| `config.py` | `HoraAlgorithmConfig` 超参 schema（默认值逐项对齐 UniLab 构造器） |
| `__init__.py` | `HoraPlugin`（插件协议实现）+ 模块级 `PLUGIN` 单例 |

## Plugin protocol

`HoraPlugin` 实现 `adapters.mjlab.algorithms.base.AlgorithmPlugin`：

- `build_actor_critic(obs_dim, action_dim, cfg)` → `HoraSharedActorCritic`
  （`cfg` 可携带 `priv_info_dim` / `use_student_encoder` 等家族维度）；
- `build_storage(cfg)` → `HoraRolloutStorage`（dict 观测 spec：
  `actor` + `priv_info`）；
- `build_optimizer(params, cfg)` → Adam（默认 lr 1e-3，与 `HoraPPO` 一致）；
- `export_onnx(path, model=None)` → 部署契约 `(actor, priv_info) -> actions`
  的确定性 ONNX（`policy_mean_from_tensors` 教师路径均值头）。

## Runner integration status

纯 torch 核心已注册、可按名解析与自证导出；rsl_rl 侧 actor/critic 包装绑定
profile（`HoraActorModel` 已就绪）为下一轮工作，当前 `variants` 指向提取核心类。
