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
VELOCITY = kit_velocity_profile.VelocityProfile(dof_power_weight=-0.001)
#: 【量纲校准轮结论（2026-09-28，E1/E2 已回滚）】-0.01/-0.005/-0.001 三档在当前标准模型上
#: single 档直评 0.916/0.909/0.925——同噪声带、无显著效应；历史 0.02–0.22 是规范化前旧模型
#: （力矩 motor 接口）上测的，与现模型不可比。详见 reward_shaping_experiments.json#v3


def unitree_go2_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Create Unitree Go2 rough terrain velocity configuration."""
  return kit_velocity.make_env_cfg(GO2_VELOCITY, VELOCITY, terrain_profile="rough", play=play)


def unitree_go2_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Create Unitree Go2 flat terrain velocity configuration."""
  return kit_velocity.make_env_cfg(GO2_VELOCITY, VELOCITY, terrain_profile="flat", play=play)
