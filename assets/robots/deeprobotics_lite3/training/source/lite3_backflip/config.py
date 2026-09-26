"""Deeprobotics Lite3 的后空翻入口（薄委托：族级特技技能 + lite3 绑定）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/backflip/`。本模块只给两样 lite3 事实：

1. **机型绑定** `LITE3_VELOCITY`（复用 `lite3_velocity.binding`：契约 + 包内 MJCF 真值 +
   本机型训练实体）—— 与 `lite3-velocity` / `lite3-jump` 同一份绑定；
2. **任务数值** `BACKFLIP`（`backflip/profile.py`：机型身份；配方数值沿用族级默认值）。

**Kit 未改一行**：lite3 与 go2 的差异全部由绑定派生吸收 —— 契约角色词（`hipx/hipy/knee`）
与 body 词表（`*_HIP/THIGH/SHANK/FOOT`）**没有共同 token**，腿杆惩罚因此按**结构**派生
（腿身 body 去掉髋外展与足端 ⇒ `THIGH + SHANK`）；执行器走 MJCF 包装；腿标记含 H 后腿
（右腿仍是 1/3）；无足端 site 不影响后空翻（只用足端几何名与本体高度）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

# 仓库根自举（与 lite3_velocity 同一约定）。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills import backflip as kit_backflip  # noqa: E402

from lite3_velocity.binding import LITE3_VELOCITY  # noqa: E402

from .profile import BACKFLIP  # noqa: E402


def make_lite3_backflip_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    """族级后空翻技能 + lite3 绑定（入口签名与族级工厂一致）。"""
    return kit_backflip.make_env_cfg(LITE3_VELOCITY, BACKFLIP, play=play)


def lite3_backflip_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return make_lite3_backflip_env_cfg(play=play)


def lite3_backflip_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    return kit_backflip.make_runner_cfg(BACKFLIP)
