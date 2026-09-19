# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：``make_m20_runner_cfg`` 的构造正文与 b2w_velocity /
# go2w_velocity 的 rl_cfg.py 逐字同文（三份仅函数名 / experiment_name 字符串
# 不同；本文件还是带 go2w 残留命名的同正文副本——尾部三个 unitree_go2w_* 包装
# 与其字面值原样保留），构造正文已上移为
# adapters/mjlab/kits/wheel_leg_kit.ppo_runner_cfg_ex（唯一真值）。包内保留原
# 函数签名与全部入口包装（entrypoint 符号 ``m20_ppo_runner_cfg`` /
# ``m20_rough_ppo_runner_cfg`` 仍在 ``m20_velocity.rl_cfg`` 模块内，静态解析
# 不受影响），构造委托 kit。
# ------------------------------------------------------------------------------

"""RL configuration for active Unitree Go2-W velocity tasks."""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（见 kits/wheel_leg_kit 模块注释）：worker / schema-dump / 冒烟三种
# 运行环境都只把 training/source 或包根放进 sys.path；沿目录向上找 adapters/mjlab
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from mjlab.rl import RslRlOnPolicyRunnerCfg  # noqa: E402

from adapters.mjlab.kits import wheel_leg_kit as kit  # noqa: E402


def make_m20_runner_cfg(
  *,
  experiment_name: str = "m20_velocity",
  run_name: str | None = None,
  max_iterations: int = 10001,
  save_interval: int = 1000,
  init_noise_std: float = 1.0,
  learning_rate: float = 1.0e-3,
  entropy_coef: float = 0.01,
  max_grad_norm: float = 1.0,
  resume: bool = False,
  load_checkpoint: str | None = None,
) -> RslRlOnPolicyRunnerCfg:
  """Build a Go2-W PPO runner config from the shared lab defaults."""
  return kit.ppo_runner_cfg_ex(
    experiment_name,
    run_name=run_name,
    max_iterations=max_iterations,
    save_interval=save_interval,
    init_noise_std=init_noise_std,
    learning_rate=learning_rate,
    entropy_coef=entropy_coef,
    max_grad_norm=max_grad_norm,
    resume=resume,
    load_checkpoint=load_checkpoint,
  )


def m20_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return make_m20_runner_cfg()


def m20_rough_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return make_m20_runner_cfg(
    experiment_name="m20_velocity",
    init_noise_std=0.6,
    learning_rate=5.0e-4,
    entropy_coef=0.005,
    max_grad_norm=0.5,
  )


def m20_rough_finetune_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return make_m20_runner_cfg(
    experiment_name="m20_velocity",
    run_name="rough_ft",
    init_noise_std=0.6,
    learning_rate=5.0e-4,
    entropy_coef=0.005,
    max_grad_norm=0.5,
    resume=True,
    load_checkpoint="model_10000.pt",
  )


def unitree_go2w_flat_legs_only_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return make_m20_runner_cfg(
    experiment_name="go2w_legs_only",
    run_name="flat_walk",
    max_iterations=20001,
    init_noise_std=0.4,
    learning_rate=5.0e-4,
    entropy_coef=0.003,
    max_grad_norm=0.5,
  )


def unitree_go2w_flat_legs_only_omni_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return make_m20_runner_cfg(
    experiment_name="go2w_legs_only_omni",
    run_name="flat_walk_omni",
    max_iterations=30001,
    init_noise_std=0.3,
    learning_rate=5.0e-4,
    entropy_coef=0.002,
    max_grad_norm=0.5,
  )


def unitree_go2w_flat_legs_only_omni_finetune_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  return make_m20_runner_cfg(
    experiment_name="go2w_legs_only",
    run_name="flat_walk_omni_ft",
    max_iterations=30001,
    init_noise_std=0.3,
    learning_rate=5.0e-4,
    entropy_coef=0.002,
    max_grad_norm=0.5,
    resume=True,
    load_checkpoint="model_20000.pt",
  )
