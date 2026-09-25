"""B2 的 velocity 技能绑定（机型侧，薄委托）。

族级技能层（`adapters/mjlab/kits/quadruped_kit/skills/velocity/`）**不认识任何机型**：
它要一份"这台机型在速度跟踪任务里长什么样"的绑定。本模块就是 b2 的那一份 ——
全部字段从**契约**（`assets/robots/unitree_b2/contract.json`，v3）与 **MJCF 真值**
（`model/robot.xml`，本任务训练用的模型，经 `b2_velocity.robot_constants.get_spec`）派生：

* 关节序 / 默认姿 / 腿标记 → 契约；
* 执行器谱（`XmlActuatorCfg` 包装 MJCF 内置 `<position>`，**不重设** PD）→ 本机型实体；
* 足端几何 / 足端 site / 腿杆与躯干碰撞几何 / 根 body → MJCF 清单（`binding.py` 的技能层实现）；
* 出生高 → 本机型初始站姿高（`INIT_STATE.pos[2]`，与 `robot_constants` 同一处真值）。

**动作缩放口径**：本机型源配方（`B2_ACTION_SCALE`，见 `robot_constants`）是
`action_scale_from_actuators(articulation, 0.25)` —— **全 12 关节 0.25**；而契约的
`actuator_profile.by_role[*].action_scale` 是逐角色的 0.125（hip）/0.25/0.25
（与 `simulation/config.json` 的 `action_scale_by_joint` 一致）。两者冲突，且
`XmlActuatorCfg` 不带 `stiffness`/`effort_limit` ⇒ 技能层的比值恒 1.0 ⇒ 派生值 =
契约值（hip 0.125）。本档案在 profile 里**显式保留现行的 0.25 口径**
（`action_scale_by_role`），不静默改行为；冲突已登记进本轮报告（见 profile 注释）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 仓库根自举（与 go2 / go1 的 binding.py 同一约定）：worker / schema-dump / 冒烟三种运行
# 环境都只把 training/source（或包根）放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills import (  # noqa: E402
    QuadrupedSkillBinding,
    from_contract,
)

from .robot_constants import INIT_STATE, get_b2_robot_cfg  # noqa: E402


def contract_path() -> Path:
    """沿目录向上找本机型的 v3 契约（assets 源树与 workspace 副本都命中包根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 unitree_b2 的 contract.json（沿目录向上查找）")


def contract() -> dict:
    return json.loads(contract_path().read_text(encoding="utf-8-sig"))


B2_VELOCITY: QuadrupedSkillBinding = from_contract(
    contract(),
    spec_fn=get_b2_robot_cfg().spec_fn,
    base_entity_cfg=get_b2_robot_cfg,
    init_base_height=float(INIT_STATE.pos[2]),
)

__all__ = ["B2_VELOCITY", "contract", "contract_path"]
