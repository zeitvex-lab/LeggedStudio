"""机型绑定：把**契约**解析成技能层要的形状 —— 技能层唯一的机型差异入口（轮足族）。

## 它是什么

一份 `WheelLegSkillBinding` 就是"这台机型在这个族技能里长什么样"的完整回答：

* 关节目录与顺序（腿段 / 轮段 / 动作序）→ 契约 `action.joint_order`（按族角色拆段）
* 默认姿 → 契约 `joints.default_pose`（**与 `joints.actuated` 对齐**，见下）
* 执行器谱（PD / 力矩 / armature / 模式）与分组 → 契约 `actuator_profile.by_role` + `leg_pattern`
* 动作缩放与控制模式 → 同上（`action_scale` / `mode`），供共享动作工厂按关节取用
* 腿标记 → 契约 `morphology.leg_ids`；根 body → **MJCF 真值**（worldbody 的子 body）
* 轮-地接触主匹配 → 族声明的轮角色别名 + 通用足端 token（见 `family.py`）
* 出生高 → 源配方的任务级参数（契约里没有这一项，故由机型侧显式给）

## 默认姿的对齐口径（重要，与四足族的差异）

契约 schema 写明 `joints.default_pose` **与 `joints.actuated` 等长**（v3
`robot-contract-3.0.schema.json`；v2 侧由 `default_pose_order: "tree"` 标注）。轮足机型里
`joints.actuated`（模型树序，按腿混排）与 `action.joint_order`（策略/动作序，腿先轮后）
**不是同一个序**，所以本模块按 `actuated` 之名与 `default_pose` 逐项配对成
"关节名 → 角度"的映射——按动作序去 zip 会把左右腿髋角的符号配反（真错，不是等价改写）。

## 谁调用它

机型包（`assets/robots/<机型>/training/source/...`）在自己的模块里构造绑定、
连同伴随的 profile 一起交给 Kit 的族级工厂：

```python
from adapters.mjlab.kits.wheel_leg_kit.skills import from_contract

ROBOT = from_contract(contract(), spec_fn=get_spec, base_entity_cfg=get_base_entity_cfg,
                      init_base_height=PROFILE.init_base_height)
```
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import mujoco
from mjlab.actuator import (
    ActuatorCfg,
    BuiltinPositionActuatorCfg,
    BuiltinVelocityActuatorCfg,
)
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.managers import SceneEntityCfg

from . import family as family_roles

#: 契约 `actuator_profile.by_role[*].mode` 的合法取值（也是动作项的控制模式词表）。
_POSITION_MODE = "position"
_VELOCITY_MODE = "velocity"
_MODES = (_POSITION_MODE, _VELOCITY_MODE)


@dataclass(frozen=True)
class ActuatorGroup:
    """一条执行器组：角色 + 目标名正则 + 契约执行器谱（模式决定 cfg 类型）。"""

    role: str
    target_names_expr: tuple[str, ...]
    mode: str
    stiffness: float | None
    damping: float
    effort_limit: float
    armature: float | None = None

    def to_cfg(self) -> ActuatorCfg:
        """按契约 `mode` 选 mjlab 的**内置**执行器（position → `<position>`、velocity → `<velocity>`）。

        内置 vs 理想 PD 是两种控制律（内置写进 MJCF、由求解器算力；理想 PD 在 Python 里算力矩），
        必须照契约声明选——选错是物理行为变更，不是写法差异。
        """
        if self.mode == _VELOCITY_MODE:
            return BuiltinVelocityActuatorCfg(
                target_names_expr=self.target_names_expr,
                damping=self.damping,
                effort_limit=self.effort_limit,
                armature=self.armature,
            )
        if self.mode == _POSITION_MODE:
            if self.stiffness is None:
                raise ValueError(f"角色 {self.role!r} 为位置模式，但契约未给 stiffness")
            return BuiltinPositionActuatorCfg(
                target_names_expr=self.target_names_expr,
                stiffness=self.stiffness,
                damping=self.damping,
                effort_limit=self.effort_limit,
                armature=self.armature,
            )
        raise ValueError(f"角色 {self.role!r} 的控制模式 {self.mode!r} 不支持（只认 {_MODES}）")


@dataclass(frozen=True)
class WheelLegSkillBinding:
    """一台轮足机型在族级技能里的全部事实（只读数据，可自由传参/比较）。"""

    robot_id: str
    family_id: str
    leg_joint_order: tuple[str, ...]
    wheel_joint_order: tuple[str, ...]
    action_joint_order: tuple[str, ...]
    default_pose: Mapping[str, float]
    leg_ids: tuple[str, ...]
    leg_pattern: tuple[str, ...]
    actuator_groups: tuple[ActuatorGroup, ...]
    action_scales: Mapping[str, float]
    control_modes: Mapping[str, str]
    root_body: str
    init_base_height: float
    base_entity_cfg: Callable[[], EntityCfg]

    # --- 派生视图 -----------------------------------------------------------

    @property
    def legs(self) -> int:
        return len(self.leg_ids)

    @property
    def position_action_scales(self) -> dict[str, float]:
        """位置段的"关节名 → 缩放"（供共享动作工厂按段取值）。"""
        return {
            joint: self.action_scales[joint]
            for joint in self.leg_joint_order
            if self.control_modes[joint] == _POSITION_MODE
        }

    @property
    def velocity_action_scales(self) -> dict[str, float]:
        """速度段的"关节名 → 缩放"。"""
        return {
            joint: self.action_scales[joint]
            for joint in self.wheel_joint_order
            if self.control_modes[joint] == _VELOCITY_MODE
        }

    @property
    def wheel_contact_pattern(self) -> str:
        """轮-地接触的主匹配正则（腿序取动作序里的轮关节腿序，token 取族声明）。"""
        leg_order: list[str] = []
        for joint in self.wheel_joint_order:
            leg = family_roles.leg_of_joint(joint, self.leg_ids)
            if leg is None:
                raise ValueError(
                    f"{self.robot_id}: 轮关节 {joint!r} 不带契约 leg_ids 的腿前缀，无法派生接触匹配"
                )
            if leg not in leg_order:
                leg_order.append(leg)
        return family_roles.wheel_contact_pattern(leg_order, self.family_id)

    def family_role(self, role: str) -> str:
        """机型（契约）角色词或族角色名 → 族角色名。

        技能层的按角色项统一走这里：profile 数据可以写机型自己的角色词
        （`hip` / `hipx` / `thigh` / …，与契约 `leg_pattern` 同词），也可以写族角色名
        （`hip_abduction` / `hip_pitch` / `knee` / `wheel`）。
        """
        aliases = family_roles.role_aliases(self.family_id)
        if role in aliases:
            return role
        for family_role, names in aliases.items():
            if role.lower() in {str(item).lower() for item in names}:
                return family_role
        raise ValueError(
            f"{self.robot_id}: 角色 {role!r} 既不是族角色 {tuple(aliases)}，也不是它们的别名"
        )

    def role_joint_indices(self, role: str) -> tuple[int, ...]:
        """族角色（或机型角色词）→ 动作关节序里的位置（用于"选髋关节"这类按角色的项）。"""
        return family_roles.joint_indices_by_role(
            self.action_joint_order, self.family_role(role), self.family_id
        )

    def role_joint_pattern(self, role: str) -> str:
        """角色的关节名正则：同角色各腿同尾段 ⇒ 压成 `.*_<尾段>`，否则逐关节写全名。

        用途：执行器目标名、奖励项按角色选关节（如姿态 std 表 `.*_hip_joint`）。
        紧凑写法与源配方字面量**解析结果一致**，但它是从契约关节名派生的——技能层
        不需要知道任何机型关节名的拼法。
        """
        indices = self.role_joint_indices(role)
        if not indices:
            raise ValueError(
                f"{self.robot_id}: 关节序 {self.action_joint_order} 里找不到角色 {role!r} 的关节"
            )
        names = [self.action_joint_order[index] for index in indices]
        suffixes = {family_roles.role_suffix(name, self.leg_ids) for name in names}
        if len(suffixes) == 1:
            return f".*_{next(iter(suffixes))}"
        return "|".join(names)

    def pose_map(self) -> dict[str, float]:
        """默认姿映射（紧凑写法：同一角色在各腿上取值相同 ⇒ 合成一条角色正则）。

        两种写法在 mjlab 里解析结果一致（`resolve_matching_names_values` 逐关节解析），
        紧凑写法只是让"同族同构"的机型配置长得像人写的。
        """
        grouped: dict[str, list[tuple[str, float]]] = {}
        for name, value in self.default_pose.items():
            grouped.setdefault(family_roles.role_suffix(name, self.leg_ids), []).append(
                (str(name), float(value))
            )
        pose: dict[str, float] = {}
        for suffix, entries in grouped.items():
            values = {value for _, value in entries}
            if len(values) == 1 and suffix:
                pose[f".*_{suffix}"] = entries[0][1]
            else:
                pose.update(entries)
        return pose

    def leg_joint_cfg(self) -> SceneEntityCfg:
        """腿关节选择器（动作序，契约真值）。"""
        return SceneEntityCfg("robot", joint_names=self.leg_joint_order, preserve_order=True)

    def wheel_joint_cfg(self) -> SceneEntityCfg:
        """轮关节选择器（动作序，契约真值）。"""
        return SceneEntityCfg("robot", joint_names=self.wheel_joint_order, preserve_order=True)

    def robot_cfg(self) -> EntityCfg:
        """本机型的技能机器人：契约默认姿 + 契约执行器谱 + 契约/MJCF 的其余事实。

        设计要点：**基座实体配置只被"覆盖"三项**（出生高 / 默认姿 / 执行器谱），
        碰撞、MJCF 来源、初始速度、柔性限位系数等一律沿用该机型自己的基座配置
        （`base_entity_cfg()`）——技能层不重造物理，只改技能关心的那几项。
        """
        cfg = deepcopy(self.base_entity_cfg())
        cfg.init_state.pos = (0.0, 0.0, float(self.init_base_height))
        cfg.init_state.joint_pos = dict(self.pose_map())
        articulation = cfg.articulation
        limit_factor = articulation.soft_joint_pos_limit_factor if articulation is not None else None
        cfg.articulation = EntityArticulationInfoCfg(
            actuators=tuple(group.to_cfg() for group in self.actuator_groups),
            soft_joint_pos_limit_factor=1.0 if limit_factor is None else float(limit_factor),
        )
        return cfg


def _actuated_names(contract: Mapping[str, Any], robot_id: str) -> tuple[str, ...]:
    """契约 `joints.actuated` 的关节名（v3 = 对象数组；v2 兼容形态 = 字符串数组）。"""
    actuated = (contract.get("joints") or {}).get("actuated") or ()
    names: list[str] = []
    for item in actuated:
        if isinstance(item, Mapping):
            name = item.get("name")
        else:
            name = item
        if name:
            names.append(str(name))
    if not names:
        raise ValueError(f"{robot_id}: 契约缺 joints.actuated，无法建默认姿映射")
    return tuple(names)


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
) -> WheelLegSkillBinding:
    """由契约 + MJCF 真值构造绑定。

    参数里**没有**任何机型的名字：`spec_fn` / `base_entity_cfg` 是该机型包自己的
    资产入口，`init_base_height` 是源配方的任务级参数。
    """
    robot_id = str(contract.get("robot_id") or "?")
    morphology = contract.get("morphology") or {}
    leg_ids = tuple(str(x) for x in (morphology.get("leg_ids") or ()))
    leg_pattern = tuple(str(x) for x in (morphology.get("leg_pattern") or ()))
    joint_order = tuple(str(x) for x in ((contract.get("action") or {}).get("joint_order") or ()))
    if not leg_ids or not joint_order or not leg_pattern:
        raise ValueError(f"{robot_id}: 契约缺 leg_ids / joint_order / leg_pattern，无法建立族级技能绑定")
    if len(joint_order) != len(leg_ids) * len(leg_pattern):
        raise ValueError(
            f"{robot_id}: 关节数 {len(joint_order)} ≠ 腿数×角色数 {len(leg_ids) * len(leg_pattern)}"
            "（族声明与契约不同构）"
        )

    # --- 腿/轮拆分：按**族角色**（role_aliases），不是字符串找 "wheel" ---------
    aliases = family_roles.role_aliases(family_id)
    wheel_role = family_roles.WHEEL_ROLE
    family_roles.wheel_role_aliases(family_id)  # 族未声明轮角色 → 这里就判红（不静默回落）
    joint_family_role: dict[str, str | None] = {
        joint: family_roles.role_of_joint(joint, family_id) for joint in joint_order
    }
    legs: list[str] = []
    wheels: list[str] = []
    for joint in joint_order:
        role = joint_family_role[joint]
        if role is None:
            raise ValueError(
                f"{robot_id}: 关节 {joint!r} 映射不到族角色（族 {family_id} 的 role_aliases 需登记该命名）"
            )
        (wheels if role == wheel_role else legs).append(joint)
    if not wheels:
        raise ValueError(f"{robot_id}: 动作序里找不到 {wheel_role!r} 角色的关节（族角色与关节名不一致）")
    # 契约声明的是"腿先轮后"的**连续分段**：动作工厂按模式切段，分段错位会把轮写进位置段。
    if joint_order.index(wheels[0]) != len(legs):
        raise ValueError(
            f"{robot_id}: 动作序的分段不是'腿段在前、轮段在后'（轮首关节在 {joint_order.index(wheels[0])}，"
            f"腿数 {len(legs)}）—— 族级动作装配按连续分段切，声明不连续即无法装配"
        )

    # --- 默认姿：与 joints.actuated 对齐（见模块 docstring 的对齐口径） ----------
    actuated_names = _actuated_names(contract, robot_id)
    pose_values = tuple(float(x) for x in ((contract.get("joints") or {}).get("default_pose") or ()))
    if len(pose_values) != len(actuated_names):
        raise ValueError(
            f"{robot_id}: joints.default_pose({len(pose_values)}) 与 joints.actuated"
            f"({len(actuated_names)}) 不等长（schema 要求等长）"
        )
    if set(actuated_names) != set(joint_order):
        raise ValueError(
            f"{robot_id}: joints.actuated 与 action.joint_order 的关节集合不一致"
            "（默认姿/动作序必须描述同一批关节）"
        )
    default_pose = dict(zip(actuated_names, pose_values, strict=True))

    # --- 执行器谱与动作缩放：逐角色取契约值 --------------------------------------
    by_role = (contract.get("actuator_profile") or {}).get("by_role") or {}
    groups: list[ActuatorGroup] = []
    action_scales: dict[str, float] = {}
    control_modes: dict[str, str] = {}
    for role in leg_pattern:
        values = by_role.get(role)
        if not isinstance(values, Mapping):
            raise ValueError(f"{robot_id}: 契约 actuator_profile.by_role 缺角色 {role}")
        mode = str(values.get("mode") or "")
        if mode not in _MODES:
            raise ValueError(f"{robot_id}: 角色 {role} 的 mode={mode!r} 不在 {_MODES}")
        if "action_scale" not in values:
            raise ValueError(f"{robot_id}: 角色 {role} 契约缺 action_scale")
        family_role = _family_role_of(role, aliases)
        role_joints = [j for j in joint_order if joint_family_role[j] == family_role]
        armature = values.get("armature")
        groups.append(
            ActuatorGroup(
                role=role,
                # 目标名正则**由关节名派生**（`FL_hip_joint` → `.*_hip_joint`）：
                # 角色名本身不参与拼接，故契约换了角色词表也不用改技能层。
                target_names_expr=(
                    _role_pattern_from_names(role_joints, leg_ids, robot_id, role),
                ),
                mode=mode,
                stiffness=None if values.get("stiffness") is None else float(values["stiffness"]),
                damping=float(values["damping"]),
                effort_limit=float(values["effort"]),
                armature=None if armature is None else float(armature),
            )
        )
        for joint in role_joints:
            action_scales[joint] = float(values["action_scale"])
            control_modes[joint] = mode

    if set(action_scales) != set(joint_order):
        missing = sorted(set(joint_order) - set(action_scales))
        raise ValueError(f"{robot_id}: 这些关节没有从契约拿到 action_scale/控制模式：{missing}")

    return WheelLegSkillBinding(
        robot_id=robot_id,
        family_id=family_id,
        leg_joint_order=tuple(legs),
        wheel_joint_order=tuple(wheels),
        action_joint_order=joint_order,
        default_pose=default_pose,
        leg_ids=leg_ids,
        leg_pattern=leg_pattern,
        actuator_groups=tuple(groups),
        action_scales=action_scales,
        control_modes=control_modes,
        root_body=_spec_root_body(spec_fn),
        init_base_height=float(init_base_height),
        base_entity_cfg=base_entity_cfg,
    )


def _family_role_of(role: str, aliases: Mapping[str, Sequence[str]]) -> str:
    """机型（契约）角色名 → 族角色名（对不上时原样返回，交给下游判红）。"""
    for family_role, names in aliases.items():
        if role == family_role or role.lower() in {str(x).lower() for x in names}:
            return family_role
    return role


def _role_pattern_from_names(
    names: Sequence[str], leg_ids: Sequence[str], robot_id: str, role: str
) -> str:
    """同角色各关节名压成一条正则（同尾段 ⇒ `.*_<尾段>`；否则逐名列出）。"""
    if not names:
        raise ValueError(f"{robot_id}: 契约 leg_pattern 角色 {role!r} 在动作序里没有对应关节")
    suffixes = {family_roles.role_suffix(name, leg_ids) for name in names}
    if len(suffixes) == 1:
        return f".*_{next(iter(suffixes))}"
    # 尾段不齐（同角色各腿命名不齐）：逐名列出（fullmatch 语义下用可选项拼一条）。
    return "(" + "|".join(names) + ")"
