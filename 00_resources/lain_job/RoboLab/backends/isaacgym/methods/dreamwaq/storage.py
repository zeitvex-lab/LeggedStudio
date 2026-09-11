import torch


class RolloutStorageDreamWaQ:
    class Transition:
        def __init__(self):
            self.observations = None
            self.critic_observations = None
            self.observation_histories = None
            self.explicit_labels = None
            self.next_states = None
            self.actions = None
            self.rewards = None
            self.dones = None
            self.values = None
            self.actions_log_prob = None
            self.action_mean = None
            self.action_sigma = None

        def clear(self):
            self.__init__()

    def __init__(
        self,
        num_envs,
        num_steps,
        obs_dim,
        critic_dim,
        history_dim,
        explicit_dim,
        next_state_dim,
        action_dim,
        device,
    ):
        shape = (num_steps, num_envs)
        self.observations = torch.zeros(*shape, obs_dim, device=device)
        self.critic_observations = torch.zeros(*shape, critic_dim, device=device)
        self.observation_histories = torch.zeros(*shape, history_dim, device=device)
        self.explicit_labels = torch.zeros(*shape, explicit_dim, device=device)
        self.next_states = torch.zeros(*shape, next_state_dim, device=device)
        self.actions = torch.zeros(*shape, action_dim, device=device)
        self.rewards = torch.zeros(*shape, 1, device=device)
        self.dones = torch.zeros(*shape, 1, dtype=torch.bool, device=device)
        self.values = torch.zeros(*shape, 1, device=device)
        self.actions_log_prob = torch.zeros(*shape, 1, device=device)
        self.mu = torch.zeros(*shape, action_dim, device=device)
        self.sigma = torch.zeros(*shape, action_dim, device=device)
        self.returns = torch.zeros_like(self.values)
        self.advantages = torch.zeros_like(self.values)
        self.num_steps = num_steps
        self.num_transitions_per_env = num_steps
        self.num_envs = num_envs
        self.device = device
        self.step = 0

    def add(self, transition):
        if self.step >= self.num_steps:
            raise RuntimeError("DreamWaQ rollout buffer overflow")
        index = self.step
        self.observations[index].copy_(transition.observations)
        self.critic_observations[index].copy_(transition.critic_observations)
        self.observation_histories[index].copy_(transition.observation_histories)
        self.explicit_labels[index].copy_(transition.explicit_labels)
        self.next_states[index].copy_(transition.next_states)
        self.actions[index].copy_(transition.actions)
        self.rewards[index].copy_(transition.rewards.view(-1, 1))
        self.dones[index].copy_(transition.dones.view(-1, 1).bool())
        self.values[index].copy_(transition.values)
        self.actions_log_prob[index].copy_(transition.actions_log_prob.view(-1, 1))
        self.mu[index].copy_(transition.action_mean)
        self.sigma[index].copy_(transition.action_sigma)
        self.step += 1

    def compute_returns(self, last_values, gamma, lam):
        advantage = torch.zeros_like(last_values)
        for step in reversed(range(self.num_steps)):
            next_values = last_values if step == self.num_steps - 1 else self.values[step + 1]
            not_done = (~self.dones[step]).float()
            delta = self.rewards[step] + gamma * next_values * not_done - self.values[step]
            advantage = delta + gamma * lam * not_done * advantage
            self.returns[step] = advantage + self.values[step]
        self.advantages.copy_(self.returns - self.values)
        mean = self.advantages.mean()
        std = self.advantages.std(unbiased=False)
        self.advantages.sub_(mean).div_(std + 1e-8)

    def mini_batch_generator(self, num_mini_batches, num_epochs):
        total = self.num_steps * self.num_envs
        if num_mini_batches < 1 or num_mini_batches > total:
            raise ValueError(
                "num_mini_batches must be between 1 and rollout size; got %d for %d samples"
                % (num_mini_batches, total)
            )
        flat_names = (
            "observations",
            "critic_observations",
            "observation_histories",
            "explicit_labels",
            "next_states",
            "actions",
            "values",
            "advantages",
            "returns",
            "actions_log_prob",
            "mu",
            "sigma",
            "dones",
        )
        flat = {name: getattr(self, name).flatten(0, 1) for name in flat_names}
        for _ in range(num_epochs):
            indices = torch.randperm(total, device=self.device)
            for batch_indices in torch.tensor_split(indices, num_mini_batches):
                yield tuple(flat[name][batch_indices] for name in flat_names)

    def clear(self):
        self.step = 0

    add_transitions = add
