import os
import torch

from .algorithm import PPOEE
from .model import ActorCriticEE


class EERunner:
    def __init__(self, env, train_cfg, log_dir=None, device="cpu"):
        self.env, self.log_dir, self.device = env, log_dir, device
        policy_cfg, alg_cfg = train_cfg["policy"], train_cfg["algorithm"]
        self.num_steps_per_env = train_cfg["runner"].get("num_steps_per_env", 24)
        self.policy = ActorCriticEE(env.num_estimator_features, env.num_privileged_obs, env.num_actions, env.num_estimator_labels, **policy_cfg).to(device)
        self.alg = PPOEE(self.policy, alg_cfg, device); self.alg.init_storage(env, self.num_steps_per_env)
        self.current_learning_iteration = 0; self.save_interval = train_cfg["runner"].get("save_interval", 1)
        env.reset()

    def learn(self, num_learning_iterations, init_at_random_ep_len=False):
        features = self.env.get_observations(); labels = self.env.get_estimator_labels(); critic = self.env.get_privileged_observations()
        features, labels, critic = features.to(self.device), labels.to(self.device), critic.to(self.device)
        for _ in range(num_learning_iterations):
            with torch.inference_mode():
                for _ in range(self.alg.storage.steps):
                    actions = self.alg.act(features, critic, labels)
                    features, critic, rewards, dones, infos = self.env.step(actions)
                    labels = self.env.get_estimator_labels()
                    features, labels, critic = features.to(self.device), labels.to(self.device), critic.to(self.device); self.alg.process(rewards.to(self.device), dones.to(self.device), infos)
                self.alg.storage.compute_returns(self.policy.evaluate(critic).detach(), self.alg.gamma, self.alg.lam)
            self.alg.update(); self.current_learning_iteration += 1
            if self.log_dir and self.current_learning_iteration % self.save_interval == 0: self.save(os.path.join(self.log_dir, "model_{}.pt".format(self.current_learning_iteration)))

    def save(self, path): torch.save({"model_state_dict": self.policy.state_dict(), "iter": self.current_learning_iteration}, path)
    def load(self, path):
        state = torch.load(path, map_location=self.device); self.policy.load_state_dict(state["model_state_dict"]); self.current_learning_iteration = state.get("iter", 0)
    def get_inference_policy(self, device=None):
        if device is not None:
            self.policy.to(device)
        self.policy.eval()
        return self.policy.act_inference
