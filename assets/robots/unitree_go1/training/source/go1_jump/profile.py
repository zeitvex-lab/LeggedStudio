"""Unitree Go1 的 jump 技能 profile：机型身份。

技能级常量（周期、目标足高、帧数、PPO 超参）在族级声明
（`quadruped_kit/skills/jump/profile.py`），本模块只填与机型绑定的两项：
`task_id`（注册用的 mjlab 任务名）与 `experiment_name`（训练产物目录名）。
"""

from __future__ import annotations

import sys
from pathlib import Path

for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.jump.profile import JumpProfile  # noqa: E402

GO1_JUMP = JumpProfile(task_id="Unitree-Go1-Jump-Flat", experiment_name="go1_jump")
