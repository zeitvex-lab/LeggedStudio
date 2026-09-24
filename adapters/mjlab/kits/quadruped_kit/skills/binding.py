"""机型绑定：把**契约**解析成技能层要的形状 —— 技能层唯一的机型差异入口。

## 它是什么

一份 `QuadrupedSkillBinding` 就是"这台机型在这个族技能里长什么样"的完整回答：

* 关节目录与顺序、默认姿 → 契约 `action.joint_order` / `joints.default_pose`
* 执行器谱（PD / 力矩 / armature）与分组 → 契约 `actuator_profile.by_role` + `leg_pattern`
* 腿标记与足端几何 → 契约 `morphology.leg_ids` + 族级足端 token（见 `family.py`）
* 根 body → **MJCF 真值**（worldbody 的子 body），不是契约字段（契约不重复声明它）
* 出生高 → 源配方的任务级参数（契约里没有这一项，故由机型侧显式给）

## 谁调用它

机型包（`assets/robots/<机型>/training/source/...`）在自己的 stub 里构造绑定、
连同伴随的 profile 一起交给 Kit 的族级工厂：

```python
from adapters.mjlab.kits.quadruped_kit.skills import binding as kit_binding
from adapters.mjlab.kits.quadruped_kit.skills.jump import config as kit_jump

GO2 = kit_binding.from_contract(..., spec_fn=get_go2_robot_cfg().spec_fn, base_entity_cfg=get_go2_robot_cfg, ...)

def make_jump_env_cfg(*, play=False):
    return kit_jump.make_env_cfg(GO2, GO2_JUMP, play=play)
```

**反向约束**：本模块（以及 `skills/` 下所有模块）不得 import 任何机型包，
也不得出现任何机型的名字/数值 —— 所有名字来自契约与 MJCF，所有数值来自
契约或调用方显式传入的源配方参数。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any

import mujoco
from mjlab.actuator import IdealPdActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg

from . import family as family_roles

#: 关节名到腿标记的分隔符（契约 `leg_naming` 的形态：`{LR}_{role}_joint`）。
_LEG_PREFIX_SEPARATOR = "_"


@dataclass(frozen=True)
class ActuatorGroup:
    """一条执行器组：角色 + 目标名正则 + PD 谱。"""

    role: str
    target_names_expr: tuple[str, ...]
    stiffness: float
    damping: float
    effort_limit: float
    armature: float | None = None

    def to_cfg(self) -> IdealPdActuatorCfg:
        return IdealPdActuatorCfg(
            target_names_expr=self.target_names_expr,
            stiffness=self.stiffness,
            damping=self.damping,
            effort_limit=self.effort_limit,
            armature=self.armature,
        )


@dataclass(frozen=True)
class QuadrupedSkillBinding:
    """一台四足机型在族级技能里的全部事实（只读数据，可自由传参/比较）。"""

    robot_id: str
    family_id: str
    joint_order: tuple[str, ...]
    default_pose: tuple[float, ...]
    leg_ids: tuple[str, ...]
    leg_pattern: tuple[str, ...]
    actuator_groups: tuple[ActuatorGroup, ...]
    foot_geoms: tuple[str, ...]
    foot_legs: tuple[str, ...]
    penalized_geom_pattern: str
    root_body: str
    init_base_height: float
    base_entity_cfg: Callable[[], EntityCfg]

    # --- 派生视图 -----------------------------------------------------------

    @property
    def legs(self) -> int:
        return len(self.leg_ids)

    def role_joint_indices(self, role: str) -> tuple[int, ...]:
        """族角色 → 关节序里的位置（用于"选髋关节"这类按角色的项）。"""
        return family_roles.joint_indices_by_role(self.joint_order, role, self.family_id)

    @property
    def rear_legs(self) -> tuple[str, ...]:
        """后腿 = 腿标记序的后半（族约定：`leg_ids` 前腿在前，四足 = RL/RR）。"""
        return tuple(self.leg_ids[len(self.leg_ids) // 2 :])

    def joint_names(self, role: str, *, legs: Sequence[str] | None = None) -> tuple[str, ...]:
        """按（族角色, 腿集）挑关节名，顺序 = 契约关节序。

        用于"后腿髋限位"这类按角色的项：角色名走族别名（`hip_abduction` ← hip），
        腿前缀走契约 `leg_ids`；技能层因此不需要知道任何机型关节名。
        """
        wanted = {str(leg).lower() for leg in (self.leg_ids if legs is None else legs)}
        picked: list[str] = []
        for index in self.role_joint_indices(role):
            name = self.joint_order[index]
            leg = next(
                (
                    candidate
                    for candidate in self.leg_ids
                    if name.lower().startswith(f"{candidate.lower()}{_LEG_PREFIX_SEPARATOR}")
                ),
                None,
            )
            if leg is not None and leg.lower() in wanted:
                picked.append(name)
        return tuple(picked)

    def pose_map(self) -> dict[str, float]:
        """默认姿映射（与契约 `joint_order` 对齐的 12 个值）。

        **紧凑写法**：同一角色在各腿上取值相同 ⇒ 合成一条角色正则
        （`.*hip_joint`），否则逐关节写全名。两种写法在 mjlab 里解析结果一致，
        紧凑写法只是让"同族同构"的机型配置长得像人写的。
        """
        grouped: dict[str, list[tuple[str, float]]] = {}
        for name, value in zip(self.joint_order, self.default_pose, strict=True):
            grouped.setdefault(role_suffix(name, self.leg_ids), []).append((name, float(value)))
        pose: dict[str, float] = {}
        for suffix, entries in grouped.items():
            values = {value for _, value in entries}
            if len(values) == 1 and suffix:
                pose[f".*{suffix}"] = entries[0][1]
            else:
                pose.update(entries)
        return pose

    def with_pose_roles(self, by_role: Mapping[str, float]) -> "QuadrupedSkillBinding":
        """按**角色**统一改初始姿，返回新绑定（不改自身）。

        用途：技能源的初始姿态不是契约 `joints.default_pose` 时的出口。
        例：go2 的 trot 源用"髋归零 + 四腿同姿"，与契约声明的（jump 用的）非对称站姿
        不同 —— 这类**源配方姿态**由机型侧传入，技能层只负责把它压实成紧凑写法。
        键是机型自己的角色名（契约 `leg_pattern` 的角色词）。
        """
        pose = list(self.default_pose)
        lowered = {str(role).lower(): float(value) for role, value in by_role.items()}
        for index, name in enumerate(self.joint_order):
            suffix = role_suffix(name, self.leg_ids)
            for role, value in lowered.items():
                if role in suffix.lower():
                    pose[index] = value
        return replace(self, default_pose=tuple(pose))

    def robot_cfg(self) -> EntityCfg:
        """本机型的技能机器人：契约默认姿 + 契约执行器谱 + 契约/MJCF 的其余事实。

        设计要点：**基座实体配置只被"覆盖"三项**（出生高 / 默认姿 / 执行器谱），
        碰撞、MJCF 来源、柔性限位系数等一律沿用该机型自己的基座配置
        （`base_entity_cfg()`）—— 技能层不重造物理，只改技能关心的那几项。
        """
        cfg = deepcopy(self.base_entity_cfg())
        cfg.init_state.pos = (0.0, 0.0, float(self.init_base_height))
        cfg.init_state.joint_pos = dict(self.pose_map())
        articulation = cfg.articulation
        limit_factor = (
            articulation.soft_joint_pos_limit_factor
            if articulation is not None
            else None
        )
        cfg.articulation = EntityArticulationInfoCfg(
            actuators=tuple(group.to_cfg() for group in self.actuator_groups),
            soft_joint_pos_limit_factor=(
                1.0 if limit_factor is None else float(limit_factor)
            ),
        )
        return cfg


def role_suffix(joint_name: str, leg_ids: Sequence[str]) -> str:
    """关节名去掉腿前缀后的尾段（`FL_hip_joint` → `hip_joint`）；无前缀则原样。"""
    text = str(joint_name)
    for leg in leg_ids:
        prefix = f"{leg}{_LEG_PREFIX_SEPARATOR}"
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix) :]
    return text


def _spec_geom_names(spec_fn: Callable[[], mujoco.MjSpec]) -> tuple[str, ...]:
    model = spec_fn().compile()
    return tuple(model.geom(i).name or "" for i in range(model.ngeom))

def _spec_root_body(spec_fn: Callable[[], mujoco.MjSpec]) -> str:
    """根 body = worldbody 的第一个子 body（MJCF 真值，契约不重复声明它）。"""
    spec = spec_fn()
    bodies = list(spec.worldbody.bodies)
    if not bodies:
        raise RuntimeError("MJCF 里 worldbody 没有子 body —— 无法确定根 body")
    return str(bodies[0].name)


def from_contract(
    contract: Mapping[str, Any],
    *,
    spec_fn: Callable[[], mujoco.MjSpec],
    base_entity_cfg: Callable[[], EntityCfg],
    init_base_height: float,
    family_id: str = family_roles.DEFAULT_FAMILY_ID,
    armature_override: float | None = None,
    foot_token: str = family_roles.FOOT_TOKEN,
) -> QuadrupedSkillBinding:
    """由契约 + MJCF 真值构造绑定。

    参数里**没有**任何机型的名字：`spec_fn` / `base_entity_cfg` 是该机型包自己的
    资产入口，`init_base_height` 是源配方的任务级参数，`armature_override` 只在
    "源配方的执行器谱刻意偏离契约声明"时使用（见调用点的取证注释），
    默认 `None` 表示**照契约取值**。
    """
    robot_id = str(contract.get("robot_id") or "?")
    morphology = contract.get("morphology") or {}
    leg_ids = tuple(str(x) for x in (morphology.get("leg_ids") or ()))
    leg_pattern = tuple(str(x) for x in (morphology.get("leg_pattern") or ()))
    joint_order = tuple(str(x) for x in ((contract.get("action") or {}).get("joint_order") or ()))
    default_pose = tuple(float(x) for x in ((contract.get("joints") or {}).get("default_pose") or ()))
    if not leg_ids or not joint_order or not leg_pattern:
        raise ValueError(f"{robot_id}: 契约缺 leg_ids / joint_order / leg_pattern，无法建立族级技能绑定")
    if len(default_pose) != len(joint_order):
        raise ValueError(
            f"{robot_id}: joints.default_pose({len(default_pose)}) 与 action.joint_order({len(joint_order)}) 不等长"
        )
    expected_joints = len(leg_ids) * len(leg_pattern)
    if len(joint_order) != expected_joints:
        raise ValueError(
            f"{robot_id}: 关节数 {len(joint_order)} ≠ 腿数×角色数 {expected_joints}（族声明与契约不同构）"
        )

    profile = contract.get("actuator_profile") or {}
    by_role = profile.get("by_role") or {}
    groups: list[ActuatorGroup] = []
    for role in leg_pattern:
        values = by_role.get(role)
        if not isinstance(values, Mapping):
            raise ValueError(f"{robot_id}: 契约 actuator_profile.by_role 缺角色 {role}")
        # 目标名正则**由关节名派生**（`FL_hip_joint` → `.*hip_joint`）：
        # 角色名本身不参与拼接，故契约换了角色词表也不用改技能层。
        suffix = role_suffix(_first_of_role(joint_order, role, leg_ids, robot_id), leg_ids)
        armature = values.get("armature")
        groups.append(
            ActuatorGroup(
                role=role,
                target_names_expr=(f".*{suffix}",),
                stiffness=float(values["stiffness"]),
                damping=float(values["damping"]),
                effort_limit=float(values["effort"]),
                armature=(
                    armature_override
                    if armature_override is not None
                    else (None if armature is None else float(armature))
                ),
            )
        )

    # 惩罚用几何：**髋以外的腿杆**（族角色里 hip_abduction 之外的角色），
    # 与源任务"髋接触不计入惩罚"的口径一致；正则里的词取该机型**契约角色名**
    # （不是族别名 —— 几何名跟的是本机型的角色词表），仍然无机型字面量。
    aliases = family_roles.role_aliases(family_id)
    penalized_tokens = [
        role
        for role in leg_pattern
        if _family_role_of(role, aliases) != "hip_abduction"
    ]
    if not penalized_tokens:
        raise ValueError(f"{robot_id}: 契约 leg_pattern 里找不到髋以外的腿杆角色，无法派生惩罚几何正则")
    penalized = ".*_(" + "|".join(dict.fromkeys(penalized_tokens)) + ")_collision"

    geom_names = _spec_geom_names(spec_fn)
    foot_geoms = family_roles.foot_geoms_for_legs(geom_names, leg_ids, foot_token)
    foot_legs = tuple(name.split("_")[0] for name in foot_geoms)

    return QuadrupedSkillBinding(
        robot_id=robot_id,
        family_id=family_id,
        joint_order=joint_order,
        default_pose=default_pose,
        leg_ids=leg_ids,
        leg_pattern=leg_pattern,
        actuator_groups=tuple(groups),
        foot_geoms=foot_geoms,
        foot_legs=foot_legs,
        penalized_geom_pattern=penalized,
        root_body=_spec_root_body(spec_fn),
        init_base_height=float(init_base_height),
        base_entity_cfg=base_entity_cfg,
    )


def _family_role_of(role: str, aliases: Mapping[str, Sequence[str]]) -> str:
    """机型角色名 → 族角色名（契约角色名与族别名对不上时原样返回，交给下游判红）。"""
    for family_role, names in aliases.items():
        if role == family_role or role.lower() in {str(x).lower() for x in names}:
            return family_role
    return role


def _first_of_role(
    joint_order: Sequence[str], role: str, leg_ids: Sequence[str], robot_id: str
) -> str:
    """关节序里第一个属于该角色的关节（角色名按 token 出现在关节名尾段里）。"""
    for name in joint_order:
        suffix = role_suffix(name, leg_ids)
        if role.lower() in suffix.lower():
            return name
    raise ValueError(f"{robot_id}: 关节序里找不到角色 {role} 的关节（契约 leg_pattern 与关节名不一致）")
