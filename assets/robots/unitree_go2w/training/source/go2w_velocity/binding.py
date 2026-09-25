"""Go2-W 的族级技能绑定（机型侧，薄委托）。

族级技能层（`adapters/mjlab/kits/wheel_leg_kit/skills/`）**不认识任何机型**：
它要一份"这台机型在族技能里长什么样"的绑定，本模块就是 go2w 的那一份 —— 全部字段
从**契约**（`assets/robots/unitree_go2w/contract.json`，v3）与 **MJCF 真值**
（`training/source/go2w_velocity/xmls/go2w.xml`，就是训练模型本身）派生：

* 腿/轮关节序、动作缩放、控制模式（position/velocity）、默认姿、PD 谱 → 契约；
* 根 body（worldbody 第一个子 body）→ MJCF；
* 轮-地接触主匹配 → 族声明的轮角色别名 + 通用足端 token；
* 出生高 → 源配方任务级参数（契约无此字段），取自 `profile.ROUGH.init_base_height`。

唯一"机型侧额外事实"是**基座实体配置**（MJCF 来源 + 碰撞 + 柔性限位系数，见
`go2w_constants.py`）——族级绑定只在它之上覆盖"出生高 / 默认姿 / 执行器谱"三项。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 仓库根自举（与包内 stub / 族 Kit 同一约定）：worker 只把包根与 training/source
# 放进 sys.path，不保证仓库根在场；沿目录向上找 adapters/mjlab 对 assets 源树与
# workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.wheel_leg_kit.skills import (  # noqa: E402
    WheelLegSkillBinding,
    from_contract,
)

from .go2w_constants import get_go2w_base_entity_cfg, get_spec  # noqa: E402
from .profile import ROUGH  # noqa: E402


def contract_path() -> Path:
    """沿目录向上找本机型的 v3 契约（assets 源树与 workspace 副本都命中包根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 unitree_go2w 的 contract.json（沿目录向上查找）")


def contract() -> dict:
    return json.loads(contract_path().read_text(encoding="utf-8-sig"))


GO2W: WheelLegSkillBinding = from_contract(
    contract(),
    spec_fn=get_spec,
    base_entity_cfg=get_go2w_base_entity_cfg,
    init_base_height=ROUGH.init_base_height,
)
