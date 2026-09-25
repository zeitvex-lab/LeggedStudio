"""族级技能的观测帧与历史缓冲。

来源：`go2_skills/trot/mdp/observations.py`（与 `.../jump/mdp/observations.py` 逐字相同，
两技能共用一份）。**只保留 trot / jump 用到的部分**：姿态类技能（hand_stand / rear_stand）
的帧与它们的域随机化标签是 go2 独占实现，未上移，仍留在 go2 包内。

第二段（`# --- 速度跟踪的算法变体帧 ---` 起）来源：
`local_tasks/robots/unitree/go2/mdp/observations.py` 里**被 CTS/AMP-CTS/TS/AMP-TS/
TS-学生/HIM/DreamWaQ/AMP-DreamWaQ 八个变体消费**的那部分（45-D 盲帧及其历史、
CTS/TS/HIM/DreamWaQ 的特权与 critic 帧、地形高度扫描、AMP 判别器状态、CTS 教师掩码）。
去机型化改动逐条记在段首注释里。

与源实现的差异只有两处，都是"去掉机型常量"：

1. 关节序：`joint_ids(env)` 取自动作项（= 契约 `action.joint_order`），不再写死 12 个 go2 关节名；
2. 帧宽不再写死（源实现 `frame_dim = 47 / 68 / 70`）：首次成帧时按**实际帧宽**建缓冲，
   于是"帧宽声明"和"帧实现"不可能漂移（声明仍在 profile 的 `actor_frame_dim` 里留档）。
   `history_length` 是技能级常量（源配方就这么多帧），保留为类属性。
"""

import math
from collections.abc import Sequence

import torch
from mjlab.entity import Entity
from mjlab.managers import ObservationTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactSensor
from mjlab.sensor.raycast_sensor import RayCastSensor

from .actions import DelayedJointPositionAction
from .contacts import (
    joint_ids,
    joint_names,
    phase,
    phase_command,
    root_euler,
    source_contact,
    source_vertical_contact,
    stance_mask,
)
from .sensors import FEET_SENSOR, TERRAIN_SCAN


def contact_observation(env, sensor_name: str, threshold: float = 5.0) -> torch.Tensor:
    sensor: ContactSensor = env.scene[sensor_name]
    return source_contact(sensor, threshold).float()


def actor_frame(env, command_name: str, cycle_time: float) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = joint_ids(env)
    return torch.cat(
        (
            phase_command(env, command_name, cycle_time),
            robot.data.root_link_ang_vel_b * 0.25,
            root_euler(robot),
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
        ),
        dim=1,
    )


def critic_frame(
    env, command_name: str, sensor_name: str, cycle_time: float
) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = joint_ids(env)
    return torch.cat(
        (
            phase_command(env, command_name, cycle_time),
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
            robot.data.root_link_lin_vel_b * 2.0,
            robot.data.root_link_ang_vel_b * 0.25,
            root_euler(robot),
            stance_mask(env, cycle_time),
            contact_observation(env, sensor_name),
        ),
        dim=1,
    )


class _SourceHistory:
    """Frame-major, oldest-to-newest history with source-style zero reset."""

    history_length: int

    def __init__(self, cfg: ObservationTermCfg, env) -> None:
        del cfg
        self._history: torch.Tensor | None = None
        self._frame_dim: int | None = None
        self._num_envs = env.num_envs
        self._device = env.device

    def _append(self, frame: torch.Tensor) -> torch.Tensor:
        if self._history is None:
            self._frame_dim = int(frame.shape[-1])
            self._history = torch.zeros(
                self._num_envs, self.history_length, self._frame_dim, device=self._device
            )
        self._history = torch.roll(self._history, shifts=-1, dims=1)
        self._history[:, -1] = frame
        return self._history.reshape(frame.shape[0], -1)

    def reset(self, env_ids=None) -> None:
        if self._history is not None:
            self._history[env_ids] = 0.0


class TrotActorHistory(_SourceHistory):
    history_length = 10

    def __call__(
        self, env, command_name: str, cycle_time: float, add_noise: bool
    ) -> torch.Tensor:
        frame = actor_frame(env, command_name, cycle_time)
        if add_noise:
            _, upper = single_frame_noise_bounds(frame.shape[-1])
            amplitude = torch.tensor(upper, device=env.device)
            frame = frame + (2.0 * torch.rand_like(frame) - 1.0) * amplitude
        return self._append(frame)


class TrotCriticHistory(_SourceHistory):
    history_length = 3

    def __call__(
        self, env, command_name: str, sensor_name: str, cycle_time: float
    ) -> torch.Tensor:
        return self._append(critic_frame(env, command_name, sensor_name, cycle_time))


def jump_phase(env, cycle_time: float) -> torch.Tensor:
    """Unwrapped source Jump phase (the stance transition happens only once)."""
    return env.episode_length_buf * env.step_dt / cycle_time


def jump_stance_mask(env, cycle_time: float) -> torch.Tensor:
    gait_phase = jump_phase(env, cycle_time)
    return torch.stack((gait_phase < 0.6, gait_phase > 0.6), dim=1).float()


def jump_phase_command(env, command_name: str, cycle_time: float) -> torch.Tensor:
    gait_phase = jump_phase(env, cycle_time)
    command = env.command_manager.get_command(command_name)
    assert command is not None
    return torch.cat(
        (
            torch.sin(2.0 * math.pi * gait_phase).unsqueeze(1),
            torch.cos(2.0 * math.pi * gait_phase).unsqueeze(1),
            command[:, :2] * 2.0,
            command[:, 2:3] * 0.25,
        ),
        dim=1,
    )


def jump_actor_frame(env, command_name: str, cycle_time: float) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = joint_ids(env)
    return torch.cat(
        (
            jump_phase_command(env, command_name, cycle_time),
            robot.data.root_link_ang_vel_b * 0.25,
            root_euler(robot),
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
        ),
        dim=1,
    )


def jump_critic_frame(
    env, command_name: str, sensor_name: str, cycle_time: float
) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    ids = joint_ids(env)
    sensor: ContactSensor = env.scene[sensor_name]
    # The source samples one friction bucket per environment and applies it to all
    # robot shapes. Reading the first robot geom therefore recovers the label.
    friction = robot.data.model.geom_friction[:, robot.indexing.geom_ids[0], 0].unsqueeze(
        1
    )
    # Go2_Jump allocates body_mass but never writes to it; its critic observes zero.
    source_body_mass = torch.zeros((env.num_envs, 1), device=env.device)
    return torch.cat(
        (
            jump_phase_command(env, command_name, cycle_time),
            robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
            robot.data.joint_pos[:, ids],
            robot.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
            robot.data.root_link_lin_vel_b * 2.0,
            robot.data.root_link_ang_vel_b * 0.25,
            root_euler(robot),
            friction,
            source_body_mass,
            jump_stance_mask(env, cycle_time),
            source_vertical_contact(sensor, 5.0).float(),
        ),
        dim=1,
    )


class JumpActorHistory(_SourceHistory):
    history_length = 10

    def __call__(
        self, env, command_name: str, cycle_time: float, add_noise: bool
    ) -> torch.Tensor:
        frame = jump_actor_frame(env, command_name, cycle_time)
        if add_noise:
            _, upper = single_frame_noise_bounds(frame.shape[-1])
            amplitude = torch.tensor(upper, device=env.device)
            frame = frame + (2.0 * torch.rand_like(frame) - 1.0) * amplitude
        return self._append(frame)


class JumpCriticHistory(_SourceHistory):
    history_length = 3

    def __call__(
        self, env, command_name: str, sensor_name: str, cycle_time: float
    ) -> torch.Tensor:
        return self._append(jump_critic_frame(env, command_name, sensor_name, cycle_time))


def single_frame_noise_bounds(
    frame_dim: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """源配方的逐段噪声幅度（按帧布局展开）。

    帧布局 = 相位 5 段 + 角速度 3 维 + 欧拉角 3 维 + 关节位置 n + 关节速度 n + 动作 n，
    故只有关节类的三段宽度随族关节数变化 —— 这里按实际帧宽反推 n，
    不再写死 `[0.01] * 12`（换关节数不会静默错位）。
    """
    non_joint = 5 + 3 + 3
    if frame_dim < non_joint or (frame_dim - non_joint) % 3 != 0:
        raise ValueError(
            f"帧宽 {frame_dim} 与族级帧布局（5 相位 + 3 角速度 + 3 欧拉 + 3×关节数）不符"
        )
    joints = (frame_dim - non_joint) // 3
    amplitudes = (
        [0.0] * 5
        + [0.2 * 0.25] * 3
        + [0.1] * 3
        + [0.01] * joints
        + [1.5 * 0.05] * joints
        + [0.0] * joints
    )
    return tuple(-value for value in amplitudes), tuple(amplitudes)


# ---------------------------------------------------------------------------
# 速度跟踪的算法变体帧（来源：包内 `...go2/mdp/observations.py` 的对应函数）
#
# 这段只服务 `skills/velocity/variants.py` 的八个算法变体（CTS / AMP-CTS / TS /
# AMP-TS / TS-学生 / HIM / DreamWaQ / AMP-DreamWaQ）。去机型化改动：
#
# * 关节序：源实现用 `asset.data.joint_pos`（**模型序**）拼帧；这里统一走
#   `joint_ids(env)`（= 动作项序 = 契约 `action.joint_order`）。对"模型序恰好等于
#   契约序"的机型逐位等价；对不同的机型，这是**策略输入布局与动作布局对齐**的修正。
# * 足端接触位：源实现写死 `contact[:, (1, 0, 3, 2)]` 的重排（注释称"共享传感器序
#   是 FR/FL/RR/RL"）。这里改成"按**观测契约声明的足序**取位"（`contact_order`
#   由 profile 给）：契约序为空时直接用传感器槽位序。见 `source_foot_contact_bits`。
# * 地形高度扫描：`terrain_heights` 的传感器名由调用方给（族级常量或 profile 数据）。
# * 域随机化标签与足端几何/root body：从 `asset.indexing`（MJCF 真值）取，无机型名。
# * 源槽位布局（TS 的 28 个 link-mass 槽）：腿标记取自**足端传感器**、角色词取自
#   契约关节名的尾段（`<腿>_<角色>_joint`）—— 两者都是契约事实，不是机型字面量。
# * 帧宽 / 历史宽度 / 缓存尺寸一律**按实际帧宽**建（不再写死 45 / 270 / 28）。
# ---------------------------------------------------------------------------

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")

#: CTS 的教师/学生环境划分周期（源配方固定 3:1：每第 4 个环境是 history-only 学生）。
CTS_TEACHER_PERIOD = 4

#: 源地形相对高度标签的偏移与缩放（`clip(h - 0.5, -1, 1) * 5`，Isaac Gym 口径）。
_TERRAIN_HEIGHT_OFFSET = 0.5
_TERRAIN_HEIGHT_SCALE = 5.0


def cts_teacher_mask(env) -> torch.Tensor:
    """CTS 的教师/学生环境划分（1 = 特权教师，0 = history-only 学生）。

    源 runner 每 4 个环境留 3 个给特权教师、第 4 个给只用历史的学生。把它做成
    一个观测组，划分就成为 rollout 的一部分（PPO minibatch 洗牌时保持稳定），
    同时不改变 actor 输入维度。环境数不是 4 的倍数时（小规模冒烟）按同一周期续。
    """
    ids = torch.arange(env.num_envs, device=env.device)
    return (ids.remainder(CTS_TEACHER_PERIOD) != 0).to(dtype=torch.float32).unsqueeze(-1)


def terrain_heights(env, sensor_name: str = TERRAIN_SCAN) -> torch.Tensor:
    """地形相对高度（射线命中点与帧原点的高差），按源口径偏移与缩放。"""
    sensor: RayCastSensor = env.scene[sensor_name]
    data = sensor.data
    frame_count, ray_count = sensor.num_frames, sensor.num_rays_per_frame
    batch = data.distances.shape[0]
    frame_z = data.frame_pos_w[:, :, 2:3]
    hit_z = data.hit_pos_w[..., 2].view(batch, frame_count, ray_count)
    heights = (frame_z - hit_z).view(batch, frame_count * ray_count)
    heights = torch.where(
        data.distances < 0,
        torch.full_like(heights, sensor.cfg.max_distance),
        heights,
    )
    # Isaac Gym's source privileged observations use
    # clip(base_height - measured_height - 0.5, -1, 1) * 5.  With a raycast
    # frame attached to the root body, ``heights`` is already base_height minus
    # the hit height, so apply the same offset/scale here.
    return (heights - _TERRAIN_HEIGHT_OFFSET).clamp(-1.0, 1.0) * _TERRAIN_HEIGHT_SCALE


def source_terrain_heights(env, sensor_name: str = TERRAIN_SCAN) -> torch.Tensor:
    """源 TS 教师的裁剪/缩放高度扫描（宽度 = 传感器帧数 × 每帧射线数）。"""
    return terrain_heights(env, sensor_name)


def _contact_mask(sensor: ContactSensor, threshold: float) -> torch.Tensor:
    """源口径的足端接触位：竖直力超阈值（无 force 字段时退化到 found）。"""
    force = sensor.data.force
    if force is not None:
        return (force[..., 2] > threshold).to(torch.float32)
    found = sensor.data.found
    assert found is not None
    return (found > 0).to(torch.float32)


def source_foot_contact_bits(
    sensor: ContactSensor,
    threshold: float,
    contact_order: Sequence[str] | None = None,
) -> torch.Tensor:
    """足端接触位，按**观测契约声明的足序**取位。

    `contact_order` 是腿标记序列；空 = 直接用传感器槽位序（传感器槽位序本身由
    绑定按契约 `leg_ids` 传入）。给定契约序时按"传感器槽位名 → 契约序"求置换再取位，
    因此传感器槽位序变了也不会静默错位。
    """
    contact = _contact_mask(sensor, threshold)
    if not contact_order:
        return contact
    wanted = tuple(str(leg).upper() for leg in contact_order)
    if contact.shape[-1] != len(wanted):
        raise ValueError(
            f"足端接触维 {tuple(contact.shape)} 与契约足序 {wanted} 不符（{len(wanted)} 腿）"
        )
    slot_legs = tuple(str(name).split("_")[0].upper() for name in sensor.primary_names)
    try:
        permutation = [slot_legs.index(leg) for leg in wanted]
    except ValueError as exc:
        raise ValueError(
            f"契约足序 {wanted} 里的腿在传感器槽位 {slot_legs} 里找不到"
        ) from exc
    return contact[:, permutation]


def _domain_randomization_fields(env, *, include_mass_com: bool) -> torch.Tensor:
    """源配置随机化的 MuJoCo 字段标签（26 / 42 维，按实际关节数展开）。"""
    asset: Entity = env.scene["robot"]
    joints = int(asset.data.joint_pos.shape[-1])
    size = (6 + 3 * joints) if include_mass_com else (2 + 2 * joints)
    zeros = torch.zeros((env.num_envs, size), device=env.device)
    try:
        model = env.sim.model
        default_gain = env.sim.get_default_field("actuator_gainprm")
        default_bias = env.sim.get_default_field("actuator_biasprm")
        ctrl_ids = asset.indexing.ctrl_ids
        kp = getattr(env, "_source_pd_kp_multiplier", None)
        kd = getattr(env, "_source_pd_kd_multiplier", None)
        if kp is None or kd is None:
            kp = model.actuator_gainprm[:, ctrl_ids, 0] / default_gain[ctrl_ids, 0].clamp_min(
                1e-6
            )
            kd = (-model.actuator_biasprm[:, ctrl_ids, 2]) / (
                -default_bias[ctrl_ids, 2]
            ).clamp_min(1e-6)
        if kp.shape[-1] != joints or kd.shape[-1] != joints:
            return zeros
        # The source buffers store the sampled coefficient itself (not a ratio to
        # the XML default), so keep the MuJoCo value in the same units.
        friction = model.geom_friction[:, asset.indexing.geom_ids, 0].mean(
            dim=-1, keepdim=True
        )
        restitution = torch.zeros_like(friction)
        if include_mass_com:
            body_id = asset.indexing.body_ids[0]
            default_mass = env.sim.get_default_field("body_mass")[body_id].clamp_min(1e-6)
            # ``added_base_masses`` in the source is an additive kilogram offset.
            mass = model.body_mass[:, body_id : body_id + 1] - default_mass
            default_ipos = env.sim.get_default_field("body_ipos")[body_id]
            com = model.body_ipos[:, body_id] - default_ipos
            torque = getattr(env, "_source_torque_multiplier", torch.ones_like(kp))
            return torch.cat((friction, restitution, mass, com, kp, kd, torque), dim=-1)
        return torch.cat((friction, restitution, kp, kd), dim=-1)
    except (AttributeError, IndexError, RuntimeError, TypeError):
        return zeros


def _delayed_policy_state(env):
    """读可选的"源延时"电机/IMU 观测。

    缓冲挂在延时动作项上、每个 MuJoCo 子步更新一次。可选读取保证未启用延时随机的
    任务仍然走普通 mjlab 路径。
    """
    try:
        action_term = env.action_manager.get_term("joint_pos")
        if not isinstance(action_term, DelayedJointPositionAction):
            return None
        motor = action_term.get_delayed_motor_observation()
        imu = action_term.get_delayed_imu_observation()
    except (AttributeError, KeyError, RuntimeError):
        return None
    if motor is None or imu is None:
        return None
    return motor[0], motor[1], imu


def source_stand_frame(
    env,
    command_name: str = "twist",
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    command_first: bool = False,
) -> torch.Tensor:
    """45-D 盲帧（命令 / IMU / 重力 / 关节位置 / 关节速度 / 上一动作）。

    源手撑与鼎立任务把 IMU 与重力放在命令之前，CTS/DreamWaQ/TS 把命令放最前；
    用一个开关表达两种来源契约，不重复状态拼装。
    """
    asset: Entity = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)
    assert command is not None, f"Command '{command_name}' not found."
    ids = joint_ids(env)
    projected_gravity = asset.data.projected_gravity_b
    command_obs = command[:, :3] * torch.tensor((2.0, 2.0, 0.25), device=env.device)
    delayed = _delayed_policy_state(env)
    if delayed is None:
        imu_obs = asset.data.root_link_ang_vel_b * 0.25
        joint_pos = asset.data.joint_pos[:, ids] - asset.data.default_joint_pos[:, ids]
        joint_vel = asset.data.joint_vel[:, ids] * 0.05
    else:
        joint_pos, joint_vel, delayed_imu = delayed
        imu_obs = delayed_imu[:, :3]
    state = (
        (command_obs, imu_obs, projected_gravity)
        if command_first
        else (imu_obs, projected_gravity, command_obs)
    )
    return torch.cat((*state, joint_pos, joint_vel, env.action_manager.action), dim=-1)


def dreamwaq_privileged_frame(
    env,
    command_name: str = "twist",
    sensor_name: str = TERRAIN_SCAN,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """261-D DreamWaQ 特权帧（地形 + 体线速度 + 域随机化 + 45-D 盲帧段）。"""
    asset: Entity = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)
    assert command is not None, f"Command '{command_name}' not found."
    ids = joint_ids(env)
    terrain = terrain_heights(env, sensor_name)
    zeros = _domain_randomization_fields(env, include_mass_com=False).to(terrain.dtype)
    return torch.cat(
        (
            terrain,
            asset.data.root_link_lin_vel_b,
            zeros,
            command[:, :3] * torch.tensor((2.0, 2.0, 0.25), device=env.device),
            asset.data.root_link_ang_vel_b * 0.25,
            asset.data.projected_gravity_b,
            asset.data.joint_pos[:, ids] - asset.data.default_joint_pos[:, ids],
            asset.data.joint_vel[:, ids] * 0.05,
            env.action_manager.action,
        ),
        dim=-1,
    )


def dreamwaq_velocity_target(
    env,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """DreamWaQ VAE 的 3-D 体坐标系速度标签。"""
    asset: Entity = env.scene[asset_cfg.name]
    return asset.data.root_link_lin_vel_b


def _contract_legs(env, contact_sensor_name: str) -> tuple[str, ...]:
    """契约腿序（= 足端传感器的 primary 名序，由绑定按契约腿序传入）。"""
    sensor: ContactSensor = env.scene[contact_sensor_name]
    return tuple(str(name).split("_")[0] for name in sensor.primary_names)


def _contract_link_roles(env, legs: Sequence[str]) -> tuple[str, ...]:
    """契约关节名尾段里的**角色词**（`FL_hip_joint` → `hip`），按首次出现序。"""
    roles: list[str] = []
    for name in joint_names(env):
        suffix = str(name)
        for leg in legs:
            prefix = f"{leg}_"
            if suffix.lower().startswith(prefix.lower()):
                suffix = suffix[len(prefix) :]
                break
        role = suffix.rsplit("_", 1)[0] if "_" in suffix else suffix
        if role and role not in roles:
            roles.append(role)
    if not roles:
        raise RuntimeError("契约关节名里找不到角色词（`<腿>_<角色>_joint` 约定）")
    return tuple(roles)


def cts_privileged_frame(
    env,
    sensor_name: str = TERRAIN_SCAN,
    contact_sensor_name: str = FEET_SENSOR,
    contact_order: Sequence[str] | None = None,
) -> torch.Tensor:
    """CTS 编码器输入（42 域随机化 + 4 接触 + 地形高度扫描）。"""
    terrain = terrain_heights(env, sensor_name)
    sensor: ContactSensor = env.scene[contact_sensor_name]
    reserved = _domain_randomization_fields(env, include_mass_com=True).to(terrain.dtype)
    return torch.cat(
        (
            reserved,
            source_foot_contact_bits(sensor, 1.0, contact_order).to(terrain.dtype),
            terrain,
        ),
        dim=-1,
    )


def ts_privileged_frame(
    env,
    contact_sensor_name: str = FEET_SENSOR,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    contact_order: Sequence[str] | None = None,
) -> torch.Tensor:
    """与地形无关的 TS 教师编码器输入（域随机化 + 4 足端接触）。

    源 TS 环境把 ``privileged_buf`` 与三倍宽的 critic 分开：域随机化字段后跟
    4 个足端接触位，地形与基座线速度只进 critic。保持独立观测组，
    使教师编码器拿到与源 runner 相同的契约。

    源在公共块里插了一段 **link-mass 比** 槽位；MuJoCo 资产不暴露 Isaac Gym 的精确
    link 序，固定子体被折叠进运动父体，所以缺失的比值保持中性值 1、已表达的 link
    放回它原来的槽位。槽位布局（腿序 × 角色序）从**足端传感器**与**契约关节名尾段**
    派生 —— 换机型不需要改代码。
    """
    asset: Entity = env.scene[asset_cfg.name]
    sensor: ContactSensor = env.scene[contact_sensor_name]
    base_fields = _domain_randomization_fields(env, include_mass_com=True)
    legs = _contract_legs(env, contact_sensor_name)
    roles = _contract_link_roles(env, legs)
    stride = 2 * len(roles)
    # 源布局：2（头预留）+ 每腿 stride + 2（尾预留）。
    link_mass = torch.ones(
        (env.num_envs, 2 + len(legs) * stride + 2),
        device=env.device,
        dtype=base_fields.dtype,
    )
    try:
        model = env.sim.model
        body_ids = asset.indexing.body_ids
        source_slots = {
            f"{leg}_{role}": 2 + leg_index * stride + role_index
            for leg_index, leg in enumerate(legs)
            for role_index, role in enumerate(roles)
        }
        default_mass = env.sim.get_default_field("body_mass")
        for local_index, body_name in enumerate(asset.body_names):
            source_index = source_slots.get(body_name)
            if source_index is None:
                continue
            body_id = body_ids[local_index]
            link_mass[:, source_index] = model.body_mass[:, body_id] / default_mass[
                body_id
            ].clamp_min(1.0e-6)
    except (AttributeError, IndexError, RuntimeError, TypeError):
        pass

    # Reorder the shared block to match the source layout:
    # friction, restitution, base mass, link masses, COM, kp, kd, torque.
    base_mass = base_fields[:, 2:3]
    com = base_fields[:, 3:6]
    gains_and_torque = base_fields[:, 6:]
    domain = torch.cat(
        (base_fields[:, :2], base_mass, link_mass, com, gains_and_torque), dim=-1
    )
    contact = source_foot_contact_bits(sensor, 1.0, contact_order).to(domain.dtype)
    return torch.cat((domain, contact), dim=-1)


def cts_critic_frame(
    env,
    sensor_name: str = TERRAIN_SCAN,
    contact_sensor_name: str = FEET_SENSOR,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    include_lin_vel: bool = False,
    contact_order: Sequence[str] | None = None,
) -> torch.Tensor:
    """CTS 价值输入（盲帧 + 特权块 [ + 体线速度]）。"""
    asset: Entity = env.scene[asset_cfg.name]
    actor = source_stand_frame(env, asset_cfg=asset_cfg, command_first=True)
    privileged = cts_privileged_frame(
        env, sensor_name, contact_sensor_name, contact_order
    )
    if include_lin_vel:
        return torch.cat((actor, privileged, asset.data.root_link_lin_vel_b), dim=-1)
    return torch.cat((actor, privileged), dim=-1)


def ts_critic_frame(
    env,
    sensor_name: str = TERRAIN_SCAN,
    contact_sensor_name: str = FEET_SENSOR,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
    contact_order: Sequence[str] | None = None,
) -> torch.Tensor:
    """TS 价值输入，按源拼接序。

    源 ``LeggedRobotAMP_TS`` 的 critic 缓冲是
    ``base_lin_vel || actor_obs || domain || contacts || terrain``。
    速度前缀必须保留（CTS 是把它**追加**在 AMP-CTS 里）—— 训练好的 TS checkpoint
    与价值网络依赖这个顺序。
    """
    asset: Entity = env.scene[asset_cfg.name]
    actor = source_stand_frame(env, asset_cfg=asset_cfg, command_first=True)
    ts_privileged = ts_privileged_frame(
        env,
        contact_sensor_name=contact_sensor_name,
        asset_cfg=asset_cfg,
        contact_order=contact_order,
    )
    contact = ts_privileged[:, -len(_contract_legs(env, contact_sensor_name)) :]
    domain = ts_privileged[:, : -len(_contract_legs(env, contact_sensor_name))]
    terrain = terrain_heights(env, sensor_name).to(actor.dtype)
    return torch.cat(
        (asset.data.root_link_lin_vel_b, actor, domain, contact, terrain), dim=-1
    )


def amp_state_frame(
    env,
    sensor_name: str = TERRAIN_SCAN,
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """AMP 判别器输入（源口径：**未缩放**的绝对关节位置 + 地形相对根高）。"""
    asset: Entity = env.scene[asset_cfg.name]
    ids = joint_ids(env)
    # Source ``_get_base_heights`` averages root-height minus nearby terrain
    # samples.  Recover the equivalent scalar from the raycast heights when the
    # sensor is available; flat scenes naturally reduce to the root height.
    try:
        terrain = terrain_heights(env, sensor_name)
        base_height = (terrain / _TERRAIN_HEIGHT_SCALE + _TERRAIN_HEIGHT_OFFSET).mean(
            dim=-1, keepdim=True
        )
    except (KeyError, AttributeError, RuntimeError, TypeError):
        base_height = asset.data.root_link_pos_w[:, 2:3] - env.scene.env_origins[:, 2:3]
    return torch.cat(
        (
            asset.data.joint_pos[:, ids],
            asset.data.root_link_lin_vel_b,
            asset.data.root_link_ang_vel_b,
            asset.data.joint_vel[:, ids],
            base_height,
        ),
        dim=-1,
    )


def him_privileged_frame(
    env,
    command_name: str = "twist",
    asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
    """HIM 特权帧：``noisy_frame || base_lin_vel * 2``。

    源 HIMLoco 的每步特权帧共享带噪的 ``current_obs`` 前缀，并在其末尾按
    ``obs_scales.lin_vel = 2.0`` 追加干净基座线速度 —— 这既是估计器的速度真值切片，
    也让对比学习目标切片自洽。
    """
    asset: Entity = env.scene[asset_cfg.name]
    history = getattr(env, "_him_history_term", None)
    if history is not None and history._frame is not None:
        frame = history._frame.clone()
    else:
        frame = source_stand_frame(env, command_name, command_first=True)
    lin_vel = asset.data.root_link_lin_vel_b * 2.0
    return torch.cat((frame, lin_vel), dim=-1)


class SourceActorFrame:
    """45-D actor 帧，缓存起来让历史组复用同一份样本。

    mjlab 当前的 `ObservationTermCfg` 没有跨项 history 钩子，源 ``obs_hist_buf``
    （重复**处理过的** actor 帧，含它的策略噪声样本）在这里复现：actor 项自己采噪声
    并把结果留给 `SourceActorHistory`。
    """

    def __init__(self, cfg, env) -> None:
        params = getattr(cfg, "params", {}) or {}
        self._command_name = str(params.get("command_name", "twist"))
        self._command_first = bool(params.get("command_first", False))
        self._add_noise = bool(params.get("add_noise", True))
        self._noise = params.get("noise")
        self._frame: torch.Tensor | None = None
        env._source_actor_term = self

    def __call__(self, env, **_kwargs) -> torch.Tensor:
        frame = source_stand_frame(
            env, self._command_name, command_first=self._command_first
        )
        if self._add_noise and self._noise is not None:
            low = torch.as_tensor(self._noise.n_min, device=env.device, dtype=frame.dtype)
            high = torch.as_tensor(self._noise.n_max, device=env.device, dtype=frame.dtype)
            frame = frame + low + (high - low) * torch.rand_like(frame)
        if self._frame is None or self._frame.shape != frame.shape:
            self._frame = frame.clone()
        else:
            self._frame.copy_(frame)
        return self._frame

    def reset(self, env_ids=None) -> None:
        if self._frame is None:
            return
        if env_ids is None:
            self._frame.zero_()
        else:
            self._frame[env_ids] = 0.0


class SourceActorHistory:
    """帧优先（旧→新）的 actor 历史，末帧 = 当前帧。

    ``length`` 应当是源帧数 + 1（mjlab 的历史含当前帧）；条件模型会丢掉最新的那个
    45-D 块，以还原源"仅前序帧"的窗口。
    """

    def __init__(self, cfg, env) -> None:
        params = getattr(cfg, "params", {}) or {}
        self._length = max(1, int(params.get("length", 1)))
        self._buf: torch.Tensor | None = None
        self._num_envs = env.num_envs
        self._device = env.device
        self._dtype = torch.float32
        env._source_history_term = self

    def __call__(self, env, **_kwargs) -> torch.Tensor:
        frame = self._frame(env)
        if self._buf is None or self._buf.shape[-1] != frame.shape[-1]:
            self._buf = torch.zeros(
                (frame.shape[0], self._length, int(frame.shape[-1])),
                device=self._device,
                dtype=self._dtype,
            )
        out = self._buf.reshape(env.num_envs, -1).clone()
        self._buf = torch.roll(self._buf, shifts=-1, dims=1)
        self._buf[:, -1] = frame
        return out

    def _frame(self, env) -> torch.Tensor:
        actor = getattr(env, "_source_actor_term", None)
        if actor is None or actor._frame is None:
            raise RuntimeError(
                "SourceActorHistory 需要同组内的 SourceActorFrame 先生成当前帧"
                "（源 ``obs_hist_buf`` 语义：历史 = 处理过的 actor 帧序列）"
            )
        return actor._frame

    def reset(self, env_ids=None) -> None:
        if self._buf is None:
            return
        if env_ids is None:
            self._buf.zero_()
        else:
            self._buf[env_ids] = 0.0


class HimHistory:
    """HIMLoco ``obs_hist_buf``：actor 帧按**最新在前**堆叠。

    HIM 把整段堆叠历史喂给估计器与 actor（``cat(current, older)``），而
    CTS/DreamWaQ 的历史编码器只吃当前帧之前的帧。该项自己采观测噪声并缓存处理过的
    （带噪）当前帧，供 `him_privileged_frame` 复用同一份样本 —— 与源特权缓冲共享
    带噪 ``current_obs`` 前缀的做法一致。
    """

    def __init__(self, cfg, env) -> None:
        params = getattr(cfg, "params", {}) or {}
        self._command_name = str(params.get("command_name", "twist"))
        self._command_first = bool(params.get("command_first", True))
        self._add_noise = bool(params.get("add_noise", True))
        self._noise = params.get("noise")
        self._length = max(1, int(params.get("length", 6)))
        self._frame: torch.Tensor | None = None
        self._buf: torch.Tensor | None = None
        self._device = env.device
        self._dtype = torch.float32
        env._him_history_term = self

    def __call__(self, env, **_kwargs) -> torch.Tensor:
        frame = source_stand_frame(
            env, self._command_name, command_first=self._command_first
        )
        if self._add_noise and self._noise is not None:
            low = torch.as_tensor(self._noise.n_min, device=env.device, dtype=frame.dtype)
            high = torch.as_tensor(self._noise.n_max, device=env.device, dtype=frame.dtype)
            frame = frame + low + (high - low) * torch.rand_like(frame)
        if self._frame is None or self._frame.shape != frame.shape:
            self._frame = frame.clone()
        else:
            self._frame.copy_(frame)
        if self._buf is None or self._buf.shape[-1] != frame.shape[-1]:
            self._buf = torch.zeros(
                (frame.shape[0], self._length, int(frame.shape[-1])),
                device=self._device,
                dtype=self._dtype,
            )
        # Source stacking keeps the newest frame at offset 0; older frames follow
        # in recency order so the first block of the flattened history is the
        # current observation.
        self._buf = torch.roll(self._buf, shifts=1, dims=1)
        self._buf[:, 0] = frame
        return self._buf.reshape(env.num_envs, -1)

    def reset(self, env_ids=None) -> None:
        for buf in (self._frame, self._buf):
            if buf is None:
                continue
            if env_ids is None:
                buf.zero_()
            else:
                buf[env_ids] = 0.0
