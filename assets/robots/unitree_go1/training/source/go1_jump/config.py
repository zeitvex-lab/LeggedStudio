"""Unitree Go1 的 jump 环境/运行器入口（族级技能 + go1 绑定）。

## 这个文件为什么这么短

族级技能层（`adapters/mjlab/kits/quadruped_kit/skills/`）承接了 shared + trot + jump 的
全部实现：观测帧、奖励方程、命令采样、初始事件、课程、终止、传感器装配、平地起点、PPO runner。
本文件只做两件事：

1. 用 go1 的**契约 + 包内 MJCF** 建立绑定（`_build_binding()`）——关节序 / 默认姿 /
   PD 谱 / 足端几何 / 根 body 全部派生，没有一处手抄；
2. 把绑定与 profile 交给族级工厂。

## 两处机型侧输入（都在此取证）

* `init_base_height=0.42` —— 出生高，契约里没有这一项（不是机型常量，是任务参数）；
* `armature_override=None` —— **照契约取**（0.01）。go2 侧为了与它的源配方行为等价而显式
  覆盖为 0.0（见 `unitree_go2/.../go2_skills/binding.py`）；go1 没有那份源约束，
  故按契约声明，不做任何"顺手对齐"。

## 已知的复用边界（如实登记）

* go1 无足端 site：族级 `foot_heights()` 自动回退到足端几何位姿（已实现，不需要改 MJCF）；
* go1 的 MJCF 有内置 `<position kp=35>` 执行器，包内机器人工厂的 `spec_fn` 会先删掉它们
  （否则与注入的 IdealPd 双驱动）—— 这正是复用 `go1_velocity.robot_constants` 的原因：
  **同一个机器人不建第二份 MJCF/碰撞真值**。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 仓库根自举（与 go1 env_cfg / quadruped_kit 同一约定）：worker 只把包根与
# training/source 放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills import (  # noqa: E402
    QuadrupedSkillBinding,
    from_contract,
)
from adapters.mjlab.kits.quadruped_kit.skills.jump import config as kit_jump  # noqa: E402

from go1_velocity.robot_constants import get_go1_robot_cfg  # noqa: E402

from .profile import GO1_JUMP  # noqa: E402

#: 源配方的出生高（go1 站姿高；契约不声明该字段）。
INIT_BASE_HEIGHT = 0.42


def contract_path() -> Path:
    """沿目录向上找 v3 契约（assets 源树与 workspace 副本都命中包根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 unitree_go1 的 contract.json（沿目录向上查找）")


def _build_binding() -> QuadrupedSkillBinding:
    contract = json.loads(contract_path().read_text(encoding="utf-8-sig"))
    return from_contract(
        contract,
        spec_fn=get_go1_robot_cfg().spec_fn,
        base_entity_cfg=get_go1_robot_cfg,
        init_base_height=INIT_BASE_HEIGHT,
    )


GO1: QuadrupedSkillBinding = _build_binding()


def make_go1_jump_env_cfg(*, play: bool = False):
    """族级 Jump 技能 + go1 绑定（入口签名与族级工厂一致）。"""
    return kit_jump.make_env_cfg(GO1, GO1_JUMP, play=play)


def make_go1_jump_runner_cfg():
    return kit_jump.make_runner_cfg(GO1_JUMP)
