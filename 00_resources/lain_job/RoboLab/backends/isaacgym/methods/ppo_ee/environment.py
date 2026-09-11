import torch

from legged_gym.envs.a1.a1_config import A1RoughCfg, A1RoughCfgPPO
from legged_gym.envs.base.legged_robot import LeggedRobot


class A1EECfg(A1RoughCfg):
    class env(A1RoughCfg.env):
        num_observations = 225
        num_privileged_obs = 56
        frame_stack = 5
        num_single_obs = 45
        num_estimator_labels = 11


class A1EECfgPPO(A1RoughCfgPPO):
    class policy(A1RoughCfgPPO.policy):
        actor_hidden_dims = [256, 128]
        critic_hidden_dims = [256, 128]
        estimator_hidden_dims = [128, 64]
    class algorithm(A1RoughCfgPPO.algorithm):
        num_learning_epochs = 5
        num_mini_batches = 4
        estimator_lr = 2e-4
        num_estimator_epochs = 1
    class runner(A1RoughCfgPPO.runner):
        num_steps_per_env = 24
        save_interval = 100
        experiment_name = "a1_ee"


class A1ExplicitEstimator(LeggedRobot):
    num_single_obs = 45
    num_estimator_features = 225
    num_estimator_labels = 11

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.observation_history = torch.zeros(
            self.num_envs, 5, self.num_single_obs, device=self.device
        )
        self.estimator_labels = torch.zeros(
            self.num_envs, self.num_estimator_labels, device=self.device
        )
        self.compute_observations()

    def _get_noise_scale_vec(self, cfg):
        self.add_noise = cfg.noise.add_noise
        noise = torch.zeros(self.num_single_obs, device=self.device)
        scales, level = cfg.noise.noise_scales, cfg.noise.noise_level
        noise[:3] = scales.ang_vel * level * self.obs_scales.ang_vel
        noise[3:6] = scales.gravity * level
        noise[9:21] = scales.dof_pos * level * self.obs_scales.dof_pos
        noise[21:33] = scales.dof_vel * level * self.obs_scales.dof_vel
        return noise

    def reset_idx(self, env_ids):
        super().reset_idx(env_ids)
        if hasattr(self, "observation_history") and len(env_ids):
            self.observation_history[env_ids] = 0.0

    def compute_observations(self):
        current = torch.cat((
            self.base_ang_vel * self.obs_scales.ang_vel,
            self.projected_gravity,
            self.commands[:, :3] * self.commands_scale,
            (self.dof_pos - self.default_dof_pos) * self.obs_scales.dof_pos,
            self.dof_vel * self.obs_scales.dof_vel,
            self.actions,
        ), dim=-1)
        if self.add_noise:
            current += (2 * torch.rand_like(current) - 1) * self.noise_scale_vec
        if not hasattr(self, "observation_history"):
            self.obs_buf = current
            return
        self.observation_history = torch.roll(self.observation_history, shifts=-1, dims=1)
        self.observation_history[:, -1] = current
        self.obs_buf = self.observation_history.flatten(1)
        foot_forces = torch.norm(self.contact_forces[:, self.feet_indices], dim=-1)
        contacts = (foot_forces > 1.0).float()
        scaled_forces = torch.clamp(foot_forces / 100.0, 0.0, 1.0)
        self.estimator_labels = torch.cat((
            self.base_lin_vel * self.obs_scales.lin_vel,
            contacts,
            scaled_forces,
        ), dim=-1)
        self.privileged_obs_buf = torch.cat((current, self.estimator_labels), dim=-1)

    def get_estimator_labels(self):
        return self.estimator_labels

    def get_observations(self):
        return self.obs_buf

    def get_privileged_observations(self):
        return self.privileged_obs_buf

    def reset(self):
        self.reset_idx(torch.arange(self.num_envs, device=self.device))
        LeggedRobot.step(self, torch.zeros(self.num_envs, self.num_actions, device=self.device))
        return self.obs_buf, self.privileged_obs_buf

    def step(self, actions):
        obs, privileged, rewards, dones, infos = LeggedRobot.step(self, actions)
        return obs, privileged, rewards, dones, infos


def register_task(task_registry):
    if "a1_ee" not in task_registry.task_classes:
        task_registry.register("a1_ee", A1ExplicitEstimator, A1EECfg(), A1EECfgPPO())
    return "a1_ee"
