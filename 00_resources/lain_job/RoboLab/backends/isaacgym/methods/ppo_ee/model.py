import torch
import torch.nn as nn
from torch.distributions import Normal

from rsl_rl.modules.actor_critic import get_activation


def _mlp(input_dim, hidden_dims, output_dim, activation):
    layers = []
    previous = input_dim
    for width in hidden_dims:
        layers.extend((nn.Linear(previous, width), get_activation(activation)))
        previous = width
    layers.append(nn.Linear(previous, output_dim))
    return nn.Sequential(*layers)


class ActorCriticEE(nn.Module):
    is_recurrent = False

    def __init__(self, feature_dim, critic_dim, action_dim, label_dim,
                 single_obs_dim=45, actor_hidden_dims=(256, 128),
                 critic_hidden_dims=(256, 128), estimator_hidden_dims=(128, 64),
                 activation="elu", init_noise_std=1.0, **kwargs):
        super().__init__()
        self.single_obs_dim = single_obs_dim
        self.estimator = _mlp(feature_dim, estimator_hidden_dims, label_dim, activation)
        self.actor = _mlp(single_obs_dim + label_dim, actor_hidden_dims, action_dim, activation)
        self.critic = _mlp(critic_dim, critic_hidden_dims, 1, activation)
        self.std = nn.Parameter(init_noise_std * torch.ones(action_dim))
        self.distribution = None
        Normal.set_default_validate_args = False

    def _actor_input(self, features):
        return torch.cat((features[:, -self.single_obs_dim:], self.estimator(features)), dim=-1)

    def act(self, features):
        mean = self.actor(self._actor_input(features))
        self.distribution = Normal(mean, mean * 0.0 + self.std)
        return self.distribution.sample()

    def act_inference(self, features):
        return self.actor(self._actor_input(features))

    def evaluate(self, critic_obs):
        return self.critic(critic_obs)

    def get_actions_log_prob(self, actions):
        return self.distribution.log_prob(actions).sum(dim=-1)

    @property
    def action_mean(self): return self.distribution.mean
    @property
    def action_std(self): return self.distribution.stddev
    @property
    def entropy(self): return self.distribution.entropy().sum(dim=-1)
    def reset(self, dones=None): return None
