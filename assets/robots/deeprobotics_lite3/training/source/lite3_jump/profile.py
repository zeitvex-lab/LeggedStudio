"""Deeprobotics Lite3 的 jump 技能 profile：机型身份。

技能级常量（周期、目标足高、帧数、PPO 超参）在族级声明
（`quadruped_kit/skills/jump/profile.py`），本模块只填与机型绑定的两项：
`task_id`（注册用的 mjlab 任务名）与 `experiment_name`（训练产物目录名）。

**未按 lite3 标定**：`base_height_target`（0.3 m）与 `target_foot_height` 是 go2 配方
的数（go2 站姿 0.42，lite3 站姿 0.3）—— lite3 上这两个目标相对偏高；能训 ≠ 训得好，
登记在 `registry/porting_references.json` 的 `lite3-jump` 条目里。
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

LITE3_JUMP = JumpProfile(task_id="Unitree-Lite3-Jump-Flat", experiment_name="lite3_jump")
