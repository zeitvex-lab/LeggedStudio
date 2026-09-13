"""RSL-RL PPO runner configs for velocity tasks (GenesisLab).

Shared by B2, Booster K1/T1, G1, H1. Structure mirrors Go2 velocity agents.
"""

from __future__ import annotations

from genesislab.utils.configclass import configclass
from genesis_rl.rsl_rl.configs import (
    RslRlOnPolicyRunnerCfg,
    RslRlPpoActorCriticCfg,
    RslRlPpoAlgorithmCfg,
)


@configclass
class VelocityRoughPPORunnerCfg(RslRlOnPolicyRunnerCfg):
    """Default PPO runner configuration for rough-terrain velocity tracking."""

    num_steps_per_env = 24
    max_iterations = 1500
    save_interval = 100
    experiment_name = "rough"

    obs_groups = {
        "actor": ["policy"],
        "critic": ["policy"],
    }

    policy = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
        actor_obs_normalization=False,
        critic_obs_normalization=False,
        actor_hidden_dims=[512, 256, 128],
        critic_hidden_dims=[512, 256, 128],
        activation="elu",
    )

    algorithm = RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.01,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=1.0e-3,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )


@configclass
class VelocityFlatPPORunnerCfg(VelocityRoughPPORunnerCfg):
    """PPO runner configuration for flat-terrain velocity tracking."""

    def __post_init__(self):
        super().__post_init__()

        self.max_iterations = 1500
        self.experiment_name = "flat"
        self.policy.actor_hidden_dims = [128, 128, 128]
        self.policy.critic_hidden_dims = [128, 128, 128]
