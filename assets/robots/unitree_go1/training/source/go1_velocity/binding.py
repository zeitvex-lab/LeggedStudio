"""Go1 的 velocity 技能绑定（机型侧，薄委托）。

族级技能层（`adapters/mjlab/kits/quadruped_kit/skills/velocity/`）**不认识任何机型**：
它要一份"这台机型在速度跟踪任务里长什么样"的绑定。本模块就是 go1 的那一份 ——
全部字段从**契约**（`assets/robots/unitree_go1/contract.json`，v3）与 **MJCF 真值**
（`model/robot.xml`，本任务训练用的模型，经 `go1_velocity.robot_constants.get_spec`）派生。

## 本机型的两处能力/口径事实（都由数据表达，Kit 里没有机型判断）

* **没有足端 site**：go1 的 MJCF 只有 imu 一个 site（足端就是 calf 体）⇒
  `binding.has_foot_sites()` 为假，族级装配按**能力**撤掉足端高度扫描与四项依赖
  site 的奖励（`foot_clearance` / `foot_swing_height` / `soft_landing` / `foot_slip`）
  与三项足端观测 —— 与 go1 源配方的处置逐项同构；
* **动作缩放口径**：本机型源配方（`GO1_ACTION_SCALE`，HIMLoco 的 `control.action_scale`）
  与 `simulation/config.json` 的 `action_scale_by_joint` 都是**实际缩放 0.25**（全 12 关节），
  不是"归一化值 × 实体 effort/stiffness"（那会给 0.25 × 23.7/40 = 0.148）。
  故 profile 用 `action_scale_by_role` 显式给 0.25，保持与部署声明一致。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 仓库根自举（与 go2 / b2 的 binding.py 同一约定）。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills import (  # noqa: E402
    QuadrupedSkillBinding,
    from_contract,
)

from .robot_constants import INIT_STATE, get_go1_robot_cfg  # noqa: E402


def contract_path() -> Path:
    """沿目录向上找本机型的 v3 契约（assets 源树与 workspace 副本都命中包根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 unitree_go1 的 contract.json（沿目录向上查找）")


def contract() -> dict:
    return json.loads(contract_path().read_text(encoding="utf-8-sig"))


GO1_VELOCITY: QuadrupedSkillBinding = from_contract(
    contract(),
    spec_fn=get_go1_robot_cfg().spec_fn,
    base_entity_cfg=get_go1_robot_cfg,
    init_base_height=float(INIT_STATE.pos[2]),
)

__all__ = ["GO1_VELOCITY", "contract", "contract_path"]
