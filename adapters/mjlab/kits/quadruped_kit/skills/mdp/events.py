"""族级技能的初始/扰动事件函数。

来源：`go2_skills/trot/mdp/events.py`（与 `.../jump/mdp/events.py` 逐字相同；
`go2_skills/shared/events.py` 是本文件 + 一条 go2 专用的 DreamWaQ 标签事件，
后者留在 go2 包内 —— 它不是族级技能的一部分）。本文件不含机型常量：
`entity_name="robot"` 是场景实体名（族级技能统一约定），几何/关节名一律由调用方
经绑定传入。

`reset_joints_by_scale_with_velocity` 与 `torque_multiplier`（末两段）来源：
`local_tasks/robots/unitree/go2/mdp/events.py` 的同名函数（速度跟踪的算法变体用）。
两者参数签名逐项保留（`scale_range` / `velocity_range` / `asset_cfg`），
故可与源配方的参数表直接对接；`asset_cfg` 的关节/执行器名由绑定派生。
"""

from typing import Any

import torch
from mjlab.entity import Entity
from mjlab.envs.mdp.events import resolve_env_ids
from mjlab.managers.event_manager import requires_model_fields
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.utils.lab_api.math import sample_uniform

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def overwrite_root_velocity(
    env,
    env_ids,
    max_push_vel_xy: float,
    max_push_ang_vel: float,
) -> None:
    """Match the source push: overwrite XY and all angular velocity components."""
    ids = resolve_env_ids(env, env_ids)
    robot: Entity = env.scene["robot"]
    velocity = robot.data.root_link_vel_w[ids].clone()
    velocity[:, :2].uniform_(-max_push_vel_xy, max_push_vel_xy)
    velocity[:, 3:].uniform_(-max_push_ang_vel, max_push_ang_vel)
    robot.write_root_link_velocity_to_sim(velocity, env_ids=ids)


def add_root_velocity(
    env,
    env_ids,
    max_push_vel_xy: float,
    max_push_ang_vel: float,
) -> None:
    """Match ``go2_leggedstand``: add a random world-frame velocity impulse."""
    ids = resolve_env_ids(env, env_ids)
    robot: Entity = env.scene["robot"]
    velocity = robot.data.root_link_vel_w[ids].clone()
    velocity[:, :2] += torch.empty_like(velocity[:, :2]).uniform_(
        -max_push_vel_xy, max_push_vel_xy
    )
    velocity[:, 3:] += torch.empty_like(velocity[:, 3:]).uniform_(
        -max_push_ang_vel, max_push_ang_vel
    )
    robot.write_root_link_velocity_to_sim(velocity, env_ids=ids)


@requires_model_fields("geom_friction")
def source_friction_buckets(
    env,
    env_ids,
    low: float,
    high: float,
    num_buckets: int,
    entity_name: str = "robot",
) -> None:
    """Match the source's 256-value friction bucket assignment."""
    ids = resolve_env_ids(env, env_ids)
    robot: Entity = env.scene[entity_name]
    buckets = torch.empty(num_buckets, device=env.device).uniform_(low, high)
    bucket_ids = torch.randint(num_buckets, (len(ids),), device=env.device)
    values = buckets[bucket_ids]
    geom_ids = robot.indexing.geom_ids
    env.sim.model.geom_friction[ids[:, None], geom_ids, 0] = values[:, None]


def reset_joints_by_scale(
    env,
    env_ids,
    scale_range: tuple[float, float],
    entity_name: str = "robot",
) -> None:
    """Reset positions to a uniform multiple of each source default angle."""
    ids = resolve_env_ids(env, env_ids)
    robot: Entity = env.scene[entity_name]
    default_pos = robot.data.default_joint_pos
    default_vel = robot.data.default_joint_vel
    limits = robot.data.soft_joint_pos_limits
    assert default_pos is not None
    assert default_vel is not None
    assert limits is not None
    scale = torch.empty_like(default_pos[ids]).uniform_(*scale_range)
    position = (default_pos[ids] * scale).clamp(limits[ids, :, 0], limits[ids, :, 1])
    robot.write_joint_state_to_sim(
        position, torch.zeros_like(default_vel[ids]), env_ids=ids
    )


def sample_restitution_label(
    env,
    env_ids,
    low: float,
    high: float,
    attribute_name: str = "_rear_stand_restitution",
) -> None:
    """Sample the source restitution label where MuJoCo has no direct coefficient."""
    ids = resolve_env_ids(env, env_ids)
    labels = getattr(env, attribute_name, None)
    if labels is None:
        labels = torch.zeros((env.num_envs, 1), device=env.device)
        setattr(env, attribute_name, labels)
    labels[ids].uniform_(low, high)


def _scale_joint_field_and_store_label(
    env,
    env_ids,
    low: float,
    high: float,
    field_name: str,
    attribute_name: str,
    entity_name: str,
) -> None:
    ids = resolve_env_ids(env, env_ids)
    robot: Entity = env.scene[entity_name]
    values = torch.empty((len(ids), 1), device=env.device).uniform_(low, high)
    dof_ids = robot.indexing.joint_v_adr
    field = getattr(env.sim.model, field_name)
    field[ids[:, None], dof_ids] *= values
    labels = torch.zeros((env.num_envs, 1), device=env.device)
    setattr(env, attribute_name, labels)
    labels[ids] = values


@requires_model_fields("dof_frictionloss")
def scale_joint_friction_and_store_label(
    env,
    env_ids,
    low: float,
    high: float,
    entity_name: str = "robot",
) -> None:
    _scale_joint_field_and_store_label(
        env,
        env_ids,
        low,
        high,
        "dof_frictionloss",
        "_handstand_joint_friction",
        entity_name,
    )


@requires_model_fields("dof_damping")
def scale_joint_damping_and_store_label(
    env,
    env_ids,
    low: float,
    high: float,
    entity_name: str = "robot",
) -> None:
    _scale_joint_field_and_store_label(
        env,
        env_ids,
        low,
        high,
        "dof_damping",
        "_handstand_joint_damping",
        entity_name,
    )


def reset_joints_by_scale_with_velocity(
    env,
    env_ids: torch.Tensor | None,
    scale_range: tuple[float, float],
    velocity_range: tuple[float, float],
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> None:
    """Reset joints as ``default_q * U(scale_range)`` and jitter the velocity.

    与 `reset_joints_by_scale`（同一模块，速度归零）是**两条源口径**：算法变体的
    源环境用**乘性**关节初值 + 速度抖动区间，而不是 mjlab 的加性
    `reset_joints_by_offset`。保持独立函数以免改动通用 reset 语义。
    结果按软限位夹紧（与 mjlab 常规 reset 事件同口径）。
    """
    env_ids = resolve_env_ids(env, env_ids)
    asset: Entity = env.scene[asset_cfg.name]
    default_joint_pos = asset.data.default_joint_pos
    default_joint_vel = asset.data.default_joint_vel
    soft_joint_pos_limits = asset.data.soft_joint_pos_limits
    assert default_joint_pos is not None
    assert default_joint_vel is not None
    assert soft_joint_pos_limits is not None

    joint_ids = asset_cfg.joint_ids
    if isinstance(joint_ids, list):
        joint_ids = torch.tensor(joint_ids, device=env.device)
    joint_pos = default_joint_pos[env_ids][:, joint_ids].clone()
    scales = sample_uniform(*scale_range, joint_pos.shape, env.device)
    joint_pos = joint_pos * scales
    limits = soft_joint_pos_limits[env_ids][:, joint_ids]
    joint_pos = joint_pos.clamp_(limits[..., 0], limits[..., 1])

    joint_vel = default_joint_vel[env_ids][:, joint_ids].clone()
    joint_vel += sample_uniform(*velocity_range, joint_vel.shape, env.device)
    asset.write_joint_state_to_sim(
        joint_pos.reshape(len(env_ids), -1),
        joint_vel.reshape(len(env_ids), -1),
        env_ids=env_ids,
        joint_ids=joint_ids,
    )


def torque_multiplier(
    env,
    env_ids: torch.Tensor | None,
    torque_multiplier_range: tuple[float, float],
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> None:
    """Scale each position actuator's complete PD torque at startup.

    源（Isaac Gym）控制器在 PD 计算之后按环境乘一个力矩倍率；对 MuJoCo 原生位置
    执行器，这等价于把 actuator gain 与两个 bias 系数同乘一个**共享**采样值。
    它刻意在独立的 PD 增益事件之后运行，并把 PD 增益/力矩倍率两个标签留在 env 上
    （特权观测按源字段口径读它们）。全是族级机制：执行器集合来自 `asset_cfg`。
    """
    env_ids = resolve_env_ids(env, env_ids)
    asset: Entity = env.scene[asset_cfg.name]
    actuator_ids = asset_cfg.actuator_ids
    if isinstance(actuator_ids, list):
        actuators = [asset.actuators[i] for i in actuator_ids]
    elif isinstance(actuator_ids, slice):
        actuators = list(asset.actuators[actuator_ids])
    else:
        actuators = [asset.actuators[actuator_ids]]

    gainprm = env.sim.model.actuator_gainprm
    biasprm = env.sim.model.actuator_biasprm
    default_gainprm = env.sim.get_default_field("actuator_gainprm")
    default_biasprm = env.sim.get_default_field("actuator_biasprm")
    joint_count = asset.data.joint_pos.shape[-1]
    state: Any = env
    if not hasattr(state, "_source_pd_kp_multiplier"):
        state._source_pd_kp_multiplier = torch.ones(
            (env.num_envs, joint_count), device=env.device
        )
        state._source_pd_kd_multiplier = torch.ones_like(state._source_pd_kp_multiplier)
        state._source_torque_multiplier = torch.ones_like(state._source_pd_kp_multiplier)
    for actuator in actuators:
        ctrl_ids = actuator.global_ctrl_ids
        target_ids = actuator.target_ids
        n_targets = len(ctrl_ids)
        # Capture the independent PD samples before applying the complete-torque
        # multiplier.  Reading gainprm afterwards would conflate two distinct
        # source privileged-observation fields.
        state._source_pd_kp_multiplier[env_ids[:, None], target_ids] = gainprm[
            env_ids[:, None], ctrl_ids, 0
        ] / default_gainprm[ctrl_ids, 0].clamp_min(1.0e-6)
        state._source_pd_kd_multiplier[env_ids[:, None], target_ids] = -biasprm[
            env_ids[:, None], ctrl_ids, 2
        ] / (-default_biasprm[ctrl_ids, 2]).clamp_min(1.0e-6)
        multipliers = sample_uniform(
            torque_multiplier_range[0],
            torque_multiplier_range[1],
            (len(env_ids), n_targets),
            env.device,
        )
        state._source_torque_multiplier[env_ids[:, None], target_ids] = multipliers
        gainprm[env_ids[:, None], ctrl_ids, 0] *= multipliers
        biasprm[env_ids[:, None], ctrl_ids, 1] *= multipliers
        biasprm[env_ids[:, None], ctrl_ids, 2] *= multipliers
