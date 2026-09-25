"""Unitree B2-W velocity environment configurations（族级实现 + 本机型数据）。

技能上移（2026-09-25）：本模块原先是 333 行的手写装配（与 go2w 的同名文件
**逐字节同文**的移植副本）；现为**薄委托** —— 族级实现在
`adapters/mjlab/kits/wheel_leg_kit/skills/velocity/`，这里只把 b2w 的绑定
（`binding.B2W`）与四档 profile 数据（`profile.py`）接上去。
**公开函数名沿用源实现**（profile 档案 `b2w-velocity` 与 `traversal_env_cfg`
按原名引用：`unitree_go2w_*` 是移植时留下的命名，改名会牵动档案与越障入口）。

四个变体是**同一份族级实现**的具名分支（结构差异在 Kit，数值差异在 profile）：

| 入口 | 变体 | 地形 | 动作 |
|---|---|---|---|
| `unitree_go2w_rough_env_cfg` | `rough` | 生成器 + 地形课程 | 腿位置 + 轮速度 |
| `unitree_go2w_flat_env_cfg` | `flat` | 平面 | 腿位置 + 轮速度 |
| `unitree_go2w_flat_legs_only_env_cfg` | `flat_legs_only` | 平面 | 仅腿位置 |
| `unitree_go2w_flat_legs_only_omni_env_cfg` | `flat_legs_only_omni` | 平面 | 仅腿位置（全向命令） |

`b2w_traversal_env_cfg`（越障档案）仍按名调用本模块的 `unitree_go2w_rough_env_cfg`
作机器人侧基座，课程侧取族级越障工厂 —— 本模块的公开面因此一个字都没动。
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
from .binding import B2W  # noqa: E402


def unitree_go2w_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Create the supported rough-terrain hybrid B2-W velocity config."""
  return make_velocity_env_cfg(B2W, _profiles.ROUGH, variant="rough", play=play)


def unitree_go2w_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Create the supported flat-terrain hybrid B2-W velocity config."""
  return make_velocity_env_cfg(B2W, _profiles.FLAT, variant="flat", play=play)


def unitree_go2w_flat_legs_only_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Create the supported flat legs-only B2-W walking config."""
  return make_velocity_env_cfg(
    B2W, _profiles.LEGS_ONLY, variant="flat_legs_only", play=play
  )


def unitree_go2w_flat_legs_only_omni_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Create the supported omni-directional flat B2-W legs-only config."""
  return make_velocity_env_cfg(
    B2W, _profiles.OMNI, variant="flat_legs_only_omni", play=play
  )
