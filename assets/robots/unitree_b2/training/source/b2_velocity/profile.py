"""B2 的 velocity 任务数值 + 机型侧任务配方。

族级技能层（`quadruped_kit/skills/velocity/`）装配**族级机制**（基座 env cfg / 实体 /
动作装配 / 地形课程 / viewer / flat 与 play 收尾）；本模块给两样：

1. **`B2_VELOCITY`（`VelocityProfile`）**：本档案的族级开关与任务数值；
2. **`recipe`**：本机型源配方里 Kit 装不出来的那几样（传感器表 / 终止 / 事件 / 命令），
   逐项来自原 `b2_velocity.env_cfg`（B8 去包化时上移过一半，本轮把整段收回数据面）。

## 口径登记（不静默改行为）

* **动作缩放**：源配方 `B2_ACTION_SCALE = action_scale_from_actuators(..., 0.25)` 是
  **全 12 关节 0.25**；契约 `actuator_profile.by_role`（hip 0.125 / thigh 0.25 / calf 0.25）
  与 `simulation/config.json` 的 `action_scale_by_joint` 则是**逐角色**的。两者冲突 ——
  本档案按"不改行为"保留现行的 0.25（`action_scale_by_role`），**冲突登记在案**：
  若按契约派生（`binding.action_scale_by_joint()`，XmlActuatorCfg 的比值恒 1.0），
  髋关节会变成 0.125（与 sim2sim 声明一致）。取哪一个是裁决题，不在本笔里改。
* **`upright` 的 `terrain_sensor_names`**：族级 rough 配方给该项（按地形法线算倾角，
  go2 口径）；b2 的源配方没有它（按世界 up 算）。本档案撤掉，保持原奖励方程。
* **接触监看块**：b2 的 rough 口径是"足端 + **非足端**"两组传感器 + 非足端非法接触
  终止（力阈值 10），不是族级默认的四组（自碰撞/大腿/小腿/躯干）；
  `contact_supervision=False` + 本模块 recipe 自备。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.managers import TerminationTermCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

# 仓库根自举（与 binding.py 同一约定）。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.velocity.profile import (  # noqa: E402
    VelocityProfile,
)

#: 非足端接触传感器（源配方 `b2_velocity.env_cfg::_contact_sensors` 的第二组）。
NONFOOT_SENSOR = "nonfoot_ground_touch"
#: 非足端非法接触终止的力阈值（源配方值）。
ILLEGAL_CONTACT_FORCE_THRESHOLD = 10.0


def _b2_recipe(
    cfg: ManagerBasedRlEnvCfg,
    binding,
    profile: VelocityProfile,
    *,
    terrain_profile: str,
    play: bool,
) -> None:
    """机型侧任务配方（源 `b2_velocity.env_cfg` 的机型专属接线，逐项同构）。"""
    # 1) 接触传感器：足端（族级已按本机型足端几何装配）+ 非足端全身几何
    #    （`.*_collision`，含足端 —— 源配方口径如此，保持原样）。
    cfg.scene.sensors = (cfg.scene.sensors or ()) + (
        ContactSensorCfg(
            name=NONFOOT_SENSOR,
            primary=ContactMatch(mode="geom", pattern=".*_collision", entity="robot"),
            secondary=ContactMatch(mode="body", pattern="terrain"),
            fields=("found", "force"),
            reduce="netforce",
            num_slots=1,
            track_air_time=True,
        ),
    )

    # 2) 非法接触终止：挂非足端传感器（不是族级的 thigh_ground_touch——本机型不装它）。
    cfg.terminations["illegal_contact"] = TerminationTermCfg(
        func=velocity_mdp.illegal_contact,
        params={
            "sensor_name": NONFOOT_SENSOR,
            "force_threshold": ILLEGAL_CONTACT_FORCE_THRESHOLD,
        },
    )

    # 3) 本机型源配方：rough 档不按朝向终止（地形上倾斜是常态）；flat 档同样不撤
    #    fell_over（源 flat 档只有非法接触 + 超时两条终止）——族级 flat 收尾会补
    #    fell_over(70°)，本机型按源配方撤掉。
    if terrain_profile == "flat":
        cfg.terminations.pop("fell_over", None)

    # 4) 足端摩擦：基座 evento 的 geom 列表是空的（本机型 MJCF 的足端几何在
    #    CollisionCfg 里按正则重建、基座事件引用的名字在它身上不存在）⇒ 源配方整项撤掉。
    cfg.events.pop("foot_friction", None)

    # 5) 命令可视化 z 偏移（源配方值；族级默认留基座值）。
    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.viz.z_offset = 0.5

    # 6) play + flat：源配方的展厅命令档（族级 play 收尾只覆盖 lin_vel_x / ang_vel_z）。
    if play and terrain_profile == "flat":
        command.ranges.lin_vel_x = (-1.0, 1.5)
        command.ranges.lin_vel_y = (-0.5, 0.5)
        command.ranges.ang_vel_z = (-0.7, 0.7)

    # 7) 源配方的 upright 按世界 up 算倾角（族级 rough 配方给 terrain_sensor_names）；
    #    flat 档族级收尾已撤该项，这里统一撤掉。
    cfg.rewards["upright"].params.pop("terrain_sensor_names", None)


B2_VELOCITY = VelocityProfile(
    # 接触监看块自备（见模块 docstring）⇒ 族级四组传感器 / 三项惩罚 / 摩擦三轴 DR /
    # thigh 终止都不装配。
    contact_supervision=False,
    # 源配方不碰 MuJoCo 的 impratio / cone（族级 go2 配方才调）：保持引擎默认。
    mujoco_solver_tuning=False,
    # 源装配骨架（`kit.new_velocity_env_cfg`）统一给 `sim.nconmax = None`（全身接触
    # 传感器需要余量）；族级 go2 配方不碰该项。
    contact_sensor_headroom=True,
    # flat 档撤 terrain_scan 传感器 + height_scan 观测（源配方 `apply_flat_postlude` 两项全开）。
    flat_drop_terrain_scan=True,
    flat_drop_height_scan=True,
    # 动作缩放：源配方 = 全关节 0.25（见模块 docstring 的口径登记）。
    action_scale_by_role={"hip_abduction": 0.25, "hip_pitch": 0.25, "knee": 0.25},
    # G1 对齐（2026-09-28，legged_gym 系结构；go2 同款实证 motion 0→0.459）：足端三罚
    # 归零（上游无此三项，基座 -2.0/-0.25/-0.1 压垮早期探索）、action_rate -0.01（上游
    # 同款）、only_positive_rewards（负总奖励截 0）、stand_still 显式关（F1 实证短预算
    # 下惩罚主导；预算/课程到位后再评估启用）。
    air_time_weight=1.0,
    foot_clearance_override=0.0,
    foot_swing_height_override=0.0,
    foot_slip_override=0.0,
    action_rate_override=-0.01,
    only_positive_rewards=True,
    recipe=_b2_recipe,
)
