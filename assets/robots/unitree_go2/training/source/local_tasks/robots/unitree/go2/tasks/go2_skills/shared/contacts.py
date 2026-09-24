"""Go2 侧薄委托：族级接触/步态原语 + 本机型的关节序/足端视图。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/mdp/contacts.py`；
本模块只做两件事：

1. 把 go2 的绑定（契约关节序 / 契约腿序足端）绑上去，保留包内原有符号
   （`JOINT_NAMES` / `SOURCE_FOOT_GEOMS` / `joint_ids(robot)` / `source_contact(sensor, thr)`）——
   包内**未上移**的技能（backflip / dreamwaq / amp_dreamwaq / 姿态类）继续按老签名调用；
2. 一字不改地转出与机型无关的原语（phase / stance_mask / root_euler / phase_command）。

`JOINT_NAMES` 的值来自契约 `action.joint_order`（不再手抄 12 个名字）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.mdp import contacts as _kit_contacts

from ..binding import GO2

JOINT_NAMES = GO2.joint_order
SOURCE_FOOT_GEOMS = GO2.foot_geoms

phase = _kit_contacts.phase
stance_mask = _kit_contacts.stance_mask
root_euler = _kit_contacts.root_euler
phase_command = _kit_contacts.phase_command


def joint_ids(robot) -> list[int]:
    """按契约关节序解析关节 id（签名保持包内旧口径：收实体）。"""
    return _kit_contacts.joint_ids_named(robot, JOINT_NAMES)


def source_contact(sensor, threshold: float):
    return _kit_contacts.source_contact(sensor, threshold)


def source_vertical_contact(sensor, threshold: float):
    return _kit_contacts.source_vertical_contact(sensor, threshold)
