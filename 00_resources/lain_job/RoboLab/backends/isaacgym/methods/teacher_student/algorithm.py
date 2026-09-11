import torch
import torch.nn as nn

from .storage import RolloutStorageTS


class PPOTS:
    """PPO teacher update plus a separately optimized history encoder."""

    def __init__(self, policy, cfg, device):
        self.policy, self.device = policy, device
        self.gamma = float(cfg.get("gamma", 0.99)); self.lam = float(cfg.get("lam", 0.95)); self.clip_param = float(cfg.get("clip_param", 0.2))
        self.value_loss_coef = float(cfg.get("value_loss_coef", 1.0)); self.entropy_coef = float(cfg.get("entropy_coef", 0.0)); self.max_grad_norm = float(cfg.get("max_grad_norm", 1.0))
        self.learning_rate = float(cfg.get("learning_rate", 3e-4)); self.schedule = cfg.get("schedule", "fixed"); self.desired_kl = cfg.get("desired_kl", 0.01)
        self.use_clipped_value_loss = bool(cfg.get("use_clipped_value_loss", True)); self.num_learning_epochs = int(cfg.get("num_learning_epochs", 5)); self.num_mini_batches = int(cfg.get("num_mini_batches", 4))
        self.encoder_lr = float(cfg.get("encoder_lr", 2e-4)); self.num_encoder_epochs = int(cfg.get("num_encoder_epochs", 2))
        self.rl_parameters = list(policy.actor.parameters()) + list(policy.critic.parameters()) + list(policy.privilege_encoder.parameters()) + [policy.std]
        self.rl_optimizer = torch.optim.Adam(self.rl_parameters, lr=self.learning_rate); self.history_optimizer = torch.optim.Adam(policy.history_encoder.parameters(), lr=self.encoder_lr)
        self.optimizer = self.rl_optimizer
        self.storage = None; self.transition = RolloutStorageTS.Transition()

    def init_storage(self, env, steps):
        self.storage = RolloutStorageTS(env.num_envs, steps, env.num_observations, env.num_teacher_obs, env.num_history_obs, env.num_critic_obs, env.num_actions, self.device)

    def act(self, obs, teacher, history, critic):
        self.transition.observations, self.transition.teacher_observations = obs, teacher; self.transition.observation_histories, self.transition.critic_observations = history, critic
        self.transition.actions = self.policy.act(obs, teacher).detach(); self.transition.values = self.policy.evaluate(critic).detach(); self.transition.actions_log_prob = self.policy.get_actions_log_prob(self.transition.actions).detach(); self.transition.action_mean = self.policy.action_mean.detach(); self.transition.action_sigma = self.policy.action_std.detach()
        return self.transition.actions

    def process_env_step(self, rewards, dones, infos):
        self.transition.rewards, self.transition.dones = rewards.clone(), dones
        timeouts = infos.get("time_outs") if isinstance(infos, dict) else None
        if timeouts is not None: self.transition.rewards += self.gamma * self.transition.values.squeeze(-1) * timeouts.to(self.device)
        self.storage.add(self.transition); self.transition.clear(); self.policy.reset(dones)

    def compute_returns(self, critic): self.storage.compute_returns(self.policy.evaluate(critic).detach(), self.gamma, self.lam)

    def _value_loss(self, value, returns, old_value):
        if not self.use_clipped_value_loss: return (value - returns).pow(2).mean()
        clipped = old_value + (value - old_value).clamp(-self.clip_param, self.clip_param)
        return torch.maximum((value - returns).pow(2), (clipped - returns).pow(2)).mean()

    def _adjust_learning_rate(self, sigma, old_sigma, mu, old_mu):
        if self.schedule != "adaptive" or self.desired_kl is None: return
        with torch.no_grad(): kl = torch.sum(torch.log((sigma + 1e-5) / (old_sigma + 1e-5)) + (old_sigma.pow(2) + (old_mu - mu).pow(2)) / (2 * sigma.pow(2)) - 0.5, dim=-1).mean()
        if kl > self.desired_kl * 2: self.learning_rate = max(1e-5, self.learning_rate / 1.5)
        elif 0 < kl < self.desired_kl / 2: self.learning_rate = min(1e-2, self.learning_rate * 1.5)
        for group in self.rl_optimizer.param_groups: group["lr"] = self.learning_rate

    def update(self):
        assert self.storage is not None
        value_sum = surrogate_sum = 0.0; updates = 0; max_action = float(self.storage.actions.abs().max().item()) if self.storage.step else 0.0
        for batch in self.storage.mini_batch_generator(self.num_mini_batches, self.num_learning_epochs):
            obs, teacher, history, critic, actions, old_values, advantages, returns, old_log, old_mu, old_sigma, dones = batch
            self.policy.act(obs, teacher); log_prob = self.policy.get_actions_log_prob(actions); value = self.policy.evaluate(critic).squeeze(-1); self._adjust_learning_rate(self.policy.action_std, old_sigma, self.policy.action_mean, old_mu)
            ratio = torch.exp(log_prob - old_log.squeeze(-1)); adv = advantages.squeeze(-1); surrogate = torch.maximum(-adv * ratio, -adv * ratio.clamp(1 - self.clip_param, 1 + self.clip_param)).mean(); value_loss = self._value_loss(value, returns.squeeze(-1), old_values.squeeze(-1))
            loss = surrogate + self.value_loss_coef * value_loss - self.entropy_coef * self.policy.entropy.mean(); self.rl_optimizer.zero_grad(set_to_none=True); loss.backward(); nn.utils.clip_grad_norm_(self.rl_parameters, self.max_grad_norm); self.rl_optimizer.step()
            value_sum += value_loss.item(); surrogate_sum += surrogate.item(); updates += 1
        encoder_sum = 0.0; encoder_updates = 0
        for batch in self.storage.mini_batch_generator(self.num_mini_batches, self.num_learning_epochs):
            _, teacher, history, _, _, _, _, _, _, _, _, dones = batch; valid = (~dones).float().squeeze(-1); denom = valid.sum().clamp_min(1.0)
            with torch.no_grad(): target = self.policy.privilege_encoder(teacher)
            for _ in range(self.num_encoder_epochs):
                prediction = self.policy.history_encoder(history); encoder_loss = (prediction - target).pow(2).mean(dim=-1).mul(valid).sum() / denom
                self.history_optimizer.zero_grad(set_to_none=True); encoder_loss.backward(); nn.utils.clip_grad_norm_(self.policy.history_encoder.parameters(), self.max_grad_norm); self.history_optimizer.step(); encoder_sum += encoder_loss.item(); encoder_updates += 1
        self.storage.clear(); return {"value_loss": value_sum / max(updates, 1), "surrogate_loss": surrogate_sum / max(updates, 1), "encoder_loss": encoder_sum / max(encoder_updates, 1), "learning_rate": self.learning_rate, "action_abs_max": max_action}


PPO_TS = PPOTS
