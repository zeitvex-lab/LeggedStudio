"""族级技能层（wheel_leg skills）—— velocity。

## 这一层解决什么

轮足族此前**没有**族级技能层：速度跟踪的框架底座（`mdp/` + `velocity_env_cfg.py`）已上移，
但"这条技能长什么样"（动作分段、观测换项、奖励表、地形档、四个变体）仍写在每个机型的
包内（go2w 的 333 行 `env_cfgs.py` 是典型）。本层把这组实现上移为族级技能：机型包只保留
薄委托（入口名不动）+ 一份**机型绑定** + 一份 profile 数据。

## 三层各自的职责

* `family.py`  —— 族角色/命名解析（读 `registry/families/wheel_leg.json`，机型名不出现）；
* `binding.py` —— 机型绑定：契约 + MJCF 真值 → 技能层要的形状（**唯一的机型入口**）；
* `velocity/`  —— 技能实现：`config.py`（四变体同一份装配）+ `profile.py`（源配方数据类）。

## 关节序真值怎么传（关键设计）

策略的关节布局 = 动作项的输出顺序。本层不接受任何关节名参数：腿/轮段从绑定按契约
`action.joint_order` **连续分段**（腿段在前、轮段在后）交给共享动作工厂
（`kits/joint_actions.build_joint_actions`，`preserve_order=True` 的有序动作项），
观测/奖励一律用绑定派生的 `SceneEntityCfg`（同一份契约序）。
这样"观测里的 joint_pos 顺序"与"动作维顺序"**结构上不可能错位**——轮足机型里
MJCF 序（按腿混排）与契约序（腿先轮后）本就不同，从 MJCF 推序必错。
"""

from __future__ import annotations

from .binding import ActuatorGroup, WheelLegSkillBinding, from_contract
from .velocity.competition import VARIANTS as COMPETITION_VARIANTS
from .velocity.config import VARIANTS, make_env_cfg as make_velocity_env_cfg
from .velocity.official import VARIANTS as OFFICIAL_VARIANTS
from .velocity.profile import (
    UNSET,
    CommandRanges,
    CompetitionActionSpec,
    CompetitionCommandLevel,
    CompetitionCommandSpec,
    CompetitionEventSpec,
    CompetitionMetric,
    CompetitionObservationSpec,
    CompetitionRewardSpec,
    CompetitionSimSpec,
    CompetitionVelocityProfile,
    LegsOnlyRecipe,
    OfficialVelocityProfile,
    SimOverride,
    VelocityProfile,
)

__all__ = [
    "COMPETITION_VARIANTS",
    "OFFICIAL_VARIANTS",
    "UNSET",
    "VARIANTS",
    "ActuatorGroup",
    "CommandRanges",
    "CompetitionActionSpec",
    "CompetitionCommandLevel",
    "CompetitionCommandSpec",
    "CompetitionEventSpec",
    "CompetitionMetric",
    "CompetitionObservationSpec",
    "CompetitionRewardSpec",
    "CompetitionSimSpec",
    "CompetitionVelocityProfile",
    "LegsOnlyRecipe",
    "OfficialVelocityProfile",
    "SimOverride",
    "VelocityProfile",
    "WheelLegSkillBinding",
    "from_contract",
    "make_velocity_env_cfg",
]
