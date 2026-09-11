import torch


class RolloutStorageCTS:
    class Transition:
        def __init__(self):
            self.observations = None
            self.teacher_observations = None
            self.observation_histories = None
            self.critic_observations = None
            self.actions = None
            self.rewards = None
            self.dones = None
            self.values = None
            self.actions_log_prob = None
            self.action_mean = None
            self.action_sigma = None

        def clear(self):
            self.__init__()

    def __init__(self, num_envs, num_teacher, num_steps, obs_dim, teacher_dim, history_dim, critic_dim, action_dim, device):
        if not 0 < num_teacher < num_envs:
            raise ValueError("CTS needs a non-empty teacher and student partition")
        shape = (num_steps, num_envs)
        self.observations = torch.zeros(*shape, obs_dim, device=device)
        self.teacher_observations = torch.zeros(*shape, teacher_dim, device=device)
        self.observation_histories = torch.zeros(*shape, history_dim, device=device)
        self.critic_observations = torch.zeros(*shape, critic_dim, device=device)
        self.actions = torch.zeros(*shape, action_dim, device=device)
        self.rewards = torch.zeros(*shape, 1, device=device)
        self.dones = torch.zeros(*shape, 1, dtype=torch.bool, device=device)
        self.values = torch.zeros(*shape, 1, device=device)
        self.actions_log_prob = torch.zeros(*shape, 1, device=device)
        self.mu = torch.zeros(*shape, action_dim, device=device)
        self.sigma = torch.zeros(*shape, action_dim, device=device)
        self.returns = torch.zeros_like(self.values)
        self.teacher_advantages = torch.zeros(num_steps, num_teacher, 1, device=device)
        self.student_advantages = torch.zeros(num_steps, num_envs - num_teacher, 1, device=device)
        self.num_envs = num_envs
        self.num_teacher = num_teacher
        self.num_steps = num_steps
        self.device = device
        self.step = 0

    def add(self, transition):
        if self.step >= self.num_steps:
            raise RuntimeError("CTS rollout buffer overflow")
        index = self.step
        for destination, source in (
            (self.observations, transition.observations),
            (self.teacher_observations, transition.teacher_observations),
            (self.observation_histories, transition.observation_histories),
            (self.critic_observations, transition.critic_observations),
            (self.actions, transition.actions),
            (self.values, transition.values),
            (self.mu, transition.action_mean),
            (self.sigma, transition.action_sigma),
        ):
            destination[index].copy_(source)
        self.rewards[index].copy_(transition.rewards.view(-1, 1))
        self.dones[index].copy_(transition.dones.view(-1, 1).bool())
        self.actions_log_prob[index].copy_(transition.actions_log_prob.view(-1, 1))
        self.step += 1

    def compute_returns(self, last_values, gamma, lam):
        for start, end, advantages in (
            (0, self.num_teacher, self.teacher_advantages),
            (self.num_teacher, self.num_envs, self.student_advantages),
        ):
            advantage = torch.zeros_like(last_values[start:end])
            for step in reversed(range(self.num_steps)):
                next_values = last_values[start:end] if step == self.num_steps - 1 else self.values[step + 1, start:end]
                not_done = (~self.dones[step, start:end]).float()
                delta = self.rewards[step, start:end] + gamma * next_values * not_done - self.values[step, start:end]
                advantage = delta + gamma * lam * not_done * advantage
                self.returns[step, start:end] = advantage + self.values[step, start:end]
            advantages.copy_(self.returns[:, start:end] - self.values[:, start:end])
            advantages.sub_(advantages.mean()).div_(advantages.std(unbiased=False) + 1.0e-8)

    def mini_batch_generator(self, num_mini_batches, num_epochs):
        teacher_total = self.num_steps * self.num_teacher
        student_total = self.num_steps * (self.num_envs - self.num_teacher)
        full_total = self.num_steps * self.num_envs
        teacher = {
            "obs": self.observations[:, :self.num_teacher].flatten(0, 1),
            "privileged": self.teacher_observations[:, :self.num_teacher].flatten(0, 1),
            "actions": self.actions[:, :self.num_teacher].flatten(0, 1),
            "log_prob": self.actions_log_prob[:, :self.num_teacher].flatten(0, 1),
            "advantages": self.teacher_advantages.flatten(0, 1),
            "mu": self.mu[:, :self.num_teacher].flatten(0, 1),
            "sigma": self.sigma[:, :self.num_teacher].flatten(0, 1),
        }
        student = {
            "obs": self.observations[:, self.num_teacher:].flatten(0, 1),
            "privileged": self.teacher_observations[:, self.num_teacher:].flatten(0, 1),
            "history": self.observation_histories[:, self.num_teacher:].flatten(0, 1),
            "actions": self.actions[:, self.num_teacher:].flatten(0, 1),
            "log_prob": self.actions_log_prob[:, self.num_teacher:].flatten(0, 1),
            "advantages": self.student_advantages.flatten(0, 1),
        }
        critic = self.critic_observations.flatten(0, 1)
        values = self.values.flatten(0, 1)
        returns = self.returns.flatten(0, 1)
        for _ in range(num_epochs):
            teacher_batches = torch.tensor_split(torch.randperm(teacher_total, device=self.device), num_mini_batches)
            student_batches = torch.tensor_split(torch.randperm(student_total, device=self.device), num_mini_batches)
            full_batches = torch.tensor_split(torch.randperm(full_total, device=self.device), num_mini_batches)
            for teacher_indices, student_indices, full_indices in zip(teacher_batches, student_batches, full_batches):
                yield (
                    tuple(teacher[name][teacher_indices] for name in ("obs", "privileged", "actions", "log_prob", "advantages", "mu", "sigma")),
                    tuple(student[name][student_indices] for name in ("obs", "privileged", "history", "actions", "log_prob", "advantages")),
                    critic[full_indices], values[full_indices], returns[full_indices],
                )

    def clear(self):
        self.step = 0

    add_transitions = add
