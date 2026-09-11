from collections import deque

import torch
import torch.nn.functional as F
from isaacgym import gymtorch
from legged_gym.envs.a1.a1_config import A1RoughCfg, A1RoughCfgPPO
from legged_gym.envs.base.legged_robot import LeggedRobot


class A1CTSCfg(A1RoughCfg):
    class env(A1RoughCfg.env):
        num_observations = 45
        num_teacher_obs = 99
        num_latent_dims = 99
        num_single_critic_obs = 96
        # LeggedGym-Ex keeps the encoder input (privileged observation) and
        # the recurrent critic input as separate contracts.  The former is
        # the 99-D teacher observation; the latter is 5 x 96 = 480-D.
        num_privileged_obs = 99
        num_critic_obs = 480
        frame_stack = 20
        num_history_obs = 900
        c_frame_stack = 5


class A1CTSCfgPPO(A1RoughCfgPPO):
    class policy(A1RoughCfgPPO.policy):
        # Match Go2CTSCfgPPO: CTS uses the base actor width [512, 256, 128].
        actor_hidden_dims = [512, 256, 128]
        critic_hidden_dims = [1024, 256, 128]
        privilege_encoder_hidden_dims = [256, 128]
        history_encoder_hidden_dims = [256, 128]

    class algorithm(A1RoughCfgPPO.algorithm):
        encoder_lr = 5.0e-4
        num_encoder_epochs = 1

    class runner(A1RoughCfgPPO.runner):
        num_steps_per_env = 24
        save_interval = 300
        experiment_name = "a1_cts"


class A1CTS(LeggedRobot):
    """A1 task exposing the concurrent teacher/student observation contracts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.num_envs < 4 or self.num_envs % 4:
            raise ValueError("CTS requires num_envs to be a positive multiple of 4")
        self.num_teacher = self.num_envs * 3 // 4
        self.num_observations = self.num_obs
        self.num_history_obs = self.cfg.env.num_history_obs
        self.num_teacher_obs = self.cfg.env.num_teacher_obs
        self.num_latent_dims = self.cfg.env.num_latent_dims
        self.num_critic_obs = self.cfg.env.num_critic_obs
        rigid_body_tensor = self.gym.acquire_rigid_body_state_tensor(self.sim)
        self.gym.refresh_rigid_body_state_tensor(self.sim)
        self.rigid_body_states = gymtorch.wrap_tensor(rigid_body_tensor).view(self.num_envs, -1, 13)
        # LeggedGym-Ex does not use Isaac Gym's native rigid-body order for
        # privileged contacts.  The CTS contract is grouped as
        # thigh -> calf -> foot -> base -> hip.
        body_names = self.gym.get_actor_rigid_body_names(self.envs[0], self.actor_handles[0])
        ordered = []
        for suffix in ("_thigh", "_calf", "_foot", "base", "_hip"):
            ordered.extend(
                index for index, name in enumerate(body_names)
                if name.lower() == suffix or name.lower().endswith(suffix)
            )
        if len(ordered) != 17:
            raise RuntimeError(
                "CTS contact-state contract requires 17 links in thigh/calf/foot/base/hip order; got %d from %s"
                % (len(ordered), body_names)
            )
        self.contact_state_indices = torch.tensor(ordered, dtype=torch.long, device=self.device)
        self.observation_history = deque(maxlen=20)
        self.critic_history = deque(maxlen=5)
        for _ in range(20):
            self.observation_history.append(torch.zeros(self.num_envs, 45, device=self.device))
        for _ in range(5):
            self.critic_history.append(torch.zeros(self.num_envs, 96, device=self.device))
        self.teacher_obs_buf = torch.zeros(self.num_envs, 99, device=self.device)
        self.compute_observations()

    def _current_observation(self):
        # Match LeggedGym-Ex Go2CTS ordering exactly:
        # commands, gravity, angular velocity, joint position, joint velocity, actions.
        return torch.cat((self.commands[:, :3] * self.commands_scale, self.projected_gravity, self.base_ang_vel * self.obs_scales.ang_vel, (self.dof_pos - self.default_dof_pos) * self.obs_scales.dof_pos, self.dof_vel * self.obs_scales.dof_vel, self.actions), dim=-1)

    def _privileged_domain_info(self):
        friction = getattr(self, "friction_coeffs", torch.ones(self.num_envs, 1, device=self.device)).reshape(self.num_envs, -1)[:, :1]
        return torch.cat((friction.to(self.device), getattr(self, "added_base_mass", torch.zeros(self.num_envs, 1, device=self.device)), getattr(self, "base_com_bias", torch.zeros(self.num_envs, 3, device=self.device)), getattr(self, "push_velocities", torch.zeros(self.num_envs, 2, device=self.device)), self.Kp_factors, self.Kd_factors), dim=-1)

    def _process_rigid_body_props(self, props, env_id):
        mass = props[0].mass
        com = (props[0].com.x, props[0].com.y, props[0].com.z)
        props = super()._process_rigid_body_props(props, env_id)
        if not hasattr(self, "added_base_mass"):
            self.added_base_mass = torch.zeros(self.num_envs, 1, device=self.device)
            self.base_com_bias = torch.zeros(self.num_envs, 3, device=self.device)
        self.added_base_mass[env_id, 0] = props[0].mass - mass
        self.base_com_bias[env_id] = torch.tensor((props[0].com.x - com[0], props[0].com.y - com[1], props[0].com.z - com[2]), device=self.device)
        return props

    def _push_robots(self):
        super()._push_robots()
        self.push_velocities = self.root_states[:, 7:9].clone()

    def _terrain_height_at_xy(self, xy):
        if self.cfg.terrain.mesh_type == "plane" or self.height_samples is None:
            return torch.zeros(xy.shape[:-1], device=self.device)
        points = ((xy + self.cfg.terrain.border_size) / self.cfg.terrain.horizontal_scale).long()
        px = points[..., 0].clamp(0, self.height_samples.shape[0] - 2)
        py = points[..., 1].clamp(0, self.height_samples.shape[1] - 2)
        height = torch.minimum(self.height_samples[px, py], self.height_samples[px + 1, py])
        return torch.minimum(height, self.height_samples[px, py + 1]) * self.cfg.terrain.vertical_scale

    def _terrain_sample_at_xy(self, xy):
        """Raw heightfield sample, matching `_calc_terrain_info_around_feet`.

        CTS's 9-point teacher input is deliberately not Legged Gym's
        conservative min-of-three collision-height query.
        """
        if self.cfg.terrain.mesh_type == "plane" or self.height_samples is None:
            return torch.zeros(xy.shape[:-1], device=self.device)
        points = ((xy + self.cfg.terrain.border_size) / self.cfg.terrain.horizontal_scale).long()
        px = points[..., 0].clamp(0, self.height_samples.shape[0] - 1)
        py = points[..., 1].clamp(0, self.height_samples.shape[1] - 1)
        return self.height_samples[px, py] * self.cfg.terrain.vertical_scale

    def _foot_ground_geometry(self):
        """Return the exact 9-point terrain contract used by LeggedGym-Ex.

        The upstream simulator exposes terrain heights around each foot (not
        foot clearance), followed by a normal whose z component is -1.  The
        old port returned clearance and the negated normal, changing all 99-D
        teacher targets even on a flat plane.
        """
        self.gym.refresh_rigid_body_state_tensor(self.sim)
        feet = self.rigid_body_states[:, self.feet_indices, :3]
        delta = float(self.cfg.terrain.horizontal_scale)
        offsets = torch.tensor(((-delta, 0.), (delta, 0.), (0., -delta),
                                (0., delta), (0., 0.), (-delta, -delta),
                                (delta, delta), (-delta, delta), (delta, -delta)),
                               device=self.device)
        heights = self._terrain_sample_at_xy(feet[:, :, None, :2] + offsets)
        dx = (heights[:, :, 1] - heights[:, :, 0]) / (2 * delta)
        dy = (heights[:, :, 3] - heights[:, :, 2]) / (2 * delta)
        normals = F.normalize(torch.stack((dx, dy, -torch.ones_like(dx)), dim=-1), dim=-1)
        return heights, normals

    def _teacher_observation(self):
        contacts = (torch.norm(self.contact_forces[:, self.contact_state_indices], dim=-1) > 1.).float()
        geometry, normals = self._foot_ground_geometry()
        teacher = torch.cat((self._privileged_domain_info(), geometry.flatten(1), normals.flatten(1), self.base_lin_vel[:, :3] * self.obs_scales.lin_vel, contacts), dim=-1)
        if teacher.shape[-1] != self.cfg.env.num_teacher_obs:
            raise RuntimeError("CTS teacher observation contract mismatch: got %d expected %d" % (teacher.shape[-1], self.cfg.env.num_teacher_obs))
        return teacher

    def compute_observations(self):
        current = self._current_observation()
        if not hasattr(self, "observation_history"):
            self.obs_buf = current
            return
        contacts = (torch.norm(self.contact_forces[:, self.contact_state_indices], dim=-1) > 1.).float()
        critic = torch.cat((current, self._privileged_domain_info(), self.base_lin_vel[:, :3] * self.obs_scales.lin_vel, contacts), dim=-1)
        actor = current
        if getattr(self, "add_noise", False):
            actor = actor + (2 * torch.rand_like(actor) - 1) * self.noise_scale_vec
        self.obs_buf = actor
        self.observation_history.append(actor)
        self.teacher_obs_buf = self._teacher_observation()
        self.critic_history.append(critic)
        self.privileged_obs_buf = torch.cat(tuple(self.critic_history), dim=-1)
        if critic.shape[-1] != self.cfg.env.num_single_critic_obs:
            raise RuntimeError("CTS critic observation contract mismatch: got %d expected %d" % (critic.shape[-1], self.cfg.env.num_single_critic_obs))

    def _get_noise_scale_vec(self, cfg):
        noise = torch.zeros(45, device=self.device)
        scales, level = cfg.noise.noise_scales, cfg.noise.noise_level
        noise[0:3] = 0.  # commands
        noise[3:6] = scales.gravity * level
        noise[6:9] = scales.ang_vel * level * self.obs_scales.ang_vel
        noise[9:21] = scales.dof_pos * level * self.obs_scales.dof_pos
        noise[21:33] = scales.dof_vel * level * self.obs_scales.dof_vel
        self.add_noise = cfg.noise.add_noise
        return noise

    def reset_idx(self, env_ids):
        super().reset_idx(env_ids)
        if hasattr(self, "observation_history"):
            for value in self.observation_history:
                value[env_ids] = 0
            for value in self.critic_history:
                value[env_ids] = 0

    def get_observation_history(self):
        return torch.cat(tuple(self.observation_history), dim=-1)

    def get_teacher_observations(self):
        return self.teacher_obs_buf

    def get_critic_observations(self):
        return self.privileged_obs_buf


def register_task(task_registry):
    if "a1_cts" not in task_registry.task_classes:
        task_registry.register("a1_cts", A1CTS, A1CTSCfg(), A1CTSCfgPPO())
    return "a1_cts"
