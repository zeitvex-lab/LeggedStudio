"""族级技能的动作项。

来源：`go2_skills/shared/actions.py`（逐字上移）。与源实现的唯一变化是
`actuator_names` 不再由技能层写死 —— 它由机型绑定按契约 `action.joint_order`
传入（见 `trot/config.py` / `jump/config.py`）。

`DelayedJointPositionAction`（第二段）来源：`local_tasks/robots/unitree/go2/mdp/actions.py`
的 `Go2DelayedJointPositionAction`（速度跟踪的算法变体用：源 CTS/DreamWaQ/TS 族在四个
物理子步里随机切换新旧目标）。去机型化改动一处：它不再直接继承 mjlab 的
`JointPositionAction`，而是经 `kits/joint_actions.OrderedTargets` —— 换掉动作项实现时
**动作维序仍 = 契约 `action.joint_order`**（否则会静默退回模型序；对模型序与契约序
相同的机型是逐位等价，对不同的机型才是修正）。观测侧旁路（`observation_latency`）
是源特技任务的动作观测口径，一并保留。
"""

from dataclasses import dataclass
from typing import Literal

import torch
from mjlab.envs.mdp.actions import JointPositionAction, JointPositionActionCfg
from mjlab.utils.buffers import DelayBuffer
from mjlab.utils.lab_api.math import euler_xyz_from_quat

from ....joint_actions import OrderedTargets


class EpisodeDelayedJointPositionAction(JointPositionAction):
    """Per-environment action delay with Gym-compatible reset history."""

    def __init__(self, cfg: "EpisodeDelayedJointPositionActionCfg", env) -> None:
        super().__init__(cfg, env)
        self._source_delay = DelayBuffer(
            min_lag=cfg.delay_min_lag,
            max_lag=cfg.delay_max_lag,
            batch_size=env.num_envs,
            device=env.device,
            per_env=True,
            update_period=cfg.delay_update_period,
            per_env_phase=False,
        )

    def apply_actions(self) -> None:
        self._source_delay.append(self._processed_actions)
        target = self._source_delay.compute()
        encoder_bias = self._entity.data.encoder_bias[:, self._target_ids]
        self._entity.set_joint_position_target(
            target + encoder_bias, joint_ids=self._target_ids
        )

    def reset(self, env_ids=None) -> None:
        super().reset(env_ids)
        self._source_delay.reset(batch_ids=env_ids)
        zeros = torch.zeros_like(self._processed_actions)
        if not self._source_delay.is_initialized:
            self._source_delay.append(zeros)
            return
        if env_ids is None:
            ids = torch.arange(self.num_envs, device=self.device)
        elif isinstance(env_ids, slice):
            ids = torch.arange(self.num_envs, device=self.device)[env_ids]
        else:
            ids = env_ids
        self._source_delay.backfill(zeros, ids)


@dataclass(kw_only=True)
class EpisodeDelayedJointPositionActionCfg(JointPositionActionCfg):
    delay_min_lag: int = 1
    delay_max_lag: int = 3
    delay_update_period: int = 2**30

    def build(self, env) -> EpisodeDelayedJointPositionAction:
        return EpisodeDelayedJointPositionAction(self, env)


class DelayedJointPositionAction(OrderedTargets, JointPositionAction):
    """Apply delayed targets while retaining raw action history for rewards.

    「延时」是源实现的**每策略步重新采样**口径：每个环境每步抽一个
    ``[0, decimation)`` 的整数，在该点之前继续下发上一目标、之后下发新目标。
    ``delay=False`` 时退化为与 :class:`JointPositionAction` 逐位等价。
    """

    cfg: "DelayedJointPositionActionCfg"  # pyright: ignore[reportIncompatibleVariableOverride]

    def __init__(self, cfg: "DelayedJointPositionActionCfg", env) -> None:
        super().__init__(cfg, env)
        self._decimation = int(env.cfg.decimation)
        self._delay_steps = torch.zeros(self.num_envs, device=self.device, dtype=torch.long)
        self._substep = 0
        self._previous_processed = torch.zeros_like(self._processed_actions)
        self._delay_enabled = bool(cfg.delay)
        self._delay_mode = cfg.delay_mode
        if self._delay_mode not in ("switch", "buffer"):
            raise ValueError(f"Unknown delay mode: {self._delay_mode!r}")
        if cfg.delay_steps_range is None:
            self._delay_range = (0, max(0, self._decimation - 1))
        else:
            self._delay_range = cfg.delay_steps_range
        low, high = self._delay_range
        if not 0 <= low <= high < self._decimation:
            raise ValueError(
                "delay_steps_range must satisfy 0 <= low <= high < env decimation"
            )
        self._action_buffer = torch.zeros(
            self.num_envs, self.action_dim, high + 1, device=self.device
        )
        self._default_processed = self._entity.data.default_joint_pos[
            :, self._target_ids
        ].clone()
        self._previous_processed[:] = self._default_processed
        self._action_buffer[:] = self._default_processed.unsqueeze(-1)
        self._observation_latency = bool(cfg.observation_latency)
        self._obs_motor_latency_steps = torch.zeros(
            self.num_envs, dtype=torch.long, device=self.device
        )
        self._obs_imu_latency_steps = torch.zeros(
            self.num_envs, dtype=torch.long, device=self.device
        )
        motor_low, motor_high = cfg.observation_motor_latency_range
        imu_low, imu_high = cfg.observation_imu_latency_range
        if not (0 <= motor_low <= motor_high and 0 <= imu_low <= imu_high):
            raise ValueError("Observation latency ranges must satisfy 0 <= low <= high")
        if cfg.observation_imu_orientation not in ("euler", "gravity"):
            raise ValueError("observation_imu_orientation must be 'euler' or 'gravity'")
        self._obs_motor_latency_buffer = torch.zeros(
            self.num_envs, self.action_dim * 2, motor_high + 1, device=self.device
        )
        self._obs_imu_latency_buffer = torch.zeros(
            self.num_envs, 6, imu_high + 1, device=self.device
        )
        self._obs_motor_latency_range = (motor_low, motor_high)
        self._obs_imu_latency_range = (imu_low, imu_high)
        # Observation terms can retrieve this state through the action manager;
        # keeping it on the term avoids a second global per-environment manager.

    def process_actions(self, actions: torch.Tensor) -> None:
        super().process_actions(actions)
        if self._delay_enabled and self._delay_mode == "switch":
            self._delay_steps = torch.randint(
                self._delay_range[0],
                self._delay_range[1] + 1,
                (self.num_envs,),
                device=self.device,
            )
        elif not self._delay_enabled:
            self._delay_steps.zero_()
        self._substep = 0

    def apply_actions(self) -> None:
        if self._delay_enabled and self._delay_mode == "buffer":
            self._action_buffer[:, :, 1:] = self._action_buffer[:, :, :-1].clone()
            self._action_buffer[:, :, 0] = self._processed_actions
            selected = self._action_buffer[
                torch.arange(self.num_envs, device=self.device),
                :,
                self._delay_steps,
            ]
        elif self._delay_enabled:
            use_current = self._substep >= self._delay_steps
            selected = torch.where(
                use_current.unsqueeze(-1), self._processed_actions, self._previous_processed
            )
        else:
            selected = self._processed_actions
        encoder_bias = self._entity.data.encoder_bias[:, self._target_ids]
        target = selected - encoder_bias
        self._entity.set_joint_position_target(target, joint_ids=self._target_ids)
        self._previous_processed[:] = selected
        self._substep = (self._substep + 1) % self._decimation

    def post_physics_step(self) -> None:
        """Record source-style motor/IMU samples after one physics substep."""
        if not self._observation_latency:
            return
        q = self._entity.data.joint_pos[:, self._target_ids] - self._default_processed
        dq = self._entity.data.joint_vel[:, self._target_ids] * 0.05
        self._obs_motor_latency_buffer[:, :, 1:] = self._obs_motor_latency_buffer[
            :, :, :-1
        ].clone()
        self._obs_motor_latency_buffer[:, :, 0] = torch.cat((q, dq), dim=-1)
        if self.cfg.observation_imu_orientation == "gravity":
            orientation = self._entity.data.projected_gravity_b
        else:
            roll, pitch, yaw = euler_xyz_from_quat(self._entity.data.root_link_quat_w)
            orientation = torch.stack((roll, pitch, yaw), dim=-1)
        imu = torch.cat((self._entity.data.root_link_ang_vel_b * 0.25, orientation), dim=-1)
        self._obs_imu_latency_buffer[:, :, 1:] = self._obs_imu_latency_buffer[
            :, :, :-1
        ].clone()
        self._obs_imu_latency_buffer[:, :, 0] = imu

    def get_delayed_motor_observation(self) -> tuple[torch.Tensor, torch.Tensor] | None:
        """Return delayed ``(q_rel, dq_scaled)`` or ``None`` when disabled."""
        if not self._observation_latency:
            return None
        ids = torch.arange(self.num_envs, device=self.device)
        values = self._obs_motor_latency_buffer[ids, :, self._obs_motor_latency_steps]
        return values[:, : self.action_dim], values[:, self.action_dim :]

    def get_delayed_imu_observation(self) -> torch.Tensor | None:
        """Return delayed ``ang_vel*0.25 || orientation`` or ``None``."""
        if not self._observation_latency:
            return None
        ids = torch.arange(self.num_envs, device=self.device)
        return self._obs_imu_latency_buffer[ids, :, self._obs_imu_latency_steps]

    def reset(self, env_ids: torch.Tensor | slice | None = None) -> None:
        super().reset(env_ids)
        target_ids = slice(None) if env_ids is None else env_ids
        self._previous_processed[target_ids] = self._default_processed[target_ids]
        if self._delay_enabled and self._delay_mode == "buffer":
            count = self._delay_steps[target_ids].shape[0]
            self._delay_steps[target_ids] = torch.randint(
                self._delay_range[0],
                self._delay_range[1] + 1,
                (count,),
                device=self.device,
            )
        else:
            self._delay_steps[target_ids] = 0
        self._action_buffer[target_ids] = self._default_processed[target_ids].unsqueeze(-1)
        if self._observation_latency:
            self._obs_motor_latency_buffer[target_ids] = 0.0
            self._obs_imu_latency_buffer[target_ids] = 0.0
            count = self._obs_motor_latency_steps[target_ids].shape[0]
            motor_low, motor_high = self._obs_motor_latency_range
            imu_low, imu_high = self._obs_imu_latency_range
            self._obs_motor_latency_steps[target_ids] = torch.randint(
                motor_low, motor_high + 1, (count,), device=self.device
            )
            self._obs_imu_latency_steps[target_ids] = torch.randint(
                imu_low, imu_high + 1, (count,), device=self.device
            )


@dataclass(kw_only=True)
class DelayedJointPositionActionCfg(JointPositionActionCfg):
    """Joint-position action with a random substep switch point.

    ``delay=False`` makes this a drop-in equivalent of
    :class:`JointPositionActionCfg` for tasks that do not use the source latency
    model.
    """

    delay: bool = True
    delay_mode: Literal["switch", "buffer"] = "switch"
    delay_steps_range: tuple[int, int] | None = None
    observation_latency: bool = False
    # The source backflip observer uses projected gravity; the other special
    # action observers use Euler angles in their six-dimensional IMU block.
    observation_imu_orientation: Literal["euler", "gravity"] = "euler"
    observation_motor_latency_range: tuple[int, int] = (1, 3)
    observation_imu_latency_range: tuple[int, int] = (1, 3)

    def build(self, env) -> DelayedJointPositionAction:
        return DelayedJointPositionAction(self, env)
