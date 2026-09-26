"""Unitree B2 的后空翻入口（薄委托：族级特技技能）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/backflip/`。本模块只给两样 b2 事实：

1. **机型绑定** `B2_VELOCITY`（复用 `b2_velocity.binding`：契约 + `model/robot.xml`
   真值 + 本机型训练实体）—— 与 `b2-velocity` / `b2-wtw` / `b2-cts` 同一份绑定；
2. **任务数值** `BACKFLIP`（`backflip/profile.py`：机型身份；配方数值沿用族级默认值，
   b2 无自有后空翻配方，详见该文件的口径说明）。

**Kit 未改一行**：b2 与 go2 的差异全部由绑定派生吸收 —— 腿序 `FR,FL,RR,RL`（动作项
按契约序排布）、MJCF 执行器包装（`XmlActuatorCfg`）、镜像腿对（右腿在 0/2 位）、
以及**腿杆碰撞几何未具名**这条：族级传感器块的腿杆惩罚按**资产事实**选匹配面
（`binding.penalized_contact_match()`：几何具名走几何名、未具名走 body 名），
语义不变（"大腿/小腿与地形的接触"），两台机型共用同一段装配。

**执行器也是资产事实**：b2 的 MJCF 内建 12 个 `<position>`、实体只包装不重设 ⇒
`binding.actuator_source == "asset"`，`robot_cfg()` 沿用自带执行器（按契约重建会重名即崩）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

# 仓库根自举（与 b2_velocity/binding.py 同一约定）：worker / schema-dump / 冒烟三种
# 运行环境都只把 training/source 或包根放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills import backflip as kit_backflip  # noqa: E402

from b2_velocity.binding import B2_VELOCITY  # noqa: E402

from .profile import BACKFLIP  # noqa: E402


def make_b2_backflip_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    """b2 的后空翻环境（族级装配 + b2 绑定与数据）。"""
    return kit_backflip.make_env_cfg(B2_VELOCITY, BACKFLIP, play=play)


def b2_backflip_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return make_b2_backflip_env_cfg(play=play)


def b2_backflip_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    """b2 的后空翻 runner（族级工厂 + b2 档案数值）。"""
    return kit_backflip.make_runner_cfg(BACKFLIP)
