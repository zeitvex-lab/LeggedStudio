"""Unitree B2 velocity environment configurations（薄委托：族级 velocity 技能）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/velocity/`。本模块只剩三样 b2 事实：

1. **机型绑定** `B2_VELOCITY`（`binding.py`：契约 + `model/robot.xml` 真值 + 本机型训练实体）；
2. **任务数值与机型配方** `B2_VELOCITY`（`profile.py`：`VelocityProfile` + recipe）；
3. **入口函数**（公开名不动，profile 的 `entrypoints` 与冒烟/训练链照旧解析到这里）。

原先本文件里的接线（`kit.new_velocity_env_cfg` 装配骨架 + 两组接触传感器 + 非足端
终止 + 事件撤项 + 命令 viz/展厅档 + 姿态 std 表 + 足端 site 表）已上移：装配骨架与
族级机制在 Kit，机型专属那几样在 `profile.py` 的 recipe（同包数据面）。
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

from .binding import B2_VELOCITY as BINDING  # noqa: E402
from .profile import B2_VELOCITY as PROFILE  # noqa: E402


def make_b2_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Rough-terrain A2 velocity configuration."""
    return kit_velocity.make_env_cfg(
        BINDING, PROFILE, terrain_profile="rough", play=play
    )


def make_b2_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground A2 velocity configuration."""
    return kit_velocity.make_env_cfg(
        BINDING, PROFILE, terrain_profile="flat", play=play
    )


def b2_flat_env_cfg(*, play: bool = False):
    return make_b2_flat_env_cfg(play=play)


def b2_rough_env_cfg(*, play: bool = False):
    return make_b2_rough_env_cfg(play=play)


def b2_runner_cfg():
    return kit.ppo_runner_cfg("b2_velocity")


def make_b2_stairs_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """B2 台阶速度档（2026-10-01 stairs 全族化）：族级 velocity + stairs 地形档。"""
    return kit_velocity.make_env_cfg(BINDING, PROFILE, terrain_profile="stairs", play=play)
