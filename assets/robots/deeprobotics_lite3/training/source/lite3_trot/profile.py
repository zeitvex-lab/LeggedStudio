"""Unitree Lite3 的 小跑步态（trot） 技能 profile：机型身份。

技能级常量（周期、目标足高、帧数、PPO 超参）在族级声明
（`quadruped_kit/skills/trot/profile.py`），本模块只填与机型绑定的两项：
`task_id`（注册用的 mjlab 任务名）与 `experiment_name`（训练产物目录名）。

## 初始姿与源配方相同（少一层机型侧改动）

go2 的 trot 源配方要 `with_pose_roles` 覆写初始姿（髋归零 + 四腿同姿 0.8 / -1.5）；
lite3 的契约 `joints.default_pose` **本来就是这一组** ⇒ 直接沿用契约姿态，不需要覆写。

## 别把"能训"当成"训得好" —— 未按本机型标定

`base_height_target`（0.29 m）与目标足高是 go2 几何（站姿 0.42 m）下的数，
lite3 站姿 0.3 m ⇒ **未标定**；能训 ≠ 训得好。
登记在 `registry/porting_references.json` 的 `lite3-trot` 条目里。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（与 lite3_velocity 同一约定）：worker / schema-dump / 冒烟三种运行环境都只把
# training/source 或包根放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.trot.profile import TrotProfile  # noqa: E402

TROT = TrotProfile(
    task_id="Unitree-Lite3-Trot-Flat",
    experiment_name="lite3_trot",
)
