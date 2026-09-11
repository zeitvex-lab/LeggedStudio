import torch


class RolloutStorageEE:
    class Transition:
        def __init__(self):
            self.features = self.labels = self.critic = None
            self.actions = self.rewards = self.dones = self.values = None
            self.log_prob = self.mu = self.sigma = None
        def clear(self): self.__init__()

    def __init__(self, envs, steps, feature_dim, label_dim, critic_dim, action_dim, device):
        shape = (steps, envs)
        self.features = torch.zeros(*shape, feature_dim, device=device)
        self.labels = torch.zeros(*shape, label_dim, device=device)
        self.critic = torch.zeros(*shape, critic_dim, device=device)
        self.actions = torch.zeros(*shape, action_dim, device=device)
        self.rewards = torch.zeros(*shape, 1, device=device)
        self.dones = torch.zeros(*shape, 1, device=device)
        self.values = torch.zeros(*shape, 1, device=device)
        self.log_prob = torch.zeros(*shape, 1, device=device)
        self.mu = torch.zeros(*shape, action_dim, device=device)
        self.sigma = torch.zeros(*shape, action_dim, device=device)
        self.returns = torch.zeros_like(self.values)
        self.advantages = torch.zeros_like(self.values)
        self.step = 0; self.steps = steps; self.envs = envs; self.device = device

    def add(self, t):
        i = self.step
        for name in ("features", "labels", "critic", "actions", "rewards", "dones", "values", "log_prob", "mu", "sigma"):
            value = getattr(t, name)
            target = getattr(self, name)[i]
            target.copy_(value.view_as(target) if name in ("rewards", "dones", "log_prob") else value)
        self.step += 1

    def compute_returns(self, last, gamma, lam):
        adv = 0
        for i in reversed(range(self.steps)):
            next_value = last if i == self.steps - 1 else self.values[i + 1]
            mask = 1 - self.dones[i]
            delta = self.rewards[i] + mask * gamma * next_value - self.values[i]
            adv = delta + mask * gamma * lam * adv
            self.returns[i] = adv + self.values[i]
        self.advantages = self.returns - self.values
        self.advantages = (self.advantages - self.advantages.mean()) / (self.advantages.std() + 1e-8)

    def batches(self, minibatches):
        total = self.envs * self.steps; size = total // minibatches
        ids = torch.randperm(size * minibatches, device=self.device)
        values = [getattr(self, name).flatten(0, 1) for name in ("critic", "features", "labels", "actions", "values", "advantages", "returns", "log_prob", "mu", "sigma", "dones")]
        for index in ids.split(size): yield [value[index] for value in values]

    def clear(self): self.step = 0
