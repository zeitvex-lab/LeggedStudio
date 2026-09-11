"""DreamWaQ policy modules kept local to the method plugin."""

import torch
import torch.nn as nn
from torch.distributions import Normal


def get_activation(name):
    if isinstance(name, nn.Module):
        return name
    name = str(name).lower()
    activations = {"elu": nn.ELU(), "relu": nn.ReLU(), "selu": nn.SELU(),
                   "crelu": nn.ReLU(), "lrelu": nn.LeakyReLU(),
                   "tanh": nn.Tanh(), "sigmoid": nn.Sigmoid()}
    if name not in activations:
        raise ValueError("unsupported DreamWaQ activation %r" % name)
    return activations[name]


def mlp(inp, hidden, out, activation="elu"):
    layers = []
    for width in list(hidden or []):
        layers.extend((nn.Linear(inp, int(width)), get_activation(activation)))
        inp = int(width)
    layers.append(nn.Linear(inp, out))
    return nn.Sequential(*layers)


class VAE(nn.Module):
    """Reference DreamWaQ VAE with independent distribution heads."""

    def __init__(self, history_dim=225, latent_dim=16, explicit_dim=24,
                 output_dim=45, activation="elu",
                 encoder_hidden_dims=(256, 128), decoder_hidden_dims=(256, 128)):
        super().__init__()
        encoder_hidden_dims, decoder_hidden_dims = list(encoder_hidden_dims), list(decoder_hidden_dims)
        if not encoder_hidden_dims or not decoder_hidden_dims:
            raise ValueError("DreamWaQ encoder and decoder need hidden layers")
        enc_layers = [nn.Linear(history_dim, encoder_hidden_dims[0]), get_activation(activation)]
        for index, width in enumerate(encoder_hidden_dims):
            if index == len(encoder_hidden_dims) - 1:
                enc_layers.extend((nn.Linear(width, 2 * latent_dim + 2 * explicit_dim), get_activation(activation)))
            else:
                enc_layers.extend((nn.Linear(width, encoder_hidden_dims[index + 1]), get_activation(activation)))
        self.encoder = nn.Sequential(*enc_layers)
        encoded_dim = 2 * latent_dim + 2 * explicit_dim
        self.latent_mu = nn.Linear(encoded_dim, latent_dim)
        self.latent_var = nn.Sequential(nn.Linear(encoded_dim, latent_dim), nn.Hardtanh(-5.0, 5.0))
        self.vel_mu = nn.Linear(encoded_dim, explicit_dim)
        self.vel_var = nn.Sequential(nn.Linear(encoded_dim, explicit_dim), nn.Hardtanh(-5.0, 5.0))
        self.decoder = mlp(latent_dim + explicit_dim, decoder_hidden_dims, output_dim, activation)
        self.latent_dim, self.explicit_dim = latent_dim, explicit_dim

    def encode(self, history):
        encoded = self.encoder(history)
        return self.latent_mu(encoded), self.latent_var(encoded), self.vel_mu(encoded), self.vel_var(encoded)

    @staticmethod
    def reparameterize(mu, logvar):
        return mu + torch.randn_like(mu) * torch.exp(0.5 * logvar)

    def forward(self, history):
        latent_mu, latent_var, vel_mu, vel_var = self.encode(history)
        return ((self.reparameterize(latent_mu, latent_var), self.reparameterize(vel_mu, vel_var)),
                (latent_mu, latent_var, vel_mu, vel_var))

    def sample(self, history):
        return self.forward(history)

    def decode(self, z, v):
        return self.decoder(torch.cat((z, v), dim=-1))

    def inference(self, history):
        latent_mu, _, vel_mu, _ = self.encode(history)
        return torch.cat((latent_mu, vel_mu), dim=-1)


class ActorCriticDreamWaQ(nn.Module):
    is_recurrent = False

    def __init__(self, num_actions=12, actor_obs=45, critic_obs=480,
                 history_dim=225, output_dim=45, latent_dim=16, explicit_dim=24,
                 actor_hidden_dims=(512, 256, 128), critic_hidden_dims=(1024, 256, 128),
                 encoder_hidden_dims=(256, 128), decoder_hidden_dims=(256, 128),
                 activation="elu", init_noise_std=1.0, **kwargs):
        super().__init__()
        if kwargs:
            raise TypeError("unexpected DreamWaQ policy arguments: %s" % ", ".join(sorted(kwargs)))
        self.vae = VAE(history_dim, latent_dim, explicit_dim, output_dim, activation,
                       encoder_hidden_dims, decoder_hidden_dims)
        self.actor = mlp(actor_obs + latent_dim + explicit_dim, actor_hidden_dims, num_actions, activation)
        self.critic = mlp(critic_obs, critic_hidden_dims, 1, activation)
        self.std = nn.Parameter(float(init_noise_std) * torch.ones(num_actions))
        self.distribution = None
        Normal.set_default_validate_args = False

    def reset(self, dones=None):
        pass

    def update_distribution(self, observations, obs_history):
        (z, vel), _ = self.vae.sample(obs_history)
        mean = self.actor(torch.cat((observations, z, vel), dim=-1))
        self.distribution = Normal(mean, mean * 0.0 + self.std)

    def act(self, observations, obs_history, **kwargs):
        self.update_distribution(observations, obs_history)
        return self.distribution.sample()

    def act_inference(self, observations, observation_history, **kwargs):
        latent = self.vae.inference(observation_history)
        return self.actor(torch.cat((observations, latent), dim=-1))

    def evaluate(self, critic_obs, **kwargs):
        return self.critic(critic_obs)

    def get_actions_log_prob(self, actions):
        return self.distribution.log_prob(actions).sum(dim=-1)

    @property
    def action_mean(self): return self.distribution.mean
    @property
    def action_std(self): return self.distribution.stddev
    @property
    def entropy(self): return self.distribution.entropy().sum(dim=-1)
