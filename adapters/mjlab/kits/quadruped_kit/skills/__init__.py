"""族级技能层（quadruped skills）—— shared / trot / jump / imitation。

## 这一层解决什么

2026-09-24 之前，"特技 jump"与它的公共件（`shared/`）只存在于 `unitree_go2` 一个包里，
入口硬编码 `local_tasks.robots.unitree.go2.tasks.go2_skills.*` ⇒ 同族其它机型**没得复用**。
本层把这组实现上移为族级技能：机型包只保留薄委托（入口名不动）+ 一份**机型绑定**。

## 三层各自的职责

* `family.py`  —— 族角色/命名解析（读 `registry/families/<族>.json`，机型名不出现）；
* `binding.py` —— 机型绑定：契约 + MJCF 真值 → 技能层要的形状（**唯一的机型入口**）；
* `mdp/`、`trot/`、`jump/` —— 技能实现：关节序从动作项取、足端从足端传感器取、
  髋等角色从族别名取，**不含任何机型的名字或数值**。

## 关节序真值怎么传（关键设计）

策略的关节布局 = 动作项的输出顺序。本层的观测/奖励**不接受**任何关节名参数：
它们统一从动作项（`joint_pos`）声明的目标名序解析 `joint_ids(env)` —— 而动作项的顺序
由机型绑定按契约 `action.joint_order` 以 `preserve_order=True` 建立。
这样"观测里的 joint_pos 顺序"与"动作维顺序"**结构上不可能错位**
（这正是 go1 的陷阱：它的 MJCF 腿序是 FR/FL/RL/RR，契约是 FL/FR/RL/RR）。
"""

from __future__ import annotations

from .binding import ActuatorGroup, QuadrupedSkillBinding, from_contract
from .imitation.config import make_env_cfg as make_imitation_env_cfg
from .imitation.config import make_runner_cfg as make_imitation_runner_cfg
from .imitation.profile import AmpPpoAlgorithmCfg, AmpProfile
from .jump.config import make_env_cfg as make_jump_env_cfg
from .jump.config import make_runner_cfg as make_jump_runner_cfg
from .jump.profile import JumpProfile
from .trot.config import make_env_cfg as make_trot_env_cfg
from .trot.config import make_runner_cfg as make_trot_runner_cfg
from .trot.profile import TrotProfile

__all__ = [
    "ActuatorGroup",
    "AmpPpoAlgorithmCfg",
    "AmpProfile",
    "JumpProfile",
    "QuadrupedSkillBinding",
    "TrotProfile",
    "from_contract",
    "make_imitation_env_cfg",
    "make_imitation_runner_cfg",
    "make_jump_env_cfg",
    "make_jump_runner_cfg",
    "make_trot_env_cfg",
    "make_trot_runner_cfg",
]
