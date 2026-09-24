"""越障技能装配用的族级解析：绑定 + 配方 → 装配要的形状。

三件事，全部**声明驱动**（本模块不含任何机型名与机型数值）：

1. **足端槽位序**：配方常量（`profile.foot_slot_order`）必须是本机型腿标记
   （`binding.leg_ids`，契约 `morphology.leg_ids`）的一个排列 —— 不是就报错。
   为什么要校验而不是"直接照抄"：换序会改变接触/射线张量的槽位含义（步态相位、足端奖励）
   与源配方不再等价；把它钉成"排列"这条判据，同族机型复用才安全。
2. **足端几何 / 足端帧**：几何名走 `binding.foot_geoms`（契约腿序、MJCF 派生），
   射线帧优先用与腿同名的 site（源配方就这么取），没有 site 的机型回退到该腿的足端几何 ——
   语义同在足端，且不需要改 MJCF。
3. **配方级关节限位**：把族角色 `hip_pitch`（大腿）关节的限位**上界**收到配方值，
   下界保留 MJCF 真值（不改物理，只排除"反关节支路"这一机械可达但不可用的分支）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import mujoco
from mjlab.sensor import ObjRef

from .. import family as family_roles
from ..binding import QuadrupedSkillBinding
from .profile import ParkourProfile

#: 族角色：大腿（别名表见 `registry/families/<族>.json`）。
THIGH_ROLE = "hip_pitch"


def foot_slot_order(
    binding: QuadrupedSkillBinding, profile: ParkourProfile
) -> tuple[str, ...]:
    """足端槽位序（校验为腿标记的一个排列；不是就报错，不静默换序）。"""
    order = tuple(str(leg) for leg in profile.foot_slot_order)
    legs = tuple(str(leg) for leg in binding.leg_ids)
    if sorted(order) != sorted(legs):
        raise ValueError(
            f"{binding.robot_id}: 配方足端槽位序 {order} 不是本机型腿标记 {legs} 的一个排列 —— "
            "换序会改变接触/射线槽位语义（步态相位、足端奖励），需要单独裁决后更新配方"
        )
    return order


def foot_geom_by_leg(binding: QuadrupedSkillBinding) -> dict[str, str]:
    """腿标记 → 足端几何名（几何名来自契约腿序的 MJCF 派生结果）。"""
    legs = tuple(str(leg) for leg in binding.leg_ids)
    geoms = tuple(str(name) for name in binding.foot_geoms)
    if len(legs) != len(geoms):
        raise ValueError(
            f"{binding.robot_id}: 腿标记 {legs} 与足端几何 {geoms} 不等长，绑定自相矛盾"
        )
    return dict(zip(legs, geoms, strict=True))


def foot_ray_frames(
    binding: QuadrupedSkillBinding,
    profile: ParkourProfile,
    spec: mujoco.MjSpec,
) -> tuple[tuple[str, ObjRef], ...]:
    """足端射线传感器（名, 帧），按配方槽位序；site 优先、足端几何回退。"""
    order = foot_slot_order(binding, profile)
    geoms = foot_geom_by_leg(binding)
    sites = {str(site.name) for site in spec.sites}
    frames: list[tuple[str, ObjRef]] = []
    for leg in order:
        if leg in sites:
            ref = ObjRef(type="site", name=leg, entity="robot")
        else:
            ref = ObjRef(type="geom", name=geoms[leg], entity="robot")
        frames.append((f"{leg}_foot_ray", ref))
    return tuple(frames)


def foot_site_names(
    binding: QuadrupedSkillBinding, profile: ParkourProfile, spec: mujoco.MjSpec
) -> tuple[str, ...]:
    """足端 site 名（按配方槽位序）；缺 site 的机型在这里 fail-closed。

    用途：按足端反力的支撑判定与滑移惩罚需要"足端的速度/位置"这类 site 专有量，
    几何回退给不出（源配方口径），故缺失就是能力缺失，报错而不是换口径。
    """
    order = foot_slot_order(binding, profile)
    sites = {str(site.name) for site in spec.sites}
    missing = [leg for leg in order if leg not in sites]
    if missing:
        raise ValueError(
            f"{binding.robot_id}: 配方需要足端 site {missing}（本模型只有 {sorted(sites)}）—— "
            "本技能按足端 site 取速度/位置；缺失时须补 site 或改配方，不能静默换口径"
        )
    return order


def with_thigh_upper_limit(
    spec_fn: Callable[[], mujoco.MjSpec],
    profile: ParkourProfile,
    *,
    family_id: str = family_roles.DEFAULT_FAMILY_ID,
) -> mujoco.MjSpec:
    """把族角色 `hip_pitch` 的关节限位上界统一改成配方值（下界保留 MJCF 真值）。"""
    spec = spec_fn()
    names: Sequence[str] = [
        str(joint.name)
        for joint in spec.joints
        if family_roles.role_of_joint(str(joint.name), family_id) == THIGH_ROLE
    ]
    if not names:
        raise ValueError(
            f"MJCF 里找不到族角色 {THIGH_ROLE!r} 的关节（族别名表 "
            f"{family_roles.role_aliases(family_id)}）—— 无法应用配方限位"
        )
    upper = float(profile.thigh_joint_upper_limit)
    for name in names:
        joint = spec.joint(name)
        lower = float(joint.range[0])
        joint.range = (lower, upper)
    return spec
