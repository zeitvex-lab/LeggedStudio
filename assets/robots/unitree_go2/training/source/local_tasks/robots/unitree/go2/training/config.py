"""RL configurations for Unitree Go2 experiments."""

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


def unitree_go2_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  """Create RL runner configuration for Unitree Go2 velocity task.

  **委托** ``kits/quadruped_kit.ppo_runner_cfg``（四足框架层唯一真值；与 lite3 / b2 / go1
  同一先例）。原先本函数内联了一份与 lite3/b2 逐字相同的 runner 配置（隐藏层 512/256/128、
  elu、obs_normalization、Gaussian std 1.0 scalar、clip 0.2、entropy 0.01、epochs 5、
  minibatches 4、lr 1e-3 adaptive、gamma 0.99、lam 0.95、desired_kl 0.01、max_grad_norm 1.0、
  num_steps 24、max_iterations 10_000）—— 多份副本一旦 Kit 调超参就会各自漂移。
  本包**唯一差异**是 ``save_interval=50``（Kit 默认 100，即 lite3/b2/go1 语义），由参数携带。
  等价性由迁移前后的 ``dataclasses.asdict`` dump 逐字段比对（0 差异）保证。
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
  """Create PPO config matching the source RSL-RL observation handling."""
  cfg = unitree_go2_ppo_runner_cfg()
  # The source policies consume the environment's already scaled/clipped
  # observations directly and do not apply a running observation normalizer.
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
  is_ts_family = kind in ("amp_ts", "amp_ts_student", "ts", "ts_student")
  cfg = unitree_go2_source_ppo_runner_cfg(
    learning_rate=1.0e-5 if kind in ("amp_ts", "ts") else 1.0e-3,
    max_iterations=20_000,
    save_interval=500,
    seed=5 if is_ts_family else 1,
  )
  algorithm_classes = {
    "cts": "local_tasks.learning.algorithms.CtsPPO",
    "amp_cts": "local_tasks.learning.algorithms.AmpCtsPPO",
    "dreamwaq": "local_tasks.learning.algorithms.DreamWaQPPO",
    "amp_dreamwaq": "local_tasks.learning.algorithms.AmpDreamWaQPPO",
    "amp_ts": "local_tasks.learning.algorithms.AmpPPO",
    # Source student jobs are pure recurrent behavior distillation.  Their
    # dedicated runner does not execute PPO or AMP discriminator updates.
    "amp_ts_student": "local_tasks.learning.algorithms.TeacherStudentPPO",
    "ts": "local_tasks.learning.algorithms.Go2AuxiliaryPPO",
    "ts_student": "local_tasks.learning.algorithms.TeacherStudentPPO",
  }
  actor_classes = {
    "cts": "local_tasks.learning.models.CtsActorModel",
    "amp_cts": "local_tasks.learning.models.CtsActorModel",
    "dreamwaq": "local_tasks.learning.models.DreamWaQActorModel",
    "amp_dreamwaq": "local_tasks.learning.models.DreamWaQActorModel",
    "amp_ts": "local_tasks.learning.models.TeacherActorModel",
    "amp_ts_student": "local_tasks.learning.models.StudentActorModel",
    "ts": "local_tasks.learning.models.TeacherActorModel",
    "ts_student": "local_tasks.learning.models.StudentActorModel",
  }
  critic_classes = {
    "cts": "local_tasks.learning.models.CtsCriticModel",
    "amp_cts": "local_tasks.learning.models.CtsCriticModel",
  }
  try:
    cfg.algorithm.class_name = algorithm_classes[kind]
    cfg.actor.class_name = actor_classes[kind]
    if kind in critic_classes:
      cfg.critic.class_name = critic_classes[kind]
  except KeyError as exc:
    raise ValueError(f"Unknown Go2 custom algorithm: {kind}") from exc
  # The legacy TS distillation runners collect 50 frames per update (the
  # student LSTM is trained on that longer rollout) and clamp every action
  # standard deviation to 0.05.  Encode both constraints in the current
  # runner config instead of relying on a deployment-only workaround.
  if kind in ("amp_ts_student", "ts_student"):
    cfg.num_steps_per_env = 50
  if kind in (
    "amp_cts",
    "amp_dreamwaq",
    "amp_ts",
    "amp_ts_student",
    "ts",
    "ts_student",
  ):
    # Legacy min_normalized_std=0.05 is multiplied by each joint's complete
    # position range, yielding a distinct floor for hip/thigh/calf noise.
    assert cfg.actor.distribution_cfg is not None
    cfg.actor.distribution_cfg["class_name"] = (
      "local_tasks.learning.models.Go2ClampedGaussianDistribution"
    )
    cfg.actor.distribution_cfg["min_std"] = (
      0.10472,
      0.253075,
      0.094247,
    ) * 4
  cfg.experiment_name = f"go2_{kind}"
  return cfg


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
  algorithm/actor ``class_name`` strings below are resolved by
  ``rsl_rl.utils.resolve_callable`` inside ``PPO.construct_algorithm``.  The
  actor observation is the himloco_45_hist6 stacked history (270-D, newest
  frame first); the value observation is the 48-D HIM privileged frame built by
  ``go2_him_privileged_observation``.  Hyper-parameters follow HIMLoco's
  legacy PPO config (adaptive 1e-3, KL 0.01, entropy 0.01, gamma 0.99).
  """
  cfg = unitree_go2_source_ppo_runner_cfg(
    learning_rate=1.0e-3,
    max_iterations=20_000,
    save_interval=100,
    seed=1,
  )
  cfg.algorithm.class_name = "adapters.mjlab.algorithms.him.algorithms:HimPPO"
  cfg.actor.class_name = "adapters.mjlab.algorithms.him.models:HIMActorModel"
  cfg.critic.class_name = "rsl_rl.models.mlp_model:MLPModel"
  cfg.experiment_name = "go2_him"
  return cfg
