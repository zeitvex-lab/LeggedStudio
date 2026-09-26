"""弹簧跳（spring_jump）（族级 `SpringJumpProfile` 的 b2 实例）。

## 这份数据从哪来

本仓**没有 b2 专属的弹簧跳上游**（该技能的上游是 `00_resources` 里 Gym 包的
go2 配方）。所以本表是**同一份配方**：族级 `SpringJumpProfile` 的默认值即源配方数值，b2 侧
**只换机型身份**，与 `b2-wtw` / `b2-backflip` 同一纪律。

本技能**需要足端 site**（`binding.foot_sites()`）；b2 的 MJCF 有 `FL/FR/RL/RR`
四个足端 site ⇒ 无能力缺口（与 go1/lite3 不同，它们在这项技能上是缺口）。

## 别把"能训"当成"训得好" —— 未按 b2 标定

配方里的**高度类目标**（`base_height_target` / 目标足高）与**接触力/速度阈值**是
go2 几何（站姿 0.42 m）与质量量级下的数，b2 站姿 0.54 m 且重一档 ⇒ **未标定**；
能训 ≠ 训得好。

登记在 `registry/porting_references.json` 的 `b2-spring-jump` 条目里。
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

from adapters.mjlab.kits.quadruped_kit.skills.spring_jump.profile import SpringJumpProfile  # noqa: E402

SPRING_JUMP = SpringJumpProfile(
    task_id="Unitree-B2-Spring-Jump-Flat",
    experiment_name="b2_spring_jump",
)
