"""Go2 侧薄委托：族级 Trot 的不可变常量。

族级声明在 `.../quadruped_kit/skills/trot/profile.py`；本模块只填**机型身份**
（task_id / experiment_name），其余（周期、目标足高、帧数、PPO 超参）与源实现逐值相同。
"""

from __future__ import annotations

import sys
from pathlib import Path

for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.trot.profile import TrotProfile  # noqa: E402

TROT = TrotProfile(task_id="Unitree-Go2-Trot-Flat", experiment_name="go2_trot")
