"""Periodic Reward Framework（Walk-These-Ways 风格）的族级 MDP 项。

来源：`assets/robots/unitree_go2/training/source/local_tasks/robots/unitree/go2/tasks/
locomotion/wtw_mdp.py`（LeggedGym-Ex ``go2_wtw.py`` 的移植，BSD-3-Clause）——除下列
去机型化改动外逐段一致：

* **状态初始化**：源实现把四个行为参数的初值写死在 `_state()` 里（0.45 / 0.08 /
  0.27 / 0.0，恰为各自采样区间中点）。族级把这四个初值与采样区间、θ 池都交给
  startup 事件 `wtw_state_init`（参数来自机型 profile）——技能层零任务数值字面量；
  状态可在此事件应用前被任何 term **惰性**建立（mjlab 在 manager 构造期就会调
  term 一次，见 `_state()`），两次建立同值。
* **腿数**：θ/时钟的宽度与足端槽位由 `legs`（绑定派生）给出，不再写死 4。
* **髋关节**：`hip_pos` 按**族角色** `hip_abduction` 选关节（源实现按名字含 "hip"
  扫实体关节）；对同构机型逐关节同集合、且求和与顺序无关。

机制不变：全局相位 ``phi`` 每控制步推进；每腿 ``theta`` 偏移选中步态（trot / pronk /
pace / bound，reset 时重采样）；每腿的摆动/支撑预期是 ``(phi + theta) % 1`` 上的阶跃
指示 —— 摆动期罚足速、支撑期罚接触力。所有状态挂在 env 实例上（``_wtw_state``），
项本身保持无状态函数（mjlab 的 term 契约）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

import torch

from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg

from ..family import DEFAULT_FAMILY_ID, joint_indices_by_role
from ..mdp.contacts import joint_ids, joint_names

if TYPE_CHECKING:
    from mjlab.envs import ManagerBasedRlEnv

#: 状态在 env 实例上的属性名（每环境一份，惰性建立）。
STATE_ATTR = "_wtw_state"
#: 状态配方（初值 / 采样区间 / θ 池 / 腿数）的**唯一声明处**：startup 事件名。
#: 见 `_state()` 的时序说明。
STATE_INIT_EVENT = "wtw_state_init"


@dataclass(frozen=True)
class ContactSensorRef:
    """对场景接触传感器的引用：名字 + 传感器数据的列（腿槽位）。

    列的语义由传感器装配决定（足端传感器按契约腿序的足端几何装配），故技能层
    用槽位下标引用某条腿的力/接触，不需要知道任何几何名。
    """

    name: str
    body_ids: tuple[int, ...] | None = None


def _cols(sensor_cfg: ContactSensorRef):
    return slice(None) if sensor_cfg.body_ids is None else sensor_cfg.body_ids


def _legs(state: dict) -> int:
    return int(state["theta"].shape[1])


def _state(env: ManagerBasedRlEnv) -> dict:
    """取（必要时惰性建立）WTW 状态。

    **为什么要惰性**：mjlab 的观测/奖励 manager 在**构造期**就调用一次各 term
    （推断宽度/初始化形状），而 startup 事件要到 `load_managers` 收尾才应用 ——
    源实现同样依赖"第一次访问时建状态"的时序。配方数据的唯一声明处是 startup
    事件 `wtw_state_init` 的 params（本函数按名读它）—— 任何一个 term 先跑都能用
    同一份数据把状态建起来，不依赖 manager 的构造顺序。
    """
    state = getattr(env, STATE_ATTR, None)
    if state is not None:
        return state
    events = getattr(env.cfg, "events", None) or {}
    term = events.get(STATE_INIT_EVENT)
    if term is None:
        raise RuntimeError(
            f"WTW 状态配方缺失：环境配置里没有 startup 事件 {STATE_INIT_EVENT!r}"
            "（`wtw_mdp.init_behavior_state`，参数来自 profile）"
        )
    state = _new_state(env, **term.params)
    setattr(env, STATE_ATTR, state)
    return state


def _new_state(
    env: ManagerBasedRlEnv,
    *,
    legs: int,
    theta_pool: tuple[tuple[float, ...], ...],
    initial: Mapping[str, float],
    ranges: Mapping[str, tuple[float, float]],
    num_gaits: int = 1,
) -> dict:
    """按配方建立全新状态（相位 / θ / 行为参数 / 采样数据）。"""
    return {
        "phi": torch.zeros(env.num_envs, 1, device=env.device),
        "gait_time": torch.zeros(env.num_envs, 1, device=env.device),
        "theta": torch.zeros(env.num_envs, int(legs), device=env.device),
        "clock": torch.zeros(env.num_envs, 2 * int(legs), device=env.device),
        "gait_period": torch.full(
            (env.num_envs, 1), float(initial["gait_period"]), device=env.device
        ),
        "foot_clearance_target": torch.full(
            (env.num_envs, 1), float(initial["foot_clearance"]), device=env.device
        ),
        "base_height_target": torch.full(
            (env.num_envs, 1), float(initial["base_height"]), device=env.device
        ),
        "pitch_target": torch.full(
            (env.num_envs, 1), float(initial["pitch"]), device=env.device
        ),
        "num_gaits": int(num_gaits),
        "theta_pool": tuple(tuple(float(x) for x in row) for row in theta_pool),
        "ranges": {
            str(key): tuple(float(x) for x in value) for key, value in ranges.items()
        },
    }


def init_behavior_state(
    env: ManagerBasedRlEnv,
    env_ids=None,
    *,
    legs: int,
    theta_pool: tuple[tuple[float, ...], ...],
    initial: Mapping[str, float],
    ranges: Mapping[str, tuple[float, float]],
    num_gaits: int = 1,
) -> None:
    """startup 事件：按 profile 配方建立 WTW 状态（与 `_state()` 的惰性建立同值）。

    `initial` 是四个行为参数的初值（机型 profile 给；源配方是 `_state()` 里写死的
    0.45 / 0.08 / 0.27 / 0.0）；`theta_pool` / `ranges` / `num_gaits` 是 resample 用的
    **采样数据**（随状态持有，reset 事件据此重采样）—— 状态是这份配方数据的唯一入口。
    """
    del env_ids
    setattr(
        env,
        STATE_ATTR,
        _new_state(
            env,
            legs=legs,
            theta_pool=theta_pool,
            initial=initial,
            ranges=ranges,
            num_gaits=num_gaits,
        ),
    )


def resample_behavior_params(env: ManagerBasedRlEnv, env_ids) -> None:
    """reset 事件：重采样 theta（步态模式）与行为参数（采样数据来自状态）。"""
    state = _state(env)
    theta_pool = state["theta_pool"]
    legs = _legs(state)
    if len(theta_pool) != legs:
        raise ValueError(
            f"theta 池有 {len(theta_pool)} 行，但状态有 {legs} 条腿（宽度不一致）"
        )
    num_gaits = max(1, min(int(state["num_gaits"]), len(theta_pool[0])))
    idx = torch.randint(0, num_gaits, (len(env_ids),))
    for leg_idx in range(legs):
        values = torch.tensor(
            [theta_pool[leg_idx][k] for k in idx.tolist()], device=env.device
        )
        state["theta"][env_ids, leg_idx] = values
    ranges = state["ranges"]
    state["gait_period"][env_ids] = torch.empty(
        len(env_ids), 1, device=env.device
    ).uniform_(*ranges["gait_period"])
    state["foot_clearance_target"][env_ids] = torch.empty(
        len(env_ids), 1, device=env.device
    ).uniform_(*ranges["foot_clearance"])
    state["base_height_target"][env_ids] = torch.empty(
        len(env_ids), 1, device=env.device
    ).uniform_(*ranges["base_height"])
    state["pitch_target"][env_ids] = torch.empty(
        len(env_ids), 1, device=env.device
    ).uniform_(*ranges["pitch"])
    # pronk 步态识别（全零 theta 行）：源配方在 pronk 下把相位计时清零。
    pronk = (state["theta"][env_ids] == 0.0).all(dim=1)
    if pronk.any():
        state["gait_time"][env_ids[pronk]] = 0.0


def advance_phase(env: ManagerBasedRlEnv, dt: float) -> None:
    """推进步态相位（奖励计算之后调用一次；观测项是唯一调用者）。"""
    state = _state(env)
    state["gait_time"] += dt
    over = state["gait_time"] >= (state["gait_period"] - dt / 2)
    state["gait_time"][over] = 0.0
    state["phi"] = state["gait_time"] / state["gait_period"]
    _calc_clock(env)


def _calc_clock(env: ManagerBasedRlEnv) -> None:
    state = _state(env)
    legs = _legs(state)
    for leg_idx in range(legs):
        phase = state["phi"] + state["theta"][:, leg_idx].unsqueeze(1)
        state["clock"][:, leg_idx] = torch.sin(2 * torch.pi * phase).squeeze(-1)
        state["clock"][:, leg_idx + legs] = torch.cos(2 * torch.pi * phase).squeeze(-1)


##
# Observations
##


def clock_observation(env: ManagerBasedRlEnv, dt: float = 0.02) -> torch.Tensor:
    """2×腿数维 sin/cos 步态时钟（每腿 [sin, cos]）。

    推进相位是副作用：源实现在奖励计算之后、观测重算之前推进 phi，mjlab 的
    计算顺序（奖励 → 观测）与之一致。
    """
    advance_phase(env, dt)
    _calc_clock(env)
    return _state(env)["clock"].clone()


def behavior_params_observation(env: ManagerBasedRlEnv) -> torch.Tensor:
    """4 维行为参数：gait_period, base_height, foot_clearance, pitch。"""
    state = _state(env)
    return torch.cat(
        [
            state["gait_period"],
            state["base_height_target"],
            state["foot_clearance_target"],
            state["pitch_target"],
        ],
        dim=1,
    )


def theta_observation(env: ManagerBasedRlEnv) -> torch.Tensor:
    """腿数维的每腿步态偏移。"""
    return _state(env)["theta"].clone()


##
# Rewards
##


def _feet_state(
    env: ManagerBasedRlEnv, sensor_cfg: ContactSensorRef, asset_cfg: SceneEntityCfg
):
    asset: Entity = env.scene[asset_cfg.name]
    sensor = env.scene.sensors[sensor_cfg.name]
    force = sensor.data.force[:, _cols(sensor_cfg), :]
    feet_force_norm = torch.norm(force, dim=-1)
    feet_vel = asset.data.body_link_lin_vel_w[:, asset_cfg.body_ids, :]
    feet_vel_norm = torch.norm(feet_vel, dim=-1)
    return feet_force_norm, feet_vel_norm


def _uniped_periodic_gait(
    env: ManagerBasedRlEnv,
    state: dict,
    leg_idx: int,
    feet_force_norm: torch.Tensor,
    feet_vel_norm: torch.Tensor,
    a_swing: float,
    b_swing: float,
):
    phi = (state["phi"] + state["theta"][:, leg_idx].unsqueeze(1)) % 1.0 * 2 * torch.pi
    exp_c_frc = torch.zeros(env.num_envs, 1, device=env.device)
    exp_c_spd = torch.zeros(env.num_envs, 1, device=env.device)
    swing = (phi >= a_swing) & (phi < b_swing)
    stance = (phi >= b_swing) & (phi < 2 * torch.pi)
    exp_c_frc[swing] = -1.0
    exp_c_spd[swing] = 0.0
    exp_c_frc[stance] = 0.0
    exp_c_spd[stance] = -1.0
    quad = (
        exp_c_spd * feet_vel_norm[:, leg_idx].unsqueeze(1)
        + exp_c_frc * feet_force_norm[:, leg_idx].unsqueeze(1)
    )
    return quad, exp_c_spd, exp_c_frc


def quad_periodic_gait(
    env: ManagerBasedRlEnv,
    sensor_cfg: ContactSensorRef,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    a_swing: float = 0.0,
    b_swing: float = 0.5,
) -> torch.Tensor:
    """exp(sum_leg expected_C_spd * foot_speed + expected_C_frc * foot_force)."""
    state = _state(env)
    feet_force_norm, feet_vel_norm = _feet_state(env, sensor_cfg, asset_cfg)
    total = torch.zeros(env.num_envs, device=env.device)
    for leg_idx in range(feet_force_norm.shape[1]):
        quad, _, _ = _uniped_periodic_gait(
            env, state, leg_idx, feet_force_norm, feet_vel_norm, a_swing, b_swing
        )
        total = total + quad.flatten()
    return torch.exp(total)


def tracking_base_height(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    sigma: float = 0.01,
) -> torch.Tensor:
    state = _state(env)
    base_height = env.scene[asset_cfg.name].data.root_link_pos_w[:, 2]
    return torch.exp(
        -torch.square(base_height - state["base_height_target"].squeeze(1)) / sigma
    )


def tracking_orientation(
    env: ManagerBasedRlEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    sigma: float = 0.1,
) -> torch.Tensor:
    state = _state(env)
    gravity = env.scene[asset_cfg.name].data.projected_gravity_b
    roll_error = torch.square(gravity[:, 1])  # roll via gravity y
    pitch_error = torch.square(gravity[:, 0] - state["pitch_target"].squeeze(1) * -1.0)
    return torch.exp(-(roll_error + pitch_error) / sigma)


def tracking_foot_clearance(
    env: ManagerBasedRlEnv,
    sensor_cfg: ContactSensorRef,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    sigma: float = 0.01,
    foot_height_offset: float = 0.022,
) -> torch.Tensor:
    """摆动相位的足端高度跟踪（按水平速度加权）。"""
    del sensor_cfg
    state = _state(env)
    asset: Entity = env.scene[asset_cfg.name]
    foot_vel_xy = torch.norm(
        asset.data.body_link_lin_vel_w[:, asset_cfg.body_ids, :2], dim=-1
    )
    clearance_error = torch.sum(
        foot_vel_xy
        * torch.square(
            asset.data.body_link_pos_w[:, asset_cfg.body_ids, 2]
            - state["foot_clearance_target"]
            - foot_height_offset
        ),
        dim=-1,
    )
    return torch.exp(-clearance_error / sigma)


def hip_pos(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    """髋（`hip_abduction` 族角色）偏离默认姿的平方惩罚（族角色选择，非位置假设）。"""
    asset: Entity = env.scene[asset_cfg.name]
    hips = joint_indices_by_role(joint_names(env), "hip_abduction", DEFAULT_FAMILY_ID)
    if not hips:
        return torch.zeros(env.num_envs, device=env.device)
    ids = joint_ids(env)
    return torch.sum(
        torch.square(
            asset.data.joint_pos[:, ids][:, hips]
            - asset.data.default_joint_pos[:, ids][:, hips]
        ),
        dim=-1,
    )


##
# Standard penalties (mjlab envs.mdp lacks a few of these shapes).
##


def lin_vel_z_l2(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    asset: Entity = env.scene[asset_cfg.name]
    return torch.square(asset.data.root_link_lin_vel_b[:, 2])


def ang_vel_xy_l2(
    env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    asset: Entity = env.scene[asset_cfg.name]
    return torch.sum(torch.square(asset.data.root_link_ang_vel_b[:, :2]), dim=1)


def action_smoothness(env: ManagerBasedRlEnv) -> torch.Tensor:
    """Second-order action difference (a - 2a' + a'')."""
    prev = getattr(env, "_wtw_prev_action", None)
    prev2 = getattr(env, "_wtw_prev2_action", None)
    action = env.action_manager.action
    if prev is None or prev2 is None:
        env._wtw_prev2_action = action.clone()
        env._wtw_prev_action = action.clone()
        return torch.zeros(env.num_envs, device=env.device)
    smooth = torch.sum(torch.square(action - 2 * prev + prev2), dim=1)
    env._wtw_prev2_action.copy_(prev)
    env._wtw_prev_action.copy_(action)
    return smooth


def foot_landing_vel(
    env: ManagerBasedRlEnv,
    sensor_cfg: ContactSensorRef,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    vel_threshold: float = 0.0,
) -> torch.Tensor:
    """Penalize vertical foot velocity while about to land (low height, descending, no contact)."""
    asset: Entity = env.scene[asset_cfg.name]
    sensor = env.scene.sensors[sensor_cfg.name]
    force = sensor.data.force[:, _cols(sensor_cfg), :]
    in_contact = force.norm(dim=-1) > 1.0
    foot_vel_z = asset.data.body_link_lin_vel_w[:, asset_cfg.body_ids, 2]
    descending = foot_vel_z < vel_threshold
    return torch.sum(torch.square(foot_vel_z) * (~in_contact) * descending, dim=1)


def undesired_contacts(
    env: ManagerBasedRlEnv, threshold: float, sensor_cfg: ContactSensorRef
) -> torch.Tensor:
    """Penalize contact on non-foot bodies above a force threshold."""
    sensor = env.scene.sensors[sensor_cfg.name]
    force = sensor.data.force[:, _cols(sensor_cfg), :]
    return torch.sum(
        torch.max(
            torch.norm(force, dim=-1) - threshold,
            torch.tensor(0.0, device=env.device),
        ),
        dim=1,
    )
