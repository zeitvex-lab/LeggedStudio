# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Wuji Technology Co., Ltd.
"""RL configuration for the Wuji Hand Reorient task."""

from mjlab.rl import (
  RslRlModelCfg,
  RslRlOnPolicyRunnerCfg,
  RslRlPpoAlgorithmCfg,
)


def wuji_hand_reorient_ppo_runner_cfg(
  run_name: str = "Reorient",
  max_iterations: int = 5000,
) -> RslRlOnPolicyRunnerCfg:
  return RslRlOnPolicyRunnerCfg(
    obs_groups={"actor": ("policy",), "critic": ("critic",)},
    actor=RslRlModelCfg(
      hidden_dims=(512, 256, 128),
      activation="elu",
      obs_normalization=True,
      distribution_cfg={
        # B33: this class only exists in the vendored fork (wuji_rl_libs, rsl-rl-lib 5.0.1+wuji1),
        # not in the installed rsl_rl (5.4.2) that "import rsl_rl" resolves to inside the training
        # worker (training/source is on sys.path but has no top-level rsl_rl). Installed
        # resolve_callable only accepts "module:Class" qualified names for symbols outside rsl_rl,
        # so we point it at the vendored module. The vendored modules/distribution.py depends only
        # on torch/stdlib and its Distribution protocol (update/sample/input_dim/init_mlp_weights/
        # log_prob/kl_divergence/...) duck-type-matches what the installed MLPModel/PPO call.
        # Note: importing it triggers wuji_tasks-adjacent namespace packages
        # (wuji_rl_libs.rsl_rl.rsl_rl.modules) whose cnn/mlp/rnn submodules import helpers from the
        # installed rsl_rl.utils — no path shadowing in either direction.
        "class_name": "wuji_rl_libs.rsl_rl.rsl_rl.modules.distribution:SoftplusGaussianDistribution",
        "init_std": 0.5,
        "min_std": 0.2,
      },
    ),
    critic=RslRlModelCfg(
      hidden_dims=(512, 512, 256, 128),
      activation="elu",
      obs_normalization=True,
    ),
    algorithm=RslRlPpoAlgorithmCfg(
      value_loss_coef=0.5,
      use_clipped_value_loss=False,
      clip_param=0.2,
      entropy_coef=0.001,
      num_learning_epochs=4,
      num_mini_batches=32,
      learning_rate=1.0e-4,
      schedule="fixed",
      gamma=0.99,
      lam=0.95,
      max_grad_norm=1.0,
    ),
    experiment_name="wuji_reorient",
    logger="wandb",
    wandb_project="wuji_reorient_mjlab",
    run_name=run_name,
    save_interval=50,
    num_steps_per_env=40,
    max_iterations=max_iterations,
  )
