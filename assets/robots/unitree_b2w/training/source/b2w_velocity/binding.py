"""Unitree B2-W 的族级技能绑定（机型侧，薄委托）。

族级技能层（`adapters/mjlab/kits/wheel_leg_kit/skills/`）**不认识任何机型**：
它要一份"这台机型在族技能里长什么样"的绑定，本模块就是 b2w 的那一份 —— 全部字段
从**契约**（`assets/robots/unitree_b2w/contract.json`）与 **MJCF 真值**
（`model/robot.xml`）派生：

* 腿/轮关节序（= 契约 `action.joint_order`，也是本包训练/导出产物的接口序）、
  控制模式、PD 谱 → 契约；
* 根 body → MJCF；执行器声明归属 = `mjcf_wrapped`（MJCF 自带 `<actuator>` 段）；
* 轮-地接触主匹配 → 族声明的轮角色别名 + 通用足端 token；
* 出生高 → 源配方任务级参数（`profile.ROUGH.init_base_height`）。

唯一"机型侧额外事实"是**基座实体配置**（MJCF 来源 + 碰撞 + 柔性限位系数，见
`b2w_constants.py`）—— 族级绑定只在它之上覆盖"出生高 / 默认姿 / 执行器谱"三项。

## 两处登记的契约偏离（2026-09-25 随族级上移发现；行为按**原值**保留）

本机型的契约是按 **robot_lab 基线**填的，而本包训练真值是**按 go2w 模式移植**的
（档案 `b2w-velocity` 的 registry 结论即 `intentional`：go2w 配方，非 robot_lab 口径）。
两处因此对不上，上移口径是**纯搬运**（数值一处不改），故把它们显式登记在机型侧：

| 项 | 本包训练真值（上移前一直在跑） | 契约声明（= robot_lab 基线） |
|---|---|---|
| 默认姿 | `b2w_constants.INIT_STATE`：髋 FR/RR +0.1、FL/RL −0.1；大腿四腿 0.8；小腿 −1.5 | 髋全 0.0；大腿前腿 0.5 / 后腿 0.8；小腿 −1.5 |
| 动作缩放 | 腿 0.5（统一）/ 轮 35.0（go2w 模式） | 髋 0.125 / 大腿 0.25 / 小腿 0.25 / 轮 5.0 |
| 轮几何（奖励用） | `wheel_radius 0.09 / wheel_track 0.19`（见 `profile.py` 的 F7 注释） | —（契约不声明；MJCF 真值 ≈0.113 / 0.383） |

契约侧的机器人事实（`simulation/config.json`）两份策略各执一词：
policies[0] `b2w-velocity-robotlab` 与契约一致（0.125/0.25/5.0），
policies[1] `unitree_b2w-trained-20260918-093241`（**本包自有导出产物**）
与训练真值一致（腿 0.5 / 轮 35.0）。默认姿同时是位置动作的 `use_default_offset` 基准、
动作缩放直接决定动作语义 —— 换任何一项都等于改行为，故本模块把训练真值显式传给族 Kit
（`default_pose=` / `action_scale_override=`），**不动契约**；取哪一份由档案所有者裁决，
裁决后删掉对应参数即可回到"契约唯一真值"。
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

from .b2w_constants import get_b2w_base_entity_cfg, get_spec  # noqa: E402
from .profile import ROUGH  # noqa: E402

_LEGS = ("FR", "FL", "RR", "RL")
_LEG_SEGMENTS = ("hip", "thigh", "calf")
#: 前左 / 后左的髋角为负（其余腿为正）—— 上移前 `INIT_STATE` 的字面值口径。
_NEGATIVE_HIP_LEGS = ("FL", "RL")
#: 大腿 / 小腿的训练真值姿态角（上移前 `INIT_STATE` 四腿同值）。
_SEGMENT_POSE = {"thigh": 0.8, "calf": -1.5}


def contract_path() -> Path:
    """沿目录向上找本机型的契约（assets 源树与 workspace 副本都命中包根）。"""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "contract.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("找不到 unitree_b2w 的 contract.json（沿目录向上查找）")


def contract() -> dict:
    return json.loads(contract_path().read_text(encoding="utf-8-sig"))


#: 训练真值默认姿 = 上移前的 `b2w_constants.INIT_STATE.joint_pos`（字面值原样搬运）。
_TRAINING_DEFAULT_POSE: dict[str, float] = {
    **{
        f"{leg}_{seg}_joint": (
            (-0.1 if leg in _NEGATIVE_HIP_LEGS else 0.1)
            if seg == "hip"
            else _SEGMENT_POSE[seg]
        )
        for leg in _LEGS
        for seg in _LEG_SEGMENTS
    },
    **{f"{leg}_wheel_joint": 0.0 for leg in _LEGS},
}

#: 训练真值动作缩放 = 上移前 `env_cfgs.py` 的 go2w 模式字面值（腿统一 0.5、轮 35.0）。
_TRAINING_ACTION_SCALES: dict[str, float] = {
    **{f"{leg}_{seg}_joint": 0.5 for leg in _LEGS for seg in _LEG_SEGMENTS},
    **{f"{leg}_wheel_joint": 35.0 for leg in _LEGS},
}

B2W: WheelLegSkillBinding = from_contract(
    contract(),
    spec_fn=get_spec,
    base_entity_cfg=get_b2w_base_entity_cfg,
    init_base_height=ROUGH.init_base_height,
    # MJCF 自带执行器（资产真值）：cfg 只包装、不重复注册（见 b2w_constants.py 的说明）。
    actuator_binding="mjcf_wrapped",
    default_pose=_TRAINING_DEFAULT_POSE,
    action_scale_override=_TRAINING_ACTION_SCALES,
)
