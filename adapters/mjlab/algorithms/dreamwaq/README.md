# DreamWaQ Plugin

Registry key: `dreamwaq`

## Upstream provenance

- **Source**: DreamWaQ 盲式运动控制参考实现（仓库内参考副本：
  `00_resources/Dreamwaq`，对应训练档案
  `assets/robots/unitree_go2/training/profiles/go2-dreamwaq.json` /
  `go2-amp-dreamwaq.json`）。
- **License**: BSD-3-Clause——vendored 副本无 LICENSE 文件，但
  `00_resources/Dreamwaq/setup.py` 声明 `license="BSD-3-Clause"`
  （legged_gym 谱系脚手架）。此取证口径已如实写入 `DreamWaQPlugin.license`。
- **迁移链**: 源算法类原居 `assets/robots/unitree_go2/training/source/local_tasks/learning/{algorithms,models}.py`，
  现迁入本目录；`local_tasks` 留薄 re-export 以保持 entrypoint 兼容。

## What's inside

| File | Contents |
| --- | --- |
| `models.py` | `DreamWaQVAE`（源 CENet 等价实现）、`DreamWaQActorCritic`、`DreamWaQActorModel`（RSL-RL 侧条件 actor） |
| `algorithms.py` | `DreamWaQAlgorithm`（独立 VAE 更新器）、`DreamWaQPPO` / `AmpDreamWaQPPO` |
| `config.py` | `DreamWaQAlgorithmConfig` 超参 schema |
| `__init__.py` | `DreamWaQPlugin`（插件协议实现）+ 模块级 `PLUGIN` 单例 |

## Plugin protocol

- `build_actor_critic(obs_dim, action_dim, cfg)` → `DreamWaQActorCritic`；
- `build_storage(cfg)` → `Go2RolloutStorage`；
- `build_optimizer(params, cfg)` → Adam（VAE 专用 1e-3）；
- `export_onnx(path, model=None)` → `(actor, history) -> actions` 确定性
  ONNX（VAE 后验均值路径，`explicit || latent || actor` 输入布局）。

## Source-compatible details worth keeping

- CENet 编码器 `history->128->64`，两层后都有 ELU（含 64 维瓶颈层）；
- 潜码 16 维 + 显式速度码 3 维，解码目标为当前观测；
- 损失 = 速度监督 + 重构 + 潜码 KL（显式速度分支**无** KL 惩罚）；
- PPO 优化器刻意排除 VAE 参数（VAE 由独立 1e-3 优化器更新）。
