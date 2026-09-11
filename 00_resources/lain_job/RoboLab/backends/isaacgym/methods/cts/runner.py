import json
import os
import time

import torch
from torch.utils.tensorboard import SummaryWriter

from .algorithm import PPOCTS
from .model import ActorCriticCTS


CHECKPOINT_ARCHITECTURE = "cts-a1-v1-obs45-history900-teacher99-latent99-critic480-teacher75pct"


class CTSRunner:
    def __init__(self, env, train_cfg, log_dir=None, device="cpu"):
        self.env = env
        self.log_dir = log_dir
        self.device = device
        policy_cfg = train_cfg.get("policy", {})
        algorithm_cfg = train_cfg.get("algorithm", {})
        runner_cfg = train_cfg.get("runner", {})
        self.num_steps_per_env = int(runner_cfg.get("num_steps_per_env", 24))
        model_kwargs = {key: value for key, value in policy_cfg.items() if key in {"actor_hidden_dims", "critic_hidden_dims", "privilege_encoder_hidden_dims", "history_encoder_hidden_dims"}}
        self.policy = ActorCriticCTS(num_actions=env.num_actions, actor_obs=env.num_observations, teacher_obs=env.num_teacher_obs, history_dim=env.num_history_obs, latent_dim=env.num_latent_dims, critic_obs=env.num_critic_obs, **model_kwargs).to(device)
        self.alg = PPOCTS(self.policy, algorithm_cfg, device, env.num_teacher)
        self.alg.init_storage(env, self.num_steps_per_env)
        self.current_learning_iteration = 0
        self.save_interval = int(runner_cfg.get("save_interval", 100))
        self.metrics = []
        self.writer = SummaryWriter(log_dir=log_dir, flush_secs=10) if log_dir else None
        env.reset()

    def learn(self, num_learning_iterations, init_at_random_ep_len=False):
        if init_at_random_ep_len and hasattr(self.env, "episode_length_buf"):
            self.env.episode_length_buf = torch.randint_like(self.env.episode_length_buf, high=int(self.env.max_episode_length))
        observations = self.env.get_observations().to(self.device)
        teacher_observations = self.env.get_teacher_observations().to(self.device)
        observation_history = self.env.get_observation_history().to(self.device)
        critic_observations = self.env.get_critic_observations().to(self.device)
        self.policy.train()
        for _ in range(num_learning_iterations):
            start = time.time()
            rollout_reward = 0.0
            rollout_done = 0
            with torch.no_grad():
                for _ in range(self.num_steps_per_env):
                    actions = self.alg.act(observations, teacher_observations, observation_history, critic_observations)
                    observations, _, rewards, dones, infos = self.env.step(actions)
                    observations = observations.to(self.device)
                    rewards = rewards.to(self.device)
                    dones = dones.to(self.device)
                    teacher_observations = self.env.get_teacher_observations().to(self.device)
                    observation_history = self.env.get_observation_history().to(self.device)
                    critic_observations = self.env.get_critic_observations().to(self.device)
                    self.alg.process_env_step(rewards, dones, infos)
                    rollout_reward += float(rewards.mean().item())
                    rollout_done += int(dones.sum().item())
            self.alg.compute_returns(critic_observations)
            losses = self.alg.update()
            self.current_learning_iteration += 1
            metric = {"iteration": self.current_learning_iteration, "mean_reward": rollout_reward / self.num_steps_per_env, "done_count": rollout_done, "done_rate": rollout_done / (self.num_steps_per_env * self.env.num_envs), "collection_seconds": time.time() - start, **losses}
            self.metrics.append(metric)
            if self.writer is not None:
                for name, value in metric.items():
                    if name != "iteration" and isinstance(value, (int, float)):
                        self.writer.add_scalar(name, value, self.current_learning_iteration)
            if self.log_dir and self.current_learning_iteration % self.save_interval == 0:
                self.save(os.path.join(self.log_dir, "model_%d.pt" % self.current_learning_iteration))
        if self.log_dir:
            self.save(os.path.join(self.log_dir, "model_%d.pt" % self.current_learning_iteration))
            with open(os.path.join(self.log_dir, "training_metrics.json"), "w") as stream:
                json.dump(self.metrics, stream, indent=2)
        if self.writer is not None:
            self.writer.flush()
            self.writer.close()

    def save(self, path):
        torch.save({"model_state_dict": self.policy.state_dict(), "optimizer_state_dict": self.alg.rl_optimizer.state_dict(), "history_optimizer_state_dict": self.alg.history_optimizer.state_dict(), "iter": self.current_learning_iteration, "architecture": CHECKPOINT_ARCHITECTURE}, path)

    def load(self, path):
        state = torch.load(path, map_location=self.device)
        if state.get("architecture") != CHECKPOINT_ARCHITECTURE:
            raise RuntimeError("incompatible CTS checkpoint: expected %s; retraining is required" % CHECKPOINT_ARCHITECTURE)
        self.policy.load_state_dict(state["model_state_dict"])
        if state.get("optimizer_state_dict"):
            self.alg.rl_optimizer.load_state_dict(state["optimizer_state_dict"])
        if state.get("history_optimizer_state_dict"):
            self.alg.history_optimizer.load_state_dict(state["history_optimizer_state_dict"])
        self.current_learning_iteration = state.get("iter", 0)

    def get_inference_policy(self, device=None):
        if device is not None:
            self.policy.to(device)
        self.policy.eval()
        return lambda observations: self.policy.act_student_deterministic(observations, self.env.get_observation_history().to(observations.device))
