"""Go2 的族级技能绑定（机型侧，薄委托）。

族级技能层（`adapters/mjlab/kits/quadruped_kit/skills/`）**不认识任何机型**：
它要一份"这台机型在族技能里长什么样"的绑定，本模块就是 go2 的那一份 ——
全部字段从**契约**（`assets/robots/unitree_go2/contract.json`，v3）与 **MJCF 真值**
（`upstream/assets/robots/unitree_go2/xmls/go2.xml`，就是训练模型本身）派生。

## 只有两处"源配方参数"，且都在此取证

1. `init_base_height=0.42` —— 出生高。契约里没有这一项（它不是机型常量，是任务参数），
   源配方 `jump_robot_cfg` 取该机型站姿高 0.42；
2. `armature_override=0.0` —— **源配方的刻意偏离**：`jump_robot_cfg` 的 IdealPd 显式写
   `armature=0.0`，而契约 `actuator_profile` 声明的是髋/大腿 0.01、小腿 0.02。
   为保持**迁移前后行为等价**（迁移的硬要求），这里按源配方取值；
   是否把契约改成 0.0（真值归位）属单独裁决，不在本次迁移内 —— 登记在案，不静默改物理。

其余（关节名与序、默认姿、PD/力矩、足端几何、根 body、腿标记、惩罚几何词表）
一律契约/MJCF 派生。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 仓库根自举（与 go1 env_cfg / quadruped_kit 同一约定）：worker 只把包根与
# training/source 放进 sys.path，不保证仓库根在场；沿目录向上找 adapters/mjlab
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills import (  # noqa: E402
    QuadrupedSkillBinding,
    from_contract,
)

from .upstream.assets.robots import get_go2_robot_cfg  # noqa: E402

#: 源配方（`go2_skills/shared/robot.py`）的出生高，见模块 docstring 第 1 条。
INIT_BASE_HEIGHT = 0.42
#: 源配方的 IdealPd armature，见模块 docstring 第 2 条。
SOURCE_PARITY_ARMATURE = 0.0


def contract_path() -> Path:
    """沿目录向上找本机型的 v3 契约（assets 源树与 workspace 副本都命中包根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 unitree_go2 的 contract.json（沿目录向上查找）")


def contract() -> dict:
    return json.loads(contract_path().read_text(encoding="utf-8-sig"))


GO2: QuadrupedSkillBinding = from_contract(
    contract(),
    spec_fn=get_go2_robot_cfg().spec_fn,
    base_entity_cfg=get_go2_robot_cfg,
    init_base_height=INIT_BASE_HEIGHT,
    armature_override=SOURCE_PARITY_ARMATURE,
)

#: trot 源配方的初始姿态（角色 → 角）：**与契约 default_pose 不同**——
#: 契约声明的是非对称站姿（jump 用它），而 trot 源用"髋归零 + 四腿同姿"。
#: 属源配方姿态，故由机型侧显式给出（见 `binding.with_pose_roles`）。
GO2_TROT_STANCE = {"hip": 0.0, "thigh": 0.8, "calf": -1.5}

GO2_TROT: QuadrupedSkillBinding = GO2.with_pose_roles(GO2_TROT_STANCE)
