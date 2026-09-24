"""族级技能的 RL 运行器构造 + 奖励原语。

来源：`go2_skills/shared/rl.py` + `go2_skills/upstream/rl.py`（逐字上移）。
机组常量改为声明驱动的解析：

* `joint_ids(env)` —— 关节序取自动作项（见 `contacts.py`），不再写死 12 个 go2 关节名；
* `contact_without_command` 里的"四足全接触"由**足端传感器的槽数**决定
  （四足族 = 4），换机型不必改技能层。

`RslRlPpoWithSymmetryAlgorithmCfg` 是上游 runner 的对称性扩展（`symmetry_cfg` 字段），
trot/jump 的 runner 都走它；`experiment_name` 由机型侧的 profile 传入。
"""

from dataclasses import dataclass
from typing import Any

import torch
from mjlab.entity import Entity
from mjlab.managers import RewardTermCfg
from mjlab.rl import RslRlModelCfg, RslRlOnPolicyRunnerCfg, RslRlPpoAlgorithmCfg

from .contacts import joint_ids, source_contact


@dataclass
class RslRlPpoWithSymmetryAlgorithmCfg(RslRlPpoAlgorithmCfg):
    """Expose the symmetry extension supported by the installed RSL-RL PPO."""

    symmetry_cfg: dict[str, Any] | None = None


def make_ppo_runner_cfg(
    experiment_name: str,
    *,
    max_iterations: int = 10_000,
    entropy_coef: float = 0.01,
    save_interval: int = 100,
    symmetry_cfg: dict[str, Any] | None = None,
) -> RslRlOnPolicyRunnerCfg:
    """Create the common PPO setup used by the upstream task library locomotion tasks."""
    return RslRlOnPolicyRunnerCfg(
        actor=RslRlModelCfg(
            hidden_dims=(512, 256, 128),
            activation="elu",
            obs_normalization=True,
            distribution_cfg={
                "class_name": "GaussianDistribution",
                "init_std": 1.0,
                "std_type": "scalar",
            },
        ),
        critic=RslRlModelCfg(
            hidden_dims=(512, 256, 128),
            activation="elu",
            obs_normalization=True,
        ),
        algorithm=RslRlPpoWithSymmetryAlgorithmCfg(
            value_loss_coef=1.0,
            use_clipped_value_loss=True,
            clip_param=0.2,
            entropy_coef=entropy_coef,
            num_learning_epochs=5,
            num_mini_batches=4,
            learning_rate=1.0e-3,
            schedule="adaptive",
            gamma=0.99,
            lam=0.95,
            desired_kl=0.01,
            max_grad_norm=1.0,
            symmetry_cfg=symmetry_cfg,
        ),
        experiment_name=experiment_name,
        save_interval=save_interval,
        num_steps_per_env=24,
        max_iterations=max_iterations,
    )


def command(env, command_name: str) -> torch.Tensor:
    value = env.command_manager.get_command(command_name)
    assert value is not None
    return value


def moving(env, command_name: str) -> torch.Tensor:
    return torch.linalg.vector_norm(command(env, command_name)[:, :3], dim=1) > 0.1


def lin_vel_z_squared(env) -> torch.Tensor:
    return torch.square(env.scene["robot"].data.root_link_lin_vel_b[:, 2])


def ang_vel_xy_squared(env) -> torch.Tensor:
    return torch.square(env.scene["robot"].data.root_link_ang_vel_b[:, :2]).sum(dim=1)


def orientation_squared(env) -> torch.Tensor:
    return torch.square(env.scene["robot"].data.projected_gravity_b[:, :2]).sum(dim=1)


def torques_squared(env) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    return torch.square(robot.data.qfrc_actuator[:, joint_ids(env)]).sum(dim=1)


def absolute_torques(env) -> torch.Tensor:
    return torch.abs(env.scene["robot"].data.qfrc_actuator[:, joint_ids(env)]).sum(dim=1)


class DofAcceleration:
    def __init__(self, cfg: RewardTermCfg, env) -> None:
        del cfg
        self._last_velocity = torch.zeros(
            env.num_envs, len(joint_ids(env)), device=env.device
        )

    def __call__(self, env) -> torch.Tensor:
        robot: Entity = env.scene["robot"]
        velocity = robot.data.joint_vel[:, joint_ids(env)]
        value = torch.square((self._last_velocity - velocity) / env.step_dt).sum(dim=1)
        self._last_velocity.copy_(velocity)
        return value

    def reset(self, env_ids=None) -> None:
        self._last_velocity[env_ids] = 0.0


def collision(env, sensor_name: str) -> torch.Tensor:
    force = env.scene[sensor_name].data.force
    assert force is not None
    return (torch.linalg.vector_norm(force, dim=-1) > 0.1).float().sum(dim=1)


def action_rate(env) -> torch.Tensor:
    return torch.square(env.action_manager.prev_action - env.action_manager.action).sum(1)


def stand_still(env, command_name: str) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = joint_ids(env)
    return torch.abs(
        robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids]
    ).sum(dim=1) * ~moving(env, command_name)


def default_pos(env) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = joint_ids(env)
    return torch.abs(
        robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids]
    ).sum(dim=1)


def contact_without_command(env, sensor_name: str, command_name: str) -> torch.Tensor:
    sensor = env.scene[sensor_name]
    force = sensor.data.force
    assert force is not None
    all_feet = force.shape[1]
    return (source_contact(sensor, 0.1).sum(dim=1) == all_feet) * ~moving(
        env, command_name
    )


def terminal_cost(env) -> torch.Tensor:
    return env.termination_manager.terminated.float() / env.step_dt
