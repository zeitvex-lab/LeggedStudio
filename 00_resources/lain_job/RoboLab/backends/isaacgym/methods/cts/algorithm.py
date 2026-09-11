import torch
import torch.nn as nn

from .storage import RolloutStorageCTS


class PPOCTS:
    """PPO with concurrent teacher and student environment partitions."""

    def __init__(self, policy, cfg, device, num_teacher):
        self.policy = policy
        self.device = device
        self.num_teacher = int(num_teacher)
        self.gamma = float(cfg.get("gamma", 0.99))
        self.lam = float(cfg.get("lam", 0.95))
        self.clip_param = float(cfg.get("clip_param", 0.2))
        self.value_loss_coef = float(cfg.get("value_loss_coef", 1.0))
        self.entropy_coef = float(cfg.get("entropy_coef", 0.0))
        self.max_grad_norm = float(cfg.get("max_grad_norm", 1.0))
        self.learning_rate = float(cfg.get("learning_rate", 3.0e-4))
        self.schedule = cfg.get("schedule", "fixed")
        self.desired_kl = cfg.get("desired_kl", 0.01)
        self.use_clipped_value_loss = bool(cfg.get("use_clipped_value_loss", True))
        self.num_learning_epochs = int(cfg.get("num_learning_epochs", 5))
        self.num_mini_batches = int(cfg.get("num_mini_batches", 4))
        self.encoder_lr = float(cfg.get("encoder_lr", 5.0e-4))
        self.num_encoder_epochs = int(cfg.get("num_encoder_epochs", 1))
        self.rl_parameters = list(policy.actor.parameters()) + list(policy.critic.parameters()) + list(policy.privilege_encoder.parameters()) + [policy.std]
        self.rl_optimizer = torch.optim.Adam(self.rl_parameters, lr=self.learning_rate)
        self.history_optimizer = torch.optim.Adam(policy.history_encoder.parameters(), lr=self.encoder_lr)
        self.storage = None
        self.transition = RolloutStorageCTS.Transition()

    def init_storage(self, env, steps):
        self.storage = RolloutStorageCTS(env.num_envs, self.num_teacher, steps, env.num_observations, env.num_teacher_obs, env.num_history_obs, env.num_critic_obs, env.num_actions, self.device)

    def act(self, observations, teacher_observations, observation_history, critic_observations):
        teacher_actions = self.policy.act_teacher(observations[:self.num_teacher], teacher_observations[:self.num_teacher]).detach()
        teacher_log_prob = self.policy.distribution.log_prob(teacher_actions).sum(-1).detach()
        teacher_mean, teacher_std = self.policy.action_mean.detach(), self.policy.action_std.detach()
        student_actions = self.policy.act_student(observations[self.num_teacher:], observation_history[self.num_teacher:]).detach()
        student_log_prob = self.policy.distribution.log_prob(student_actions).sum(-1).detach()
        student_mean, student_std = self.policy.action_mean.detach(), self.policy.action_std.detach()
        self.transition.observations = observations
        self.transition.teacher_observations = teacher_observations
        self.transition.observation_histories = observation_history
        self.transition.critic_observations = critic_observations
        self.transition.actions = torch.cat((teacher_actions, student_actions), dim=0)
        self.transition.actions_log_prob = torch.cat((teacher_log_prob, student_log_prob), dim=0)
        self.transition.action_mean = torch.cat((teacher_mean, student_mean), dim=0)
        self.transition.action_sigma = torch.cat((teacher_std, student_std), dim=0)
        self.transition.values = self.policy.evaluate(critic_observations).detach()
        return self.transition.actions

    def process_env_step(self, rewards, dones, infos):
        self.transition.rewards = rewards.clone()
        self.transition.dones = dones
        timeouts = infos.get("time_outs") if isinstance(infos, dict) else None
        if timeouts is not None:
            self.transition.rewards += self.gamma * self.transition.values.squeeze(-1) * timeouts.to(self.device)
        self.storage.add(self.transition)
        self.transition.clear()
        self.policy.reset(dones)

    def compute_returns(self, critic_observations):
        self.storage.compute_returns(self.policy.evaluate(critic_observations).detach(), self.gamma, self.lam)

    def _adjust_learning_rate(self, sigma, old_sigma, mean, old_mean):
        if self.schedule != "adaptive" or self.desired_kl is None:
            return
        with torch.no_grad():
            kl = torch.sum(torch.log((sigma + 1.0e-5) / (old_sigma + 1.0e-5)) + (old_sigma.square() + (old_mean - mean).square()) / (2.0 * sigma.square()) - 0.5, dim=-1).mean()
        if kl > self.desired_kl * 2:
            self.learning_rate = max(1.0e-5, self.learning_rate / 1.5)
        elif 0 < kl < self.desired_kl / 2:
            self.learning_rate = min(1.0e-2, self.learning_rate * 1.5)
        for group in self.rl_optimizer.param_groups:
            group["lr"] = self.learning_rate

    def update(self):
        value_sum = teacher_sum = student_sum = 0.0
        updates = 0
        for teacher, student, critic, old_values, returns in self.storage.mini_batch_generator(self.num_mini_batches, self.num_learning_epochs):
            teacher_obs, teacher_privileged, teacher_actions, teacher_old_log_prob, teacher_advantages, teacher_old_mean, teacher_old_std = teacher
            student_obs, _, student_history, student_actions, student_old_log_prob, student_advantages = student
            self.policy.teacher_distribution(teacher_obs, teacher_privileged)
            teacher_log_prob = self.policy.distribution.log_prob(teacher_actions).sum(-1)
            teacher_entropy = self.policy.entropy
            self._adjust_learning_rate(self.policy.action_std, teacher_old_std, self.policy.action_mean, teacher_old_mean)
            teacher_ratio = torch.exp(teacher_log_prob - teacher_old_log_prob.squeeze(-1))
            teacher_loss = torch.maximum(-teacher_advantages.squeeze(-1) * teacher_ratio, -teacher_advantages.squeeze(-1) * teacher_ratio.clamp(1 - self.clip_param, 1 + self.clip_param)).mean()
            self.policy.student_distribution(student_obs, student_history)
            student_log_prob = self.policy.distribution.log_prob(student_actions).sum(-1)
            student_entropy = self.policy.entropy
            student_ratio = torch.exp(student_log_prob - student_old_log_prob.squeeze(-1))
            student_loss = torch.maximum(-student_advantages.squeeze(-1) * student_ratio, -student_advantages.squeeze(-1) * student_ratio.clamp(1 - self.clip_param, 1 + self.clip_param)).mean()
            value = self.policy.evaluate(critic).squeeze(-1)
            if self.use_clipped_value_loss:
                clipped = old_values.squeeze(-1) + (value - old_values.squeeze(-1)).clamp(-self.clip_param, self.clip_param)
                value_loss = torch.maximum((value - returns.squeeze(-1)).square(), (clipped - returns.squeeze(-1)).square()).mean()
            else:
                value_loss = (value - returns.squeeze(-1)).square().mean()
            loss = teacher_loss + student_loss + self.value_loss_coef * value_loss - self.entropy_coef * torch.cat((teacher_entropy, student_entropy)).mean()
            self.rl_optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(self.rl_parameters, self.max_grad_norm)
            self.rl_optimizer.step()
            value_sum += value_loss.item()
            teacher_sum += teacher_loss.item()
            student_sum += student_loss.item()
            updates += 1
        reconstruction_sum = 0.0
        reconstruction_updates = 0
        for _, student, _, _, _ in self.storage.mini_batch_generator(self.num_mini_batches, self.num_learning_epochs):
            _, student_privileged, student_history, _, _, _ = student
            with torch.no_grad():
                target = self.policy.privilege_encoder(student_privileged)
            for _ in range(self.num_encoder_epochs):
                reconstruction_loss = (self.policy.history_encoder(student_history) - target).square().mean()
                self.history_optimizer.zero_grad(set_to_none=True)
                reconstruction_loss.backward()
                nn.utils.clip_grad_norm_(self.policy.history_encoder.parameters(), self.max_grad_norm)
                self.history_optimizer.step()
                reconstruction_sum += reconstruction_loss.item()
                reconstruction_updates += 1
        self.storage.clear()
        return {
            "value_loss": value_sum / max(updates, 1),
            "teacher_surrogate_loss": teacher_sum / max(updates, 1),
            "student_surrogate_loss": student_sum / max(updates, 1),
            "reconstruction_loss": reconstruction_sum / max(reconstruction_updates, 1),
            "learning_rate": self.learning_rate,
        }


PPO_CTS = PPOCTS
