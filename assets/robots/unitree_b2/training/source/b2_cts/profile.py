"""Unitree B2 的 CTS 变体数据（族级算法变体的数据面）。

## 这份数据从哪来

本仓**没有 b2 专属的 CTS 上游**（CTS 的上游是 `00_resources/LeggedGym-Ex` 的 go2
CTS/TS 族）。所以本表是**同一份算法配方**：逐项数值取自 `unitree_go2` 的 cts 档
（`go2/tasks/locomotion/variants_profile.py`），只改**机型相关**的两项：

1. `contact_order` —— 接触观测里的足序，取 b2 自己的腿序（`FR, FL, RR, RL`，与
   契约 `morphology.leg_ids` 同序；go2 也是这个序，但两台各自声明，不互相借）；
2. `base_height_target` —— 目标站姿高，取 b2 自己的站姿（`init_base_height` 0.54；
   go2 用的是 0.4）。

**别把"能训"当成"训得好"**：其余数值（步态/命令/DR/奖励权重与阈值）是 go2 配方的
原样搬运，b2 上没有标定过。本档案的产品意义是**复用证明** —— 族级实现 + 只换数据，
第二台四足就能训 CTS。要当正式技能用，需按 b2 标定一轮（登记在
`registry/porting_references.json` 的 `b2-cts` 条目里）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.velocity.profile import (
    VariantRunnerProfile,
    VariantSpec,
)

#: b2 的接触观测足序（本机型腿序；源配方同序，但各家自己声明）。
CONTACT_ORDER = ("FR", "FL", "RR", "RL")

#: 目标站姿高（米）：取 b2 自己的站姿（`b2_velocity.binding.B2_VELOCITY.init_base_height`）。
BASE_HEIGHT_TARGET = 0.54

CTS_SPEC = VariantSpec(
    family="cts",
    amp=False,
    # **按 body 匹配**（不是 geom）：b2 的 MJCF 只给足端几何具名，腿杆/躯干的碰撞几何
    # 无名（由 `CollisionCfg` 在实体构建期重建）⇒ 几何名派生在这里不成立。族级机制
    # 本就为这类资产留了 body 口径（`ensure_supervision_bodies`，语义相同、只是匹配面
    # 从几何名换成 body 名），故这是**数据选择**、不是机型特判。
    contact_match="body",
    reset_scale_range=(0.9, 1.1),
    reset_pose_range={"x": (-1.0, 1.0), "y": (-1.0, 1.0), "z": (0.0, 0.0), "yaw": (0.0, 0.0)},
    reset_velocity_range={
        "x": (-0.5, 0.5),
        "y": (-0.5, 0.5),
        "z": (-0.5, 0.5),
        "roll": (-0.5, 0.5),
        "pitch": (-0.5, 0.5),
        "yaw": (-0.5, 0.5),
    },
    terrain_border_width=70.0,
    clip_rewards_to_positive=False,
    hip_preload_by_leg={},
    encoder_bias_range=(-0.035, 0.035),
    geom_friction_range=(0.2, 1.0),
    com_extent=0.05,
    base_mass_range=(-1.0, 5.0),
    link_mass_range=(0.8, 1.2),
    pd_gain_range=(0.9, 1.1),
    torque_multiplier_range=(0.9, 1.1),
    push_interval_s=4.0,
    push_linear=0.4,
    push_angular=0.6,
    history_frame_count=6,
    contact_order=CONTACT_ORDER,
    dof_pos_noise=0.01,
    ang_vel_noise=0.2,
    track_sigma=0.25,
    tracking_linear_weight=1.5,
    tracking_angular_weight=0.75,
    orientation_weight=-0.2,
    angular_velocity_xy_weight=-0.05,
    linear_velocity_z_weight=-1.0,
    base_height_weight=-2.0,
    base_height_target=BASE_HEIGHT_TARGET,
    torque_weight=-1.0e-4,
    joint_acceleration_weight=-2.5e-7,
    action_smoothness_weight=-0.01,
    dof_pos_limits_weight=-2.0,
    action_rate_weight=-0.01,
    collision_weight=-1.0,
    collision_groups=("thigh", "shank", "trunk"),
    foot_clearance_weight=-0.5,
    foot_clearance_target=-0.20,
    stumble_weight=-0.5,
    air_time_weight=0.0,
    air_time_offset=0.5,
    hip_position_weight=None,
    rear_hip_limit_weight=None,
    rear_hip_limit_bound=0.4,
    command_resample_s=8.0,
    lin_vel_y_range=(-1.0, 1.0),
    yaw_range=(-1.0, 1.0),
    command_min_lin_norm=0.1,
    zero_command_prob=0.0,
    zero_xy_prob=0.0,
    drop_command_curriculum=False,
    broadphase="sap_segmented",
    nconmax=35,
)

#: runner 侧：超参同 go2 的 cts 档；算法/模型符号用**平台注册表的规范路径**
#: （`adapters/mjlab/algorithms/registry.json` 的 cts 插件）—— 不指任何机型包。
#: 档案同时声明 `algorithm_plugin: "cts"`，训练服务会在运行期把同一批符号再绑一次。
CTS_RUNNER = VariantRunnerProfile(
    experiment_name="b2_cts",
    learning_rate=1.0e-3,
    max_iterations=20_000,
    save_interval=500,
    seed=1,
    algorithm_class="adapters.mjlab.algorithms.cts.algorithms:CtsPPO",
    actor_class="adapters.mjlab.algorithms.cts.models:CtsActorModel",
    critic_class="adapters.mjlab.algorithms.cts.models:CtsCriticModel",
)
