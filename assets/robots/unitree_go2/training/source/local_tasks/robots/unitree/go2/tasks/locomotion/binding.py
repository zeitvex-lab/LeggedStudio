"""Go2 的 velocity 技能绑定（机型侧，薄委托）。

族级技能层（`adapters/mjlab/kits/quadruped_kit/skills/velocity/`）**不认识任何机型**：
它要一份"这台机型在速度跟踪任务里长什么样"的绑定。本模块就是 go2 的那一份 ——
全部字段从**契约**（`assets/robots/unitree_go2/contract.json`，v3）与 **MJCF 真值**
（`model/training.xml`，就是本任务训练用的模型，经 `local_tasks.mjlab_extension`）派生。

与 `go2_skills/binding.py`（特技/模仿用的那份）**刻意分开**（同 parkour 的先例）：
两者取自不同的上游树（`go2_skills/upstream/.../xmls/go2.xml` vs `model/training.xml`），
实例参数也不同 —— 速度跟踪任务的实体整份来自本机型自己的 `get_go2_robot_cfg()`
（BuiltinPosition 执行器、`training.xml` 的碰撞/初始姿），技能层不做任何覆盖；
而 `go2_skills` 那份带 `armature_override=0.0` / `init_base_height=0.42` 这类**特技配方**
参数，对速度跟踪不适用，混用会让"velocity 的实体是什么"变得不可读。

## 只有一处"源配方参数"

`init_base_height` —— 出生高，契约里没有这一项（不是机型常量，是任务参数）。
本技能不使用 `binding.robot_cfg()`（实体整份由机型侧给），此值只为满足绑定构造，
故取本机型训练模型自己的初始站姿高（`mjlab_extension.INIT_STATE.pos[2]`），不另立第二个数。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 仓库根自举（与 go2_skills/binding.py / parkour/binding.py 同一约定）。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills import (  # noqa: E402
    QuadrupedSkillBinding,
    from_contract,
)

from local_tasks.mjlab_extension import INIT_STATE, get_go2_robot_cfg  # noqa: E402


def contract_path() -> Path:
    """沿目录向上找本机型的 v3 契约（assets 源树与 workspace 副本都命中包根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 unitree_go2 的 contract.json（沿目录向上查找）")


def contract() -> dict:
    return json.loads(contract_path().read_text(encoding="utf-8-sig"))


GO2_VELOCITY: QuadrupedSkillBinding = from_contract(
    contract(),
    spec_fn=get_go2_robot_cfg().spec_fn,
    base_entity_cfg=get_go2_robot_cfg,
    init_base_height=float(INIT_STATE.pos[2]),
)
