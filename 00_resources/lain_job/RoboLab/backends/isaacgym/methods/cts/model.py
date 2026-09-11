import torch
import torch.nn as nn
from torch.distributions import Normal


def _mlp(input_dim, hidden_dims, output_dim):
    layers = []
    for width in hidden_dims:
        layers.extend((nn.Linear(input_dim, width), nn.ELU()))
        input_dim = width
    layers.append(nn.Linear(input_dim, output_dim))
    return nn.Sequential(*layers)


class ActorCriticCTS(nn.Module):
    """Concurrent teacher/student actor-critic with a shared policy head."""

    is_recurrent = False

    def __init__(
        self,
        num_actions=12,
        actor_obs=45,
        teacher_obs=99,
        history_dim=900,
        latent_dim=99,
        critic_obs=480,
        actor_hidden_dims=(256, 256),
        critic_hidden_dims=(1024, 256, 128),
        privilege_encoder_hidden_dims=(256, 128),
        history_encoder_hidden_dims=(256, 128),
    ):
        super().__init__()
        self.privilege_encoder = _mlp(teacher_obs, privilege_encoder_hidden_dims, latent_dim)
        self.history_encoder = _mlp(history_dim, history_encoder_hidden_dims, latent_dim)
        self.actor = _mlp(actor_obs + latent_dim, actor_hidden_dims, num_actions)
        self.critic = _mlp(critic_obs, critic_hidden_dims, 1)
        self.std = nn.Parameter(torch.ones(num_actions))
        self.distribution = None

    def _distribution(self, observations, latent):
        mean = self.actor(torch.cat((observations, latent), dim=-1))
        self.distribution = Normal(mean, self.std.abs() + 1.0e-4)
        return self.distribution

    def teacher_distribution(self, observations, privileged_observations):
        return self._distribution(observations, self.privilege_encoder(privileged_observations))

    def student_distribution(self, observations, observation_history):
        return self._distribution(observations, self.history_encoder(observation_history))

    def act_teacher(self, observations, privileged_observations):
        return self.teacher_distribution(observations, privileged_observations).sample()

    def act_student(self, observations, observation_history):
        return self.student_distribution(observations, observation_history).sample()

    def act_student_deterministic(self, observations, observation_history):
        return self.student_distribution(observations, observation_history).mean

    def evaluate(self, critic_observations):
        return self.critic(critic_observations)

    @property
    def action_mean(self):
        return self.distribution.mean

    @property
    def action_std(self):
        return self.distribution.stddev

    @property
    def entropy(self):
        return self.distribution.entropy().sum(dim=-1)

    def reset(self, dones=None):
        del dones
