"""Unitree Go1 的 AMP profile：机型身份（族级 imitation 技能）。

技能级常量（判别器容量、专家预载量、奖励系数、动作加载时间步）在族级声明
（`quadruped_kit/skills/imitation/profile.py`），本模块只填与 go1 绑定的两项：
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

from adapters.mjlab.kits.quadruped_kit.skills.imitation.profile import (  # noqa: E402
    AmpProfile,
)

GO1_AMP = AmpProfile(task_id="Unitree-Go1-AMP-Rough", experiment_name="go1_amp")
