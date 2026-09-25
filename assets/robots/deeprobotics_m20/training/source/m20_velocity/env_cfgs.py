"""DeepRobotics M20 velocity environment configurations（族级实现 + 本机型数据）。

技能上移（2026-09-25）：本模块原先是 328 行的手写装配；现为**薄委托** ——
族级实现在 `adapters/mjlab/kits/wheel_leg_kit/skills/velocity/official.py`
（该机型的源配方是**官方（上游）配方**，与 reference 配方不是同一份任务：
观测布局与 21 项奖励表都不同，故族 Kit 里是第二个配方分支），这里只把 m20 的
绑定（`binding.M20`）与配方数据（`profile.OFFICIAL`）接上去。
公开函数名与签名不变（profile 档案与包 `__init__` 按名引用）。

| 入口 | 变体 | 地形 |
|---|---|---|
| `m20_rough_env_cfg` | `official_rough` | 生成器 + 地形课程 |
| `m20_flat_env_cfg` | `official_flat` | 平面（profile 档案 `m20-velocity` 的入口） |

上游口径与既有简化（与上移前注释一致）：57 维 rl_sdk 观测布局、21 项奖励表、
阈值速度命令（小线性命令归零）、动作 = 12 腿位置（hipx 0.125 / hipy·knee 0.25）
+ 4 轮速度（缩放 5.0，全部来自契约 `actuator_profile.by_role`）；对称 actor/critic
（上游那份 critic 多的 187 点高度扫描与机身线速度未移植）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（见 kits/wheel_leg_kit 模块注释）：worker / schema-dump / 冒烟三种
# 运行环境都只把 training/source 或包根放进 sys.path；沿目录向上找 adapters/mjlab
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from mjlab.envs import ManagerBasedRlEnvCfg  # noqa: E402

from adapters.mjlab.kits.wheel_leg_kit.skills import (  # noqa: E402
    make_velocity_env_cfg,
)

from . import profile as _profiles  # noqa: E402
from .binding import M20  # noqa: E402
from .rl_cfg import (  # noqa: E402, F401
    m20_ppo_runner_cfg,
    m20_rough_finetune_ppo_runner_cfg,
    m20_rough_ppo_runner_cfg,
)


def m20_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """M20 rough-terrain velocity configuration (official reward recipe)."""
    return make_velocity_env_cfg(
        M20, _profiles.OFFICIAL, variant="official_rough", play=play
    )


def m20_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """M20 flat-ground variant: plane terrain, no height scan / terrain curriculum."""
    return make_velocity_env_cfg(
        M20, _profiles.OFFICIAL, variant="official_flat", play=play
    )
