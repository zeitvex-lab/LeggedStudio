import json
import os
import time

import torch

from .algorithm import PPOTS
from .model import ActorCriticTS


class TeacherStudentRunner:
    def __init__(self, env, train_cfg, log_dir=None, device="cpu"):
        self.env, self.log_dir, self.device = env, log_dir, device
        policy_cfg = train_cfg.get("policy", {}); alg_cfg = train_cfg.get("algorithm", {}); runner_cfg = train_cfg.get("runner", {})
        self.num_steps_per_env = int(runner_cfg.get("num_steps_per_env", 24))
        model_kwargs = {k: v for k, v in policy_cfg.items() if k in {"actor_hidden_dims", "critic_hidden_dims", "privilege_encoder_hidden_dims", "history_encoder_hidden_dims", "history_encoder_type"}}
        self.policy = ActorCriticTS(num_actions=env.num_actions, actor_obs=env.num_observations, teacher_obs=env.num_teacher_obs, history_dim=env.num_history_obs, latent_dim=env.num_latent_dims, critic_obs=env.num_critic_obs, **model_kwargs).to(device)
        self.alg = PPOTS(self.policy, alg_cfg, device); self.alg.init_storage(env, self.num_steps_per_env)
        self.current_learning_iteration = 0; self.save_interval = int(runner_cfg.get("save_interval", 100)); self.metrics = []
        env.reset()

    def learn(self, num_learning_iterations, init_at_random_ep_len=False):
        if init_at_random_ep_len and hasattr(self.env, "episode_length_buf"):
            self.env.episode_length_buf = torch.randint_like(self.env.episode_length_buf, high=int(self.env.max_episode_length))
        obs = self.env.get_observations().to(self.device); history = self.env.get_observation_history().to(self.device); teacher = self.env.get_teacher_observations().to(self.device); critic = self.env.get_critic_observations().to(self.device)
        for _ in range(num_learning_iterations):
            start = time.time(); rollout_reward = 0.0; rollout_done = 0
            with torch.no_grad():
                for _ in range(self.num_steps_per_env):
                    action = self.alg.act(obs, teacher, history, critic); obs, _, reward, done, infos = self.env.step(action)
                    history = self.env.get_observation_history().to(self.device); teacher = self.env.get_teacher_observations().to(self.device); critic = self.env.get_critic_observations().to(self.device); obs = obs.to(self.device); reward, done = reward.to(self.device), done.to(self.device)
                    self.alg.process_env_step(reward, done, infos); rollout_reward += float(reward.mean().item()); rollout_done += int(done.sum().item())
            self.alg.compute_returns(critic); losses = self.alg.update(); self.current_learning_iteration += 1
            self.metrics.append({"iteration": self.current_learning_iteration, "mean_reward": rollout_reward / max(self.num_steps_per_env, 1), "done_count": rollout_done, "done_rate": rollout_done / max(self.num_steps_per_env * self.env.num_envs, 1), "collection_seconds": time.time() - start, **losses})
            if self.log_dir and self.current_learning_iteration % self.save_interval == 0: self.save(os.path.join(self.log_dir, "model_%d.pt" % self.current_learning_iteration))
        if self.log_dir:
            self.save(os.path.join(self.log_dir, "model_%d.pt" % self.current_learning_iteration))
            with open(os.path.join(self.log_dir, "training_metrics.json"), "w") as stream: json.dump(self.metrics, stream, indent=2)

    def save(self, path):
        torch.save({"model_state_dict": self.policy.state_dict(), "optimizer_state_dict": self.alg.rl_optimizer.state_dict(), "history_optimizer_state_dict": self.alg.history_optimizer.state_dict(), "iter": self.current_learning_iteration, "architecture": "teacher-student-a1-v3-obs45-history900-teacher99-latent99-critic480"}, path)

    def load(self, path):
        state = torch.load(path, map_location=self.device); expected = "teacher-student-a1-v3-obs45-history900-teacher99-latent99-critic480"
        if state.get("architecture") != expected: raise RuntimeError("incompatible Teacher-Student checkpoint: expected %s; retraining is required" % expected)
        self.policy.load_state_dict(state["model_state_dict"])
        if state.get("optimizer_state_dict"): self.alg.rl_optimizer.load_state_dict(state["optimizer_state_dict"])
        if state.get("history_optimizer_state_dict"): self.alg.history_optimizer.load_state_dict(state["history_optimizer_state_dict"])
        self.current_learning_iteration = state.get("iter", 0)

    def get_inference_policy(self, device=None):
        if device is not None: self.policy.to(device)
        self.policy.eval(); return lambda obs: self.policy.act_student(obs, self.env.get_observation_history().to(obs.device))
