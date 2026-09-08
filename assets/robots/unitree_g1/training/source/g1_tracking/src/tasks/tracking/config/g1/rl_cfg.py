"""RL configuration for the Unitree G1 motion-tracking task (plain PPO)."""

from mjlab.rl import (
  RslRlModelCfg,
  RslRlOnPolicyRunnerCfg,
  RslRlPpoAlgorithmCfg,
)


def g1_tracking_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  """Create the RL runner configuration for G1 motion tracking.

  Plain PPO (no AMP discriminator): the tracking reward family carries the
  task signal. Actor/critic hidden dims follow the upstream DeepMimic config
  (policy default [512, 256, 128], critic [1024, 256, 128], elu).
  """
  return RslRlOnPolicyRunnerCfg(
    actor=RslRlModelCfg(
      hidden_dims=(512, 256, 128),
      activation="elu",
      obs_normalization=True,
      distribution_cfg={
        "class_name": "GaussianDistribution",
        "init_std": 1.0,
        "std_type": "scalar",
      },
    ),
    critic=RslRlModelCfg(
      hidden_dims=(1024, 256, 128),
      activation="elu",
      obs_normalization=True,
    ),
    algorithm=RslRlPpoAlgorithmCfg(
      value_loss_coef=1.0,
      use_clipped_value_loss=True,
      clip_param=0.2,
      entropy_coef=0.005,
      num_learning_epochs=5,
      num_mini_batches=4,
      learning_rate=1.0e-3,
      schedule="adaptive",
      gamma=0.99,
      lam=0.95,
      desired_kl=0.01,
      max_grad_norm=1.0,
      class_name="PPO",
    ),
    experiment_name="g1_tracking",
    logger="tensorboard",
    save_interval=500,
    num_steps_per_env=32,
    max_iterations=3000,
  )
