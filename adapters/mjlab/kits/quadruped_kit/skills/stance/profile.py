"""站姿类技能（handstand / rear_stand）的源配方数据。

两个技能是同一族技能的**两个奖励档**：共享同一份内核（`observations` / `rewards` /
`events`）与同一套装配机制，差异集中在"奖励表选哪些项、命令口径、事件微调、
runner 是否开镜像损失、几何目标高"—— 全部收在本数据类里。

边界：**只放"换机型/换档位必须换"的数**；奖励权重表本身是**技能配方**，
留 `config.py` 就地可读（与 backflip / spring_jump 同一口径）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StanceProfile:
    """一个站姿技能档（= 一台机型的一个变体）。"""

    #: 变体：`"handstand"`（前腿站立/倒立）或 `"rear_stand"`（后腿站立）。
    variant: str
    display_name: str
    task_id: str
    experiment_name: str
    num_envs: int = 4096
    episode_length_s: float = 20.0
    physics_dt: float = 0.005
    decimation: int = 4
    action_scale: float = 0.25
    # --- 几何目标（换机型必须换） --------------------------------------------------
    #: 站立目标高度（米）：handstand 0.47 / rear_stand 0.52。
    base_height_target: float = 0.47
    #: 足端摆动周期（秒）与目标离地高（米）。
    cycle_time: float = 1.6
    target_foot_height: float = 0.06
    # --- 命令口径 -----------------------------------------------------------------
    command_resample_s: float = 5.0
    heading_command: bool = False
    rel_heading_envs: float = 0.0
    lin_vel_x: tuple[float, float] = (-0.4, 0.4)
    ang_vel_z: tuple[float, float] = (-0.4, 0.4)
    heading: tuple[float, float] | None = None
    # --- 事件微调（handstand 档专属：源实现先套 rear_stand 的表再覆盖这几项） ----------
    #: 推扰动（`add_root_velocity`）的上限；`None` = 用基座表里那套 `overwrite_root_velocity`。
    push_max_vel_xy: float | None = None
    push_max_ang_vel: float | None = None
    joint_friction_range: tuple[float, float] = (0.01, 0.1)
    joint_damping_range: tuple[float, float] = (0.0, 0.1)
    joint_armature_range: tuple[float, float] = (0.003, 0.08)
    #: 弹性标签落在根状态上的属性名（源实现按技能区分，避免两档互相覆盖）。
    restitution_attribute: str = "_rear_stand_restitution"
    # --- runner ------------------------------------------------------------------
    learning_rate: float = 1.0e-3
    max_iterations: int = 15_000
    save_interval: int = 100
    seed: int = 1
    #: 是否开镜像损失（源：仅 rear_stand 档开）。
    mirror_loss: bool = False
