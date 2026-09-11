import torch
import torch.nn as nn

from .storage import RolloutStorageEE


class PPOEE:
    def __init__(self, policy, cfg, device):
        self.policy, self.device = policy, device
        self.gamma, self.lam = cfg.get("gamma", .99), cfg.get("lam", .95)
        self.clip, self.value_coef = cfg.get("clip_param", .2), cfg.get("value_loss_coef", 1.)
        self.entropy_coef, self.max_grad_norm = cfg.get("entropy_coef", .01), cfg.get("max_grad_norm", 1.)
        self.epochs = cfg.get("num_learning_epochs", 1)
        self.minibatches = cfg.get("num_mini_batches", 1)
        self.rl_optimizer = torch.optim.Adam(list(policy.actor.parameters()) + list(policy.critic.parameters()) + [policy.std], lr=cfg.get("learning_rate", 1e-3))
        self.estimator_optimizer = torch.optim.Adam(policy.estimator.parameters(), lr=cfg.get("estimator_lr", 2e-4))
        self.storage = None
        self.transition = RolloutStorageEE.Transition()

    def init_storage(self, env, steps):
        self.storage = RolloutStorageEE(env.num_envs, steps, env.num_estimator_features, env.num_estimator_labels, env.num_privileged_obs, env.num_actions, self.device)

    def act(self, features, critic, labels):
        self.transition.features, self.transition.labels, self.transition.critic = features, labels, critic
        self.transition.actions = self.policy.act(features).detach(); self.transition.values = self.policy.evaluate(critic).detach()
        self.transition.log_prob = self.policy.get_actions_log_prob(self.transition.actions).detach(); self.transition.mu = self.policy.action_mean.detach(); self.transition.sigma = self.policy.action_std.detach()
        return self.transition.actions

    def process(self, rewards, dones, infos):
        self.transition.rewards, self.transition.dones = rewards, dones
        self.storage.add(self.transition); self.transition.clear(); self.policy.reset(dones)

    def update(self):
        rl_loss = est_loss = 0.
        batches_seen = 0
        for _ in range(self.epochs):
          for critic, features, labels, actions, old_values, adv, returns, old_log, old_mu, old_sigma, dones in self.storage.batches(self.minibatches):
            self.policy.act(features); log = self.policy.get_actions_log_prob(actions); value = self.policy.evaluate(critic)
            ratio = torch.exp(log - old_log.squeeze(-1)); surrogate = torch.max(-adv.squeeze(-1) * ratio, -adv.squeeze(-1) * ratio.clamp(1-self.clip, 1+self.clip)).mean()
            vf = (value - returns).pow(2).mean(); loss = surrogate + self.value_coef * vf - self.entropy_coef * self.policy.entropy.mean()
            self.rl_optimizer.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm); self.rl_optimizer.step(); rl_loss += loss.item()
            estimate = self.policy.estimator(features); supervised = ((estimate - labels) * (1-dones)).pow(2).mean()
            self.estimator_optimizer.zero_grad(); supervised.backward(); self.estimator_optimizer.step(); est_loss += supervised.item(); batches_seen += 1
        self.storage.clear(); return rl_loss / max(1,batches_seen), est_loss / max(1,batches_seen)
