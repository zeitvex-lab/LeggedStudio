"""Go2 locomotion environment factory support（薄委托：族级 velocity 技能）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/velocity/`。本模块只剩三样 go2 事实：

1. **机型绑定** `GO2_VELOCITY`（`locomotion/binding.py`：契约 + `training.xml` 真值 +
   本机型训练实体）——足端几何/site、腿杆与躯干碰撞几何、根 body、关节序、逐关节动作缩放
   全部由 Kit 从它派生；
2. **任务数值** `VELOCITY`（`VelocityProfile`：命令/地形/DR/奖励权重/终止阈值）；
3. **入口函数**（公开名不动，profile 的 `entrypoints` 照旧解析到这里）。

原先本文件里的 327 行实现（写死 `FR/FL/RR/RL` 腿序、`base_link`、`<leg>_thigh_collision` /
`<leg>_calf{i}_collision` / `base.*_collision`、足端 site 表、`pose` std 表的 `FR|FL|RR|RL`
键、逐关节动作缩放表）已全部上移为族级派生，机型侧零字面量。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（与 go2_skills/binding.py 同一约定）：worker / schema-dump / 冒烟三种运行
# 环境都只把 training/source（或包根）放进 sys.path，不保证仓库根在场；沿目录向上找
# adapters/mjlab 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from mjlab.envs import ManagerBasedRlEnvCfg  # noqa: E402

from adapters.mjlab.kits.quadruped_kit.skills.velocity import (  # noqa: E402
    TerrainProfile as TerrainProfile,
)
from adapters.mjlab.kits.quadruped_kit.skills.velocity import config as kit_velocity
from adapters.mjlab.kits.quadruped_kit.skills.velocity import (
    profile as kit_velocity_profile,
)

from .binding import GO2_VELOCITY

#: go2 的 velocity 任务数值。**唯一与族级默认不同的一项**是机械功率惩罚
#: （`dof_power_abs`，权重 -0.001）——结构层攻关收口（任务清单 §2.1 序 1，2026-09-18
#: 六组同批实验后定格）：保留 V1（dof_power 型功率惩罚，-0.001 保守档）为默认任务
#: 结构——六组中唯一不劣于 CTRL 的变体（0.211 vs CTRL 0.189，其余变体见
#: tools/baselines/reward_shaping_experiments.json v2 段）。功率 early-termination
#: （源包 `mdp/terminations.py::go2_power_runaway`）经 V2（1500/900 零触发）/V3
#: （120/60 咬死步态，0.034）/V4（250/100，0.179）三档标定后**不进默认任务**：训练侧
#: |tau*v| 量级比评测侧低一个量级，训练侧截断无法转化为评测侧 dof_power 收益。
#: 其余数值（命令档/地形档/DR 档/奖励静音位/70° 平地倾角）与族级默认逐值相同，
#: 不在此重复声明 —— 需要覆盖时按字段名加进来即可。
#: G1（2026-09-28，legged_gym 系对齐实验）：按上游 legged_gym 基座/anymal flat 实操对齐——
#: ① feet_air_time +1.0 正激励（上游学走的主正奖励，自产此前静音）；
#: ② 足端三罚关停（上游无 clearance/swing/slip 项，基座 -2.0/-0.25/-0.1 压垮早期探索）；
#: ③ action_rate -0.1→-0.01（上游同款）；④ dof_power 不注册（上游 torques 仅 -1e-5 量级）；
#: ⑤ only_positive_rewards=True（legged_gym 基座技巧：负总奖励截 0）。
#: F1/F2 证据链（reward_shaping_experiments#v3）：预算与 stand_still 单变量都不成立，任务结构才是根因。
VELOCITY = kit_velocity_profile.VelocityProfile(
    dof_power_weight=None,

    air_time_weight=1.0,  # G1 对齐：上游学走主正激励（字段名沿用现有 wire）
    foot_clearance_override=0.0,
    foot_swing_height_override=0.0,
    foot_slip_override=0.0,
    action_rate_override=-0.01,
    only_positive_rewards=True,
    # 姿态/定高对齐（G2→G3，2026-09-29）：lainlab trot 参照系同款项，但权重降档——
    # G2 实验（原值 -5/-2 + only_positive，750 轮）：runner 同链推理 0.5 命令位移仅
    # 0.09m（旧结构 750 轮 0.395 能走）⇒ lainlab 的数值在其整套 economics
    # （无 only_positive + 步态整形 + 3000+ 轮）下成立，直接搬进 G1 组合过重，
    # 早期负项压垮行走学习。降档 −1.0/−0.5 保 750 轮先学会走，再观定高趋势。
    base_height_target=0.29,
    base_height_weight=-1.0,
    orientation_weight=-0.5,
    # 命令通道（G6，2026-09-30）：lainlab trot 同款（heading 关 + yaw ±1.0 全开）。
    # G4/G5 的"判负"按学步系列同一教训重估 = 预算假阳性——lainlab trot 自配
    # 4096 envs × 15000 轮，我们此前最多 1024×2000（等效 4096×500，连"能看"线
    # 都没到）。G6 = 同配方 × 1024×8000（等效 4096×2000）让预算说话。
    command_heading=False,
    command_rel_heading_envs=0.0,
    command_ang_vel_range=(-1.0, 1.0),
)
#: 【量纲校准轮结论（2026-09-28，E1/E2 已回滚）】-0.01/-0.005/-0.001 三档在当前标准模型上
#: single 档直评 0.916/0.909/0.925——同噪声带、无显著效应；历史 0.02–0.22 是规范化前旧模型
#: （力矩 motor 接口）上测的，与现模型不可比。详见 reward_shaping_experiments.json#v3


def unitree_go2_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Create Unitree Go2 rough terrain velocity configuration."""
  return kit_velocity.make_env_cfg(GO2_VELOCITY, VELOCITY, terrain_profile="rough", play=play)


def unitree_go2_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Create Unitree Go2 flat terrain velocity configuration."""
  return kit_velocity.make_env_cfg(GO2_VELOCITY, VELOCITY, terrain_profile="flat", play=play)


def unitree_go2_stairs_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Go2 台阶速度档（2026-10-01 stairs 全族化）：族级 velocity + stairs 地形档。"""
  return kit_velocity.make_env_cfg(GO2_VELOCITY, VELOCITY, terrain_profile="stairs", play=play)
