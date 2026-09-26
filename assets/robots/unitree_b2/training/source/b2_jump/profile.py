"""跳跃（jump）（族级 `JumpProfile` 的 b2 实例）。

## 这份数据从哪来

本仓**没有 b2 专属的跳跃上游**（该技能的上游是 `00_resources` 里 Gym 包的
go2 配方）。所以本表是**同一份配方**：族级 `JumpProfile` 的默认值即源配方数值，b2 侧
**只换机型身份**，与 `b2-wtw` / `b2-backflip` 同一纪律。


## 别把"能训"当成"训得好" —— 未按 b2 标定

配方里的**高度类目标**（`base_height_target` / 目标足高）与**接触力/速度阈值**是
go2 几何（站姿 0.42 m）与质量量级下的数，b2 站姿 0.54 m 且重一档 ⇒ **未标定**；
能训 ≠ 训得好。

登记在 `registry/porting_references.json` 的 `b2-jump` 条目里。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（与 b2_velocity/binding.py 同一约定）：worker / schema-dump / 冒烟三种运行
# 环境都只把 training/source 或包根放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.jump.profile import JumpProfile  # noqa: E402

JUMP = JumpProfile(
    task_id="Unitree-B2-Jump-Flat",
    experiment_name="b2_jump",
)
