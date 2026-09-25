"""Deeprobotics Lite3 velocity environment configurations（薄委托：族级 velocity 技能）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/velocity/`。本模块只剩三样 lite3 事实：

1. **机型绑定** `LITE3_VELOCITY`（`binding.py`：契约 + `model/robot.xml` 真值 + 本机型训练实体，
   `XmlActuatorCfg` 包装 MJCF 执行器 —— 族声明的 `actuator_binding="mjcf_wrapped"` 口径）；
2. **任务数值与机型配方** `LITE3_VELOCITY`（`profile.py`：`VelocityProfile` + recipe ——
   45 维 rl_sdk 观测、官方 24 项奖励表、两组接触传感器、事件/终止/命令/地形子项）；
3. **入口函数**（公开名不动：`lite3_flat_env_cfg` / `lite3_rough_env_cfg` / `lite3_runner_cfg`，
   profile 的 `entrypoints` 与冒烟/训练链照旧解析到这里）。

原先本文件里的接线（装配骨架 + 高度扫描重指 + 接触传感器 + 观测重排 + 奖励表 + 事件与
终止 + 命令档 + play/flat 收尾）已上移：族级机制在 Kit，机型专属那几样在 `profile.py` 的
recipe（同包数据面）。**足端高度扫描**改由绑定能力表达（本机型无足端 site ⇒ body 帧
`<LR>_FOOT`，见 `profile.py` 的口径登记）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg

# 仓库根自举（见 kits/quadruped_kit 模块注释）：worker / schema-dump / 冒烟三种
# 运行环境都只把 training/source 或包根放进 sys.path；沿目录向上找 adapters/mjlab
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits import quadruped_kit as kit  # noqa: E402
from adapters.mjlab.kits.quadruped_kit.skills.velocity import config as kit_velocity  # noqa: E402

from .binding import LITE3_VELOCITY as BINDING  # noqa: E402
from .profile import LITE3_VELOCITY as PROFILE  # noqa: E402


def make_lite3_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Rough-terrain Lite3 velocity configuration (official reward recipe)."""
    return kit_velocity.make_env_cfg(BINDING, PROFILE, terrain_profile="rough", play=play)


def make_lite3_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground Lite3 velocity configuration."""
    return kit_velocity.make_env_cfg(BINDING, PROFILE, terrain_profile="flat", play=play)


def lite3_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground Lite3 velocity configuration（profile 声明的 env 入口）。"""
    return make_lite3_flat_env_cfg(play=play)


def lite3_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Rough-terrain Lite3 velocity configuration."""
    return make_lite3_rough_env_cfg(play=play)


def lite3_runner_cfg():
    """Official Lite3 PPO runner config —— **委托** `kits/quadruped_kit.ppo_runner_cfg`。"""
    return kit.ppo_runner_cfg("lite3_velocity")
