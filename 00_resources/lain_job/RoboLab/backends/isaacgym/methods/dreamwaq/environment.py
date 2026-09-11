import torch
import torch.nn.functional as F
from isaacgym import gymtorch
from legged_gym.envs.a1.a1_config import A1RoughCfg, A1RoughCfgPPO
from legged_gym.envs.base.legged_robot import LeggedRobot


class A1DreamWaQCfg(A1RoughCfg):
    class env(A1RoughCfg.env):
        num_observations = 45
        num_single_critic_obs = 96
        num_privileged_obs = 480
        frame_stack = 5
        num_history_obs = 225
        num_latent_dims = 16
        num_explicit_dims = 24
        num_decoder_output = 45
        c_frame_stack = 5


class A1DreamWaQCfgPPO(A1RoughCfgPPO):
    class policy(A1RoughCfgPPO.policy):
        actor_hidden_dims = [512, 256, 128]
        critic_hidden_dims = [1024, 256, 128]
        encoder_hidden_dims = [256, 128]
        decoder_hidden_dims = [256, 128]
        activation = "elu"
        init_noise_std = 1.0
        num_latent_dims = 16
        num_explicit_dims = 24
    class algorithm(A1RoughCfgPPO.algorithm):
        encoder_lr = 2e-4
        num_encoder_epochs = 1
        vae_kld_weight = 2.0
    class runner(A1RoughCfgPPO.runner):
        num_steps_per_env = 24
        # Keep the final checkpoint available for one-iteration smoke runs;
        # longer recipes may override this explicitly.
        save_interval = 300
        experiment_name = "a1_dreamwaq"


class A1DreamWaQ(LeggedRobot):
    num_history = 5
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.num_observations = self.num_obs
        self.num_history_obs = self.cfg.env.num_history_obs
        self.num_latent_dims = self.cfg.env.num_latent_dims
        self.num_explicit_dims = self.cfg.env.num_explicit_dims
        self.num_decoder_output = self.cfg.env.num_decoder_output
        rigid_body_state = self.gym.acquire_rigid_body_state_tensor(self.sim)
        self.gym.refresh_rigid_body_state_tensor(self.sim)
        self.rigid_body_states = gymtorch.wrap_tensor(rigid_body_state).view(self.num_envs, -1, 13)
        # Match the reference link-contact ordering: thigh, calf, foot, base,
        # then hip. Isaac Gym's native body order is different.
        try:
            body_names = self.gym.get_actor_rigid_body_names(self.envs[0], self.actor_handles[0])
            ordered = []
            for suffix in ("_thigh", "_calf", "_foot", "base", "_hip"):
                ordered.extend(
                    i for i, name in enumerate(body_names)
                    if name.lower() == suffix or name.lower().endswith(suffix)
                )
        except Exception:
            raise RuntimeError("DreamWaQ requires Isaac Gym rigid-body names to order contact labels")
        if len(ordered) != 17:
            raise RuntimeError(
                "DreamWaQ contact-state contract requires 17 links (thigh, calf, foot, base, hip); got %d from %s"
                % (len(ordered), body_names)
            )
        self.contact_state_indices = torch.tensor(ordered, dtype=torch.long, device=self.device)
        self.observation_history = torch.zeros(self.num_envs, self.num_history, 45, device=self.device)
        self.compute_observations()

    def compute_observations(self):
        current = torch.cat((self.commands[:, :3] * self.commands_scale, self.projected_gravity,
            self.base_ang_vel * self.obs_scales.ang_vel,
            (self.dof_pos - self.default_dof_pos) * self.obs_scales.dof_pos,
            self.dof_vel * self.obs_scales.dof_vel, self.actions), -1)
        if not hasattr(self, "observation_history"):
            self.obs_buf = current; return
        contacts = (torch.norm(self.contact_forces[:, self.contact_state_indices], dim=-1) > 1.0).float()
        # Keep the critic layout identical to LeggedGym-Ex:
        # base velocity, actor observation, then domain/contact/terrain state.
        critic_obs = torch.cat((self.base_lin_vel * self.obs_scales.lin_vel, current,
                                self._privileged_domain_info(), contacts), -1)
        if getattr(self.cfg.terrain, "measure_heights", False):
            heights = torch.clamp(self.root_states[:, 2:3] - 0.5 - self.measured_heights, -1, 1) * self.obs_scales.height_measurements
            critic_obs = torch.cat((critic_obs, heights), -1)
        # Keep the critic contract explicit: 5 x (actor obs + privileged state).
        if critic_obs.shape[-1] != self.cfg.env.num_single_critic_obs:
            raise RuntimeError("DreamWaQ critic observation contract mismatch: got %d expected %d" % (critic_obs.shape[-1], self.cfg.env.num_single_critic_obs))
        self.critic_history = getattr(self, "critic_history", None)
        if self.critic_history is None:
            from collections import deque
            self.critic_history = deque(maxlen=5)
            for _ in range(5):
                self.critic_history.append(torch.zeros_like(critic_obs))
        self.critic_history.append(critic_obs)
        self.privileged_obs_buf = torch.cat(tuple(self.critic_history), -1)
        self.decoder_target_buf = current.clone()
        self.decoder_target_buf[:, -self.num_actions:] *= self.cfg.control.action_scale
        actor_obs = current
        if self.add_noise:
            actor_obs = actor_obs + (2 * torch.rand_like(actor_obs) - 1) * self.noise_scale_vec
        self.observation_history = torch.roll(self.observation_history, -1, 1)
        self.observation_history[:, -1] = actor_obs
        self.obs_buf = actor_obs

    def reset_idx(self, env_ids):
        super().reset_idx(env_ids)
        if hasattr(self, "observation_history"):
            self.observation_history[env_ids] = 0
        if hasattr(self, "critic_history"):
            for value in self.critic_history:
                value[env_ids] = 0

    def get_observation_history(self): return self.observation_history.flatten(1)
    def get_decoder_target(self):
        return self.decoder_target_buf

    def _privileged_domain_info(self):
        friction = getattr(self, "friction_coeffs", torch.ones(self.num_envs, 1, device=self.device))
        friction = friction.reshape(self.num_envs, -1)[:, :1]
        mass = getattr(self, "added_base_mass", torch.zeros(self.num_envs, 1, device=self.device))
        com = getattr(self, "base_com_bias", torch.zeros(self.num_envs, 3, device=self.device))
        push = getattr(self, "push_velocities", torch.zeros(self.num_envs, 2, device=self.device))
        return torch.cat((friction.to(self.device), mass, com, push, self.Kp_factors, self.Kd_factors), -1)

    def _process_rigid_body_props(self, props, env_id):
        base_mass = props[0].mass
        base_com = (props[0].com.x, props[0].com.y, props[0].com.z)
        props = super()._process_rigid_body_props(props, env_id)
        if not hasattr(self, "added_base_mass"):
            self.added_base_mass = torch.zeros(self.num_envs, 1, device=self.device)
            self.base_com_bias = torch.zeros(self.num_envs, 3, device=self.device)
        self.added_base_mass[env_id, 0] = props[0].mass - base_mass
        self.base_com_bias[env_id] = torch.tensor((props[0].com.x - base_com[0], props[0].com.y - base_com[1], props[0].com.z - base_com[2]), device=self.device)
        return props

    def _push_robots(self):
        super()._push_robots()
        self.push_velocities = self.root_states[:, 7:9].clone()

    def _terrain_height_at_xy(self, xy):
        if self.cfg.terrain.mesh_type == "plane" or getattr(self, "height_samples", None) is None:
            return torch.zeros(xy.shape[:-1], device=self.device)
        points = ((xy + self.cfg.terrain.border_size) / self.cfg.terrain.horizontal_scale).long()
        px = points[..., 0].clamp(0, self.height_samples.shape[0] - 2)
        py = points[..., 1].clamp(0, self.height_samples.shape[1] - 2)
        height = torch.minimum(self.height_samples[px, py], self.height_samples[px + 1, py])
        height = torch.minimum(height, self.height_samples[px, py + 1])
        return height * self.cfg.terrain.vertical_scale

    def _foot_ground_geometry(self):
        self.gym.refresh_rigid_body_state_tensor(self.sim)
        feet = self.rigid_body_states[:, self.feet_indices, :3]
        offsets = torch.tensor([[-.05, -.05], [-.05, 0.], [-.05, .05], [0., -.05], [0., 0.], [0., .05], [.05, -.05], [.05, 0.], [.05, .05]], device=self.device)
        sample_xy = feet[:, :, None, :2] + offsets
        ground = self._terrain_height_at_xy(sample_xy)
        # Reference DreamWaQ uses the mean terrain height around each foot,
        # rather than an absolute world-frame foot z or a single sample.
        relative = feet[:, :, 2] - ground.mean(dim=-1) - getattr(self.cfg.rewards, "foot_height_offset", 0.0)
        delta = 0.05; x_offset = torch.tensor([delta, 0.], device=self.device); y_offset = torch.tensor([0., delta], device=self.device)
        dx = (self._terrain_height_at_xy(feet[:, :, :2] + x_offset) - self._terrain_height_at_xy(feet[:, :, :2] - x_offset)) / (2 * delta)
        dy = (self._terrain_height_at_xy(feet[:, :, :2] + y_offset) - self._terrain_height_at_xy(feet[:, :, :2] - y_offset)) / (2 * delta)
        normals = F.normalize(torch.stack((-dx, -dy, torch.ones_like(dx)), -1), dim=-1)
        return relative.clamp(-1.0, 1.0), normals
    def get_explicit_labels(self):
        # DreamWaQ's 24-D explicit target: base velocity (3), all rigid-body
        # contact states (17 for A1), and four foot-height values.
        contacts = (torch.norm(self.contact_forces[:, self.contact_state_indices], dim=-1) > 1.0).float()
        foot_geometry, _ = self._foot_ground_geometry()
        return torch.cat((
            # Reference DreamWaQ scales the velocity component by 0.5.
            self.base_lin_vel[:, :3] * self.obs_scales.lin_vel * 0.5,
            contacts,
            foot_geometry,
        ), -1)

    def _get_noise_scale_vec(self, cfg):
        noise = torch.zeros(45, device=self.device)
        scales, level = cfg.noise.noise_scales, cfg.noise.noise_level
        noise[3:6] = scales.gravity * level
        noise[6:9] = scales.ang_vel * level * self.obs_scales.ang_vel
        noise[9:21] = scales.dof_pos * level * self.obs_scales.dof_pos
        noise[21:33] = scales.dof_vel * level * self.obs_scales.dof_vel
        self.add_noise = cfg.noise.add_noise
        return noise


def register_task(task_registry):
    if "a1_dreamwaq" not in task_registry.task_classes:
        task_registry.register("a1_dreamwaq", A1DreamWaQ, A1DreamWaQCfg(), A1DreamWaQCfgPPO())
    return "a1_dreamwaq"
