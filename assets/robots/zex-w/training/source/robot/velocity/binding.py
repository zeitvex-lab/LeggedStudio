"""ZEX-W 的族级技能绑定（机型侧，薄委托）。

族级技能层（`adapters/mjlab/kits/wheel_leg_kit/skills/`）**不认识任何机型**：
它要一份"这台机型在族技能里长什么样"的绑定，本模块就是 zex-w 的那一份 —— 全部字段
从**契约**（`assets/robots/zex-w/contract.json`）与 **MJCF 真值**（`training/source/mjcf/
wheelleg.xml`，经 `spec_utils.normalize_for_training` 规范化）派生：

* 腿 / 轮关节序（= 契约 `action.joint_order`，也是本包训练与导出产物的接口序）、
  控制模式、PD 谱与 armature → 契约 `actuator_profile.by_role`；
* 默认姿（`.*_hip_pitch_joint` 0.55 / `.*_knee_joint` -1.125 / 髋外展 0） → 契约
  `joints.default_pose`（与本体 `robot_cfg.INIT_STATE` 的字面值一致，无登记偏离）；
* 根 body（`base_link`）→ MJCF worldbody 的第一个子 body；
* 轮-地接触主匹配 → 族声明的轮角色别名 + 通用足端 token（`.*(fl|fr|rl|rr)_(wheel|foot).*`）；
* 出生高 → 源配方任务级参数（`profile.FLAT.init_base_height` = 0.42）。

唯一"机型侧额外事实"是**基座实体配置**（MJCF 来源 + 碰撞方案 + 柔性限位系数，见
`robot_cfg.get_robot_cfg()`）—— 族级绑定只在它之上覆盖"出生高 / 默认姿 / 执行器谱"三项。
**crawl 档不用这份绑定**：它有自己的实体配置（`get_robot_crawl_cfg`，趴姿出生）与
自己的装配（`config/env_cfgs.py::crawl_env_cfg`），是另一条任务。
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

from ..robot_cfg import get_robot_cfg, get_spec  # noqa: E402
from .profile import FLAT  # noqa: E402


def contract_path() -> Path:
    """沿目录向上找本机型的契约（assets 源树与 workspace 副本都命中包根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 zex-w 的 contract.json（沿目录向上查找）")


def contract() -> dict:
    return json.loads(contract_path().read_text(encoding="utf-8-sig"))


#: 本机型在族级 velocity 技能里的绑定（契约 + MJCF 派生；默认姿与缩放无登记偏离）。
ZEXW: WheelLegSkillBinding = from_contract(
    contract(),
    spec_fn=get_spec,
    base_entity_cfg=get_robot_cfg,
    init_base_height=FLAT.init_base_height,
)
