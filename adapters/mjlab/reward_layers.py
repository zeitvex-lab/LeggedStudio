"""奖励四层分组注册表（T2.1，批次 2 / M3）。

四层分解是 legged_gym / walk-these-ways / extreme-parkour 的共识
（00_Survey 报告 1 §4）：Tracking / Regularization / Style / Contact。
total reward 上涨可能只是 penalty 在降——按层着色的分项曲线是 reward
hacking 可见性的唯一解。

本模块是纯数据表（无 torch/mjlab 依赖），控制面与适配器都可安全导入；
覆盖共享库（shared_rewards）与已知包配方（Lite3/M20/wtw/go2w 等）的
常见项名别名。未知项归 "Other"，由前端落到独立分组，不冒充分类。
"""

from __future__ import annotations

LAYERS = ("Tracking", "Regularization", "Style", "Contact", "Other")

REWARD_TERM_LAYERS: dict[str, str] = {
    # ---- Tracking（速度/姿态跟踪，正权重，指数核） ----
    "tracking_lin_vel": "Tracking",
    "tracking_ang_vel": "Tracking",
    "track_lin_vel": "Tracking",
    "track_ang_vel": "Tracking",
    "tracking_lin_vel_phase": "Tracking",
    "tracking_ang_vel_phase": "Tracking",
    "lin_vel_yaw": "Tracking",
    "tracking_contacts_shaped_force": "Tracking",
    # ---- Regularization（负权重正则） ----
    "action_rate": "Regularization",
    "action_rate_l2": "Regularization",
    "action_smoothness_l2": "Regularization",
    "torques": "Regularization",
    "dof_torques": "Regularization",
    "energy": "Regularization",
    "power": "Regularization",
    "dof_acc": "Regularization",
    "joint_acc_l2": "Regularization",
    "joint_pos_limits": "Regularization",
    "dof_pos_limits": "Regularization",
    "ang_vel_xy": "Regularization",
    "lin_vel_z": "Regularization",
    "collision": "Regularization",
    "termination": "Regularization",
    "limit": "Regularization",
    # ---- Style（姿态/形态类） ----
    "orientation": "Style",
    "upright": "Style",
    "base_height": "Style",
    "alive": "Style",
    "foot_flat": "Style",
    "feet_distance_ours": "Style",
    "foot_clearance_swing": "Style",
    "hip_spread": "Style",
    "torso_upright": "Style",
    # ---- Contact（接触/步态类） ----
    "feet_air_time": "Contact",
    "feet_air_time_cmd_gated": "Contact",
    "contact_forces": "Contact",
    "feet_stumble": "Contact",
    "foot_landing_vel": "Contact",
    "no_fly": "Contact",
    "foot_slip": "Contact",
    "undesired_contacts": "Contact",
    "feet_contact_number": "Contact",
    "feet_distance": "Contact",
    "contact_soles": "Contact",
}


def get_reward_layer(term_name: str) -> str:
    """奖励项 → 层名；未知项归 Other（前端独立分组，不冒充分类）。"""

    return REWARD_TERM_LAYERS.get(str(term_name), "Other")
