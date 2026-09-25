"""Lite3 的 velocity 技能绑定（机型侧，薄委托）。

族级技能层（`adapters/mjlab/kits/quadruped_kit/skills/velocity/`）**不认识任何机型**：
它要一份"这台机型在速度跟踪任务里长什么样"的绑定。本模块就是 lite3 的那一份 ——
全部字段从**契约**（`assets/robots/deeprobotics_lite3/contract.json`，v3）与 **MJCF 真值**
（`model/robot.xml`，本任务训练用的模型，经 `lite3_velocity.robot_constants.get_spec`）派生。

## 本机型的三处事实（都由数据表达，Kit 里没有机型判断）

* **执行器：MJCF 为准**（`actuator_binding = mjcf_wrapped`，族声明的默认口径）——
  `model/robot.xml` 自带 12 个 `<position>`（kp=30 / kv=1 / forcerange ±30），
  `robot_constants` 的 `XmlActuatorCfg` 只包装不重设；族级 velocity 直接用本机型自己的
  基座实体（`base_entity_cfg`），PD 谱因此来自 MJCF（与 b2 同一情形）。
* **动作缩放口径**：本机型源配方（`LITE3_ACTION_SCALE` = 契约逐角色
  0.125 / 0.25 / 0.25）与契约 `actuator_profile.by_role[*].action_scale` **一致**；
  `XmlActuatorCfg` 不带 `stiffness`/`effort_limit` ⇒ 技能层的比值恒 1.0 ⇒
  `action_scale_by_joint()` 派生值 = 契约值 = 源配方表（与 b2 的冲突情形不同：b2 源配方
  全关节 0.25 与契约逐角色值不一致，需 profile 显式覆盖；lite3 无需覆盖，见 profile）。
* **足端帧**：MJCF 没有足端 site（site 只有 `imu_site` / `TORSO_site`），足端是
  `<LR>_FOOT` **body**（B31 裁决）⇒ `foot_scan_frames()` 回退到 body 帧
  （`("body", "FL_FOOT")` 一类），足端高度扫描照装配；接触/滑移类奖励按**足端body**
  （`<LR>_SHANK` 的接触面）取，见 profile 的 recipe。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 仓库根自举（与 go1 / b2 的 binding.py 同一约定）：worker / schema-dump / 冒烟三种运行
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

from .robot_constants import INIT_STATE, get_lite3_robot_cfg  # noqa: E402


def contract_path() -> Path:
    """沿目录向上找本机型的 v3 契约（assets 源树与 workspace 副本都命中包根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 deeprobotics_lite3 的 contract.json（沿目录向上查找）")


def contract() -> dict:
    return json.loads(contract_path().read_text(encoding="utf-8-sig"))


LITE3_VELOCITY: QuadrupedSkillBinding = from_contract(
    contract(),
    spec_fn=get_lite3_robot_cfg().spec_fn,
    base_entity_cfg=get_lite3_robot_cfg,
    init_base_height=float(INIT_STATE.pos[2]),
)

__all__ = ["LITE3_VELOCITY", "contract", "contract_path"]
