"""Go2 的 RL runner 配置（薄委托：族级 Skills 的 runner 工厂）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/velocity/runner.py`。本模块只剩：

1. **基座**：本机型的 source-PPO 基座（`unitree_go2_source_ppo_runner_cfg` —— 关观测
   归一化、不裁动作、按源超参），供七个变体与 `local_tasks.robot_profiles` 共用；
2. **变体数据**：`VARIANT_RUNNERS`（`tasks/locomotion/variants_profile.py`：超参 +
   算法侧符号串 + std 下限表）；
3. **入口函数**（公开名不动，profile 的 `entrypoints.runner` 照旧解析到这里）。

原先 `unitree_go2_custom_runner_cfg` 里的机制（关归一化 / 不裁动作 / 换分布 std 下限 /
学生更长 rollout / 逐 kind 的学习率与种子）已上移为族级机制。
"""

import sys
from pathlib import Path

# 仓库根自举（见 kits/quadruped_kit 模块注释）：worker / schema-dump / 冒烟三种运行环境
# 都只把 training/source 或包根放进 sys.path；沿目录向上找 adapters/mjlab，对 assets 源树
# 与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
  if (_parent / "adapters" / "mjlab").is_dir():
    if str(_parent) not in sys.path:
      sys.path.insert(0, str(_parent))
    break

from mjlab.rl import RslRlOnPolicyRunnerCfg  # noqa: E402

from adapters.mjlab.kits import quadruped_kit as kit  # noqa: E402
from adapters.mjlab.kits.quadruped_kit.skills.velocity import runner as kit_runner  # noqa: E402

from ..tasks.locomotion.variants_profile import VARIANT_RUNNERS  # noqa: E402


def unitree_go2_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  """Create RL runner configuration for Unitree Go2 velocity task.

  **委托** ``kits/quadruped_kit.ppo_runner_cfg``（四足框架层唯一真值；与 lite3 / b2 / go1
  同一先例）。本包**唯一差异**是 ``save_interval=50``（Kit 默认 100，即 lite3/b2/go1 语义），
  由参数携带。等价性由迁移前后的 ``dataclasses.asdict`` dump 逐字段比对（0 差异）保证。
  """
  return kit.ppo_runner_cfg("go2_velocity", save_interval=50)


def unitree_go2_source_ppo_runner_cfg(
  *,
  learning_rate: float = 1.0e-3,
  max_iterations: int = 15_000,
  save_interval: int = 100,
  seed: int = 1,
  symmetry_func: str | None = None,
) -> RslRlOnPolicyRunnerCfg:
  """Create PPO config matching the source RSL-RL observation handling.

  源策略直接消费环境已经 scaled/clipped 的观测，不做 running 归一化；也不裁动作。
  `local_tasks.robot_profiles` 的八个档位与七个算法变体都从这里起步。
  """
  cfg = unitree_go2_ppo_runner_cfg()
  cfg.actor.obs_normalization = False
  cfg.critic.obs_normalization = False
  cfg.clip_actions = 100.0
  cfg.algorithm.learning_rate = learning_rate
  cfg.max_iterations = max_iterations
  cfg.save_interval = save_interval
  cfg.seed = seed
  if symmetry_func is not None:
    cfg.algorithm.symmetry_cfg = {
      "data_augmentation_func": symmetry_func,
      "use_data_augmentation": False,
      "use_mirror_loss": True,
      "mirror_loss_coeff": 1.0,
    }
  return cfg


def unitree_go2_custom_runner_cfg(kind: str) -> RslRlOnPolicyRunnerCfg:
  """Return PPO config using the migrated Go2 auxiliary update hook."""
  try:
    spec = VARIANT_RUNNERS[kind]
  except KeyError as exc:
    raise ValueError(f"Unknown Go2 custom algorithm: {kind}") from exc
  return kit_runner.make_variant_runner_cfg(
    spec,
    base_runner_cfg=lambda: unitree_go2_source_ppo_runner_cfg(
      learning_rate=spec.learning_rate,
      max_iterations=spec.max_iterations,
      save_interval=spec.save_interval,
      seed=spec.seed,
    ),
  )


# Zero-argument runner factories so each migrated custom task can be surfaced as
# a training profile (profile entrypoints must be importable no-arg callables).
def go2_cts_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return unitree_go2_custom_runner_cfg("cts")


def go2_amp_cts_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return unitree_go2_custom_runner_cfg("amp_cts")


def go2_ts_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return unitree_go2_custom_runner_cfg("ts")


def go2_amp_ts_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return unitree_go2_custom_runner_cfg("amp_ts")


def go2_ts_student_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return unitree_go2_custom_runner_cfg("ts_student")


def go2_him_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  """HIM (HIMLoco hybrid internal model) runner configuration.

  Dispatches through the standard RSL-RL ``OnPolicyRunner`` mechanism: the
  algorithm/actor ``class_name`` strings are resolved by
  ``rsl_rl.utils.resolve_callable`` inside ``PPO.construct_algorithm``.  The
  actor observation is the himloco_45_hist6 stacked history (270-D, newest
  frame first); the value observation is the 48-D HIM privileged frame built by
  ``go2_him_privileged_observation``.  Hyper-parameters follow HIMLoco's
  legacy PPO config (adaptive 1e-3, KL 0.01, entropy 0.01, gamma 0.99).
  """
  return unitree_go2_custom_runner_cfg("him")
