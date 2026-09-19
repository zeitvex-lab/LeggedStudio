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

## mjlab / RSL-RL runner integration (本轮)

标准 rsl_rl 5.x dispatch：`OnPolicyRunner` 用 `resolve_callable(cfg.algorithm.class_name)`
解析算法类、`PPO.construct_algorithm(obs, env, cfg, device)` 按 `cfg.actor/critic.class_name`
构建模型——本插件以此模式接入：

| Class | Role |
| --- | --- |
| `models.HIMActorModel` | rsl_rl `MLPModel` 子类；"actor" 观测组即 HIMLoco 堆叠历史（45-D 帧 × 6，最新帧在前，部署契约 `himloco_45_hist6`，ONNX 单输入 `obs_history[270] -> actions[12]`）；内部持有 `HIMEstimator`（act 时 no_grad 前向，PPO 梯度不流入） |
| `algorithms.HimPPO` | `Go2AuxiliaryPPO`（rsl_rl `PPO`）子类，`auxiliary_kind="him"`；`process_env_step` 把每步 next-critic-obs 写入预分配缓冲（外部分配 + `copy_` 填充，规避 inference-mode 张量进 autograd），`update()` 在 PPO 之后按同数量 minibatch 跑 estimator 联合更新（速度回归 + sinkhorn 交换预测），返回 `him_estimation` / `him_swap` 指标 |

go2 侧接线（`assets/robots/unitree_go2/training/`）：

- env 变体 `unitree_go2_him_env_cfg`（`tasks/locomotion/variants.py` kind `"him"`）：
  actor 组 = `mdp.Go2HimHistory`（自带噪声采样并缓存当前帧，HIMLoco `obs_buf` 语义
  newest-first 含当前帧）；critic 组 = `mdp.go2_him_privileged_observation`
  （48-D：同一噪声帧 + `lin_vel*2.0`，偏移精确复现估计器切片 vel `[45:48]` /
  交换目标 `[3:48]`，盲版省略上游 3-D disturbance/187-D height scan——估计器不索引、
  critic 宽度不属部署契约）；命令/摩擦等按 HIMLoco legacy（yaw ±π、heading、
  friction 0.2–1.25），reward 核复用同族已标定的 `go2_source_*` 形状层。
- runner cfg `go2_him_runner_cfg`（`training/config.py`）：算法/actor/critic class_name
  走注册表 variant（`adapters/mjlab/algorithms/registry.json` him base）；
  超参对齐 HIMLoco legacy PPO（adaptive 1e-3、KL 0.01、entropy 0.01、gamma 0.99）。
- profile `profiles/go2-him.json`（`algorithm_plugin: "him"`，history_length 6）。

## Honest boundaries（诚实边界）

- **两阶段训练**：上游 HIMLoco/UniLab 的 estimator 可两阶段（先 estimator 预训练、
  再联合更新）。本接线只覆盖**联合阶段**（PPO 与 estimator 同批交替更新，与 UniLab
  `HIMPPO.update` 逐 minibatch `estimator.update` 同构）；estimator 预训练阶段未接线，
  冷启动 estimator 对初始速度估计有偏差——依赖联合阶段自行收敛（上游 uniLab 主流程
  亦为联合更新，属可接受捷径，特此如实标注）。
- **timeout 行**：UniLab 版支持 `time_out_bootstrap_obs` 修正交换目标；mjlab wrapper
  只提供 `time_outs`（奖励 bootstrap 由 rsl_rl 原生处理），timeout 行的 next-priv
  使用 reset 后观测（与 HIMLoco 原 rsl_rl 存储语义一致）。
- **history reset**：训练侧 env reset 清零历史缓冲（本仓 `go2_history_reset: zero`
  约定）；HIMLoco 原 reset 不清零（旧帧自然滚出）。部署侧若与 rl_sar 契约
  （`history_init: repeat_first`）不一致，需在产物契约按训练语义声明。
- **produced 产物观测布局**：B44 形状表无法表达「帧×历史」契约，produced deploy
  仍标 `observation_kind: unknown`；B11 评测用包内 `go2-rlsar-himloco` 契约条目
  （逐项同源：命令/IMU/关节缩放与训练 env 完全一致）+ 显式 `--policy` 指向产物 ONNX。
