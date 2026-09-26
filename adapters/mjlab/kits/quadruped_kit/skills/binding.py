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

import re
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any

import mujoco
from mjlab.actuator import IdealPdActuatorCfg, XmlActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg

from . import family as family_roles

#: 关节名到腿标记的分隔符（契约 `leg_naming` 的形态：`{LR}_{role}_joint`）。
_LEG_PREFIX_SEPARATOR = "_"
#: 碰撞几何名的族级尾段（族 MJCF 约定：可碰撞几何以 `_collision` 结尾）。
_COLLISION_SUFFIX = "_collision"


@dataclass(frozen=True)
class ActuatorGroup:
    """一条执行器组：角色 + 目标名正则 + PD 谱 + 契约声明的动作缩放。"""

    role: str
    target_names_expr: tuple[str, ...]
    stiffness: float
    damping: float
    effort_limit: float
    armature: float | None = None
    #: 契约 `actuator_profile.by_role[<角色>].action_scale`；缺省 = 用契约级 `action.action_scale`。
    action_scale: float | None = None

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
    #: 契约 `morphology.actuator_type`（动作语义：`position` / `velocity`）。源实现写死
    #: "position" 的地方以它为准；本字段也让 `control_modes()` 成为声明驱动。
    actuator_type: str = ""
    #: 契约 `action.action_scale`（机型级默认；角色级覆盖见 `ActuatorGroup.action_scale`）。
    action_scale: float = 1.0
    #: 执行真值在哪：`contract` = 由契约 `actuator_profile.by_role` 重建理想 PD；
    #: `asset` = 沿用机型实体自带的执行器（MJCF 是执行真值、cfg 只包装，B28/B35 口径）。
    #: 判据是**资产事实**（基座实体的执行器是不是 `XmlActuatorCfg`），不是机型名 ——
    #: 执行器写在 MJCF 里的机型没法再注入同名执行器（重名即崩），必须只包装。
    actuator_source: str = "contract"
    #: **MJCF 真值**：编译后的全部几何名 / site 名（按模型序）。腿杆/躯干/足端几何与足端
    #: site 都从这里挑 —— 技能层不预设"小腿只有一个几何""足端必须有 site"这类假设，
    #: 个数与命名由机型资产决定（挑不到就报错，不静默换口径）。
    geom_names: tuple[str, ...] = ()
    site_names: tuple[str, ...] = ()
    #: **MJCF 真值**：编译后的全部 body 名（按模型序）。足端帧的回退口径要用它
    #: （lite3 无足端 site、足端是 `*_FOOT` body —— 见 `foot_scan_frames()`）。
    body_names: tuple[str, ...] = ()
    #: **MJCF 真值**：根 body 名下的 `_collision` 几何（躯干触地惩罚的匹配集合）。
    root_collision_geoms: tuple[str, ...] = ()

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

    def role_joint_pattern(self, role: str) -> tuple[str, ...]:
        """角色的关节名正则：**同角色各腿同尾段 ⇒ 压成 `.*_<尾段>`**，否则逐关节写全名。

        用途：奖励项按角色选关节（如"髋偏离"`.*_hip_joint`）。紧凑写法与源配方字面量同形，
        但它是**从契约关节名派生**的 —— 技能层不需要知道任何机型关节名的拼法；
        换了腿前缀分隔符或角色词表的机型同样对（尾段按契约 `leg_ids` 去掉前缀得到）。
        """
        indices = self.role_joint_indices(role)
        if not indices:
            raise ValueError(
                f"{self.robot_id}: 关节序 {self.joint_order} 里找不到族角色 {role!r} 的关节"
            )
        names = [self.joint_order[index] for index in indices]
        suffixes = {role_suffix(name, self.leg_ids) for name in names}
        if len(suffixes) == 1:
            return (f".*_{next(iter(suffixes))}",)
        return tuple(names)

    def family_role(self, legacy_role: str) -> str:
        """契约角色词 → 族角色（`hip` → `hip_abduction`；族别名表查不到时原样返回）。

        技能层按**族角色**成键（profile 的 std 表等），机型契约里写的是自己的角色词 ——
        本方法就是这两套词表的唯一转换口。
        """
        return _family_role_of(legacy_role, family_roles.role_aliases(self.family_id))

    def contract_role_of_joint(self, joint_name: str) -> str:
        """关节 → 契约 `leg_pattern` 里的角色词（按名字尾段匹配，找不到即报错）。"""
        suffix = role_suffix(joint_name, self.leg_ids).lower()
        for role in self.leg_pattern:
            if role.lower() in suffix:
                return role
        raise ValueError(
            f"{self.robot_id}: 关节 {joint_name!r} 的尾段 {suffix!r} 里找不到契约角色 {self.leg_pattern}"
        )

    def control_modes(self) -> dict[str, str]:
        """逐关节动作语义（`build_joint_actions` 的 `control_modes` 入参）。

        来自契约 `morphology.actuator_type` —— 技能层不写死"四足就是位置控制"。
        """
        if not self.actuator_type:
            raise ValueError(
                f"{self.robot_id}: 契约 morphology.actuator_type 缺失，无法确定动作语义"
            )
        return {joint: self.actuator_type for joint in self.joint_order}

    def contract_action_scale(self, role: str) -> float:
        """角色的契约动作缩放（`by_role[<角色>].action_scale`，缺省回退契约级 `action.action_scale`）。"""
        group = next((item for item in self.actuator_groups if item.role == role), None)
        if group is None:
            raise ValueError(f"{self.robot_id}: 契约执行器谱里没有角色 {role!r}")
        if group.action_scale is not None:
            return float(group.action_scale)
        return float(self.action_scale)

    def action_scale_by_joint(self) -> dict[str, float]:
        """逐关节动作缩放 = 契约角色缩放 × 该机型实体执行器谱的 effort/stiffness。

        为什么要乘：位置控制的动作是"归一化偏移"，源配方（mjlab 资产库口径）把它换回
        目标角增量用的就是 `effort_limit / stiffness`（`GO2_ACTION_SCALE` 一类常量的公式）。
        执行器谱没有增益的机型（MJCF 为准、cfg 只包装的 `XmlActuatorCfg`）比值记 1，
        即**照契约声明的缩放**取值。
        """
        entity_cfg = self.base_entity_cfg()
        articulation = entity_cfg.articulation
        if articulation is None:
            raise ValueError(
                f"{self.robot_id}: 实体配置没有 articulation，无法推导逐关节动作缩放"
            )
        scales: dict[str, float] = {}
        for joint in self.joint_order:
            hits = [
                actuator
                for actuator in articulation.actuators
                if any(re.fullmatch(expr, joint) for expr in actuator.target_names_expr)
            ]
            if len(hits) != 1:
                raise ValueError(
                    f"{self.robot_id}: 关节 {joint!r} 在实体执行器谱里命中 {len(hits)} 组"
                    f"（必须恰好 1 组）—— 动作缩放无法唯一确定"
                )
            ratio = 1.0
            stiffness = getattr(hits[0], "stiffness", None)
            effort = getattr(hits[0], "effort_limit", None)
            if stiffness and effort:
                ratio = float(effort) / float(stiffness)
            scales[joint] = (
                self.contract_action_scale(self.contract_role_of_joint(joint)) * ratio
            )
        return scales

    def _role_geom_token(self, role: str) -> str:
        """角色在几何名里的词干：关节尾段去掉最后一个 `_` 之后的段（`thigh_joint` → `thigh`）。"""
        joint = self._first_joint_of_role(role)
        suffix = role_suffix(joint, self.leg_ids)
        return suffix.rsplit(_LEG_PREFIX_SEPARATOR, 1)[0] if _LEG_PREFIX_SEPARATOR in suffix else suffix

    def _first_joint_of_role(self, role: str) -> str:
        for name in self.joint_order:
            if role.lower() in role_suffix(name, self.leg_ids).lower():
                return name
        raise ValueError(
            f"{self.robot_id}: 关节序里找不到契约角色 {role!r} 的关节（契约 leg_pattern 与关节名不一致）"
        )

    def collision_geoms_for_role(self, role: str) -> tuple[str, ...]:
        """某契约角色的腿杆碰撞几何：**按契约腿序、逐腿枚举 MJCF 清单**（个数不预设）。

        go2 的小腿是两个几何（`<leg>_calf1_collision` + `calf2`）、大腿是一个 —— 技能层
        按前缀枚举，所以换机型不需要改代码；找不到即报错（不许静默少配一个几何）。
        """
        token = self._role_geom_token(role)
        picked: list[str] = []
        for leg in self.leg_ids:
            prefix = f"{leg}{_LEG_PREFIX_SEPARATOR}{token}".lower()
            hits = [name for name in self.geom_names if name.lower().startswith(prefix)]
            if not hits:
                raise RuntimeError(
                    f"{self.robot_id}: 腿 {leg} 找不到角色 {role!r} 的碰撞几何（前缀 {prefix!r}）—— "
                    f"可用几何：{sorted(name for name in self.geom_names if name)[:12]}"
                )
            picked.extend(hits)
        return tuple(picked)

    def penalized_contact_match(self) -> tuple[str, str]:
        """腿杆惩罚接触的（匹配模式, 正则）：几何具名走 geom，未命名走 body。

        族 MJCF 约定要求可碰撞几何以 `_collision` 结尾；不满足该约定的资产
        （碰撞几何由机型 `CollisionCfg` 在实体构建期重建、MJCF 里只有足端几何具名）
        没法按几何名匹配。这时按 **body 名**匹配同一批腿杆 —— 语义不变
        （"大腿/小腿与地形的接触"），只是匹配面换一维。判据是**资产事实**（几何清单
        里有没有这批名字），不是机型名；两台机型因此可以共用同一段传感器装配。
        """
        if any(
            re.fullmatch(self.penalized_geom_pattern, name)
            for name in self.geom_names
            if name
        ):
            return ("geom", self.penalized_geom_pattern)
        return ("body", self.penalized_body_pattern())

    def penalized_body_pattern(self) -> str:
        """髋以外腿杆的 **body** 紧凑正则（腿序 × 契约角色词序，词同 `leg_bodies_pattern`）。

        与 `penalized_geom_pattern` 同一挑选规则（契约 `leg_pattern` 里族角色不是
        `hip_abduction` 的那些角色），只是匹配面从几何名换成 body 名。
        """
        tokens = [
            role
            for role in self.leg_pattern
            if self.family_role(role) != "hip_abduction"
        ]
        if not tokens:
            raise ValueError(
                f"{self.robot_id}: 契约 leg_pattern {self.leg_pattern} 里找不到髋以外角色"
            )
        legs = "|".join(str(leg) for leg in self.leg_ids)
        pattern = f"(?:{legs})_(?:{'|'.join(str(token) for token in tokens)})"
        resolved = {
            name for name in self.body_names if re.fullmatch(pattern, name) is not None
        }
        if not resolved:
            raise RuntimeError(
                f"{self.robot_id}: 腿杆 body 模式 {pattern!r} 在 MJCF body 清单里空匹配 —— "
                f"可用 body：{sorted(self.body_names)}"
            )
        return pattern

    def trunk_collision_pattern(self) -> str:
        """躯干碰撞几何正则：由**根 body 自己的几何清单**派生（紧凑写法，解析集合等于清单）。

        go2 的三个 `base{1,2,3}_collision` 压成 `base.*_collision`（与源配方字面量同形）；
        命名不跟根 body 名的机型（go1 的 `trunk_collision`）得到 `trunk.*_collision`。
        压缩是否安全由 `from_contract` 用 `fullmatch` 逐名核对 —— 过匹配即判红。

        **没有躯干碰撞几何的机型**（几何挂在子 body 上）调用即报错：需要它的技能
        （rough 的躯干触地）是能力缺口，不静默退化成空匹配。
        """
        geoms = self.root_collision_geoms
        if not geoms:
            raise RuntimeError(
                f"{self.robot_id}: 根 body {self.root_body!r} 名下没有 `{_COLLISION_SUFFIX}` 几何 —— "
                "需要躯干碰撞几何的技能无法在族级装配"
            )
        return _compact_collision_pattern(geoms)

    def right_leg_indices(self) -> tuple[int, ...]:
        """腿序里**右侧腿**的位置（镜像/对称项用）。

        规则来自族内腿标记的命名约定：**含 `R` 且不含 `L`** 的是右腿。
        两个字母的腿标记里侧别字母位置不定（`FL/FR` 在末位、`RF/RH` 在首位），所以判据
        必须同时看两个字母：`RR`/`FR`/`RF` 是右腿，`RL`（后左）与 `FL` 不是。
        **不从"相邻成对、取奇数位"推** —— 那假设了腿序以左腿开头，而 b2 的契约腿序是
        `FR,FL,RR,RL`（右腿在 0、2 位），照搬 go2 的 (1,3) 会把左右镜像做反。
        挑不到右腿（腿标记另立词表）即报错，不静默给空。
        """
        picked = tuple(
            index
            for index, leg in enumerate(self.leg_ids)
            if "r" in str(leg).lower() and "l" not in str(leg).lower()
        )
        if not picked:
            raise RuntimeError(
                f"{self.robot_id}: 腿标记 {self.leg_ids} 里认不出右腿"
                "（族约定：含 'R' 的是右腿）—— 镜像/对称项无法派生"
            )
        return picked

    def foot_sites(self) -> tuple[str, ...]:
        """按契约腿序的足端 site 名（从 MJCF site 清单里挑）。

        规则：优先同名 site（`FL`），否则取该腿前缀且名含足端 token 的 site。**没有足端
        site 的机型**（如 go1）调用即报错 —— 需要 site 的技能（足端高度/滑移）是能力缺口，
        不静默退化成别的口径。
        """
        picked: list[str] = []
        for leg in self.leg_ids:
            exact = [
                name for name in self.site_names if name.lower() == str(leg).lower()
            ]
            if exact:
                picked.append(exact[0])
                continue
            prefixed = [
                name
                for name in self.site_names
                if name.lower().startswith(f"{str(leg).lower()}{_LEG_PREFIX_SEPARATOR}")
                and family_roles.FOOT_TOKEN in name.lower()
            ]
            if not prefixed:
                raise RuntimeError(
                    f"{self.robot_id}: 腿 {leg} 找不到足端 site（族约定：同名 site，或名含 "
                    f"{family_roles.FOOT_TOKEN!r} 的 <腿>_ 前缀 site）—— 可用 site：{sorted(self.site_names)}"
                )
            picked.append(sorted(prefixed)[0])
        return tuple(picked)

    def has_foot_sites(self) -> bool:
        """**能力查询**：本机型的 MJCF 是否有全套按腿的足端 site。

        `foot_sites()` 在缺 site 时抛错（"需要 site 的技能在这里是能力缺口"），但那
        对**只有部分技能**依赖 site 的机型不成立 —— 技能层需要一个"先问再取"的入口：
        False 时把依赖足端 site 的项（足端高度扫描 / 足端高度与滑移奖励）**按能力撤掉**，
        而不是拿机型名判断（go1 没有足端 site，足端就是 calf 体）。
        纯 MJCF 事实：逐腿按 `foot_sites()` 的同一口径找，全中即 True。
        """
        try:
            self.foot_sites()
        except RuntimeError:
            return False
        return True

    def family_role_token(self, family_role: str) -> str:
        """族角色 → 本机型名字里的词干（`knee` → `calf`）。

        契约角色词与族角色名可以不同（四足族 `leg_pattern` 写的是 `calf`，族角色是
        `knee`）；"按角色取几何/body 词干"的项走这里，技能层不写任何机型词。
        """
        for role in self.leg_pattern:
            if self.family_role(role) == family_role:
                return self._role_geom_token(role)
        raise ValueError(
            f"{self.robot_id}: 契约 leg_pattern {self.leg_pattern} 里找不到族角色 {family_role!r}"
        )

    def leg_bodies_pattern(self) -> str:
        """**腿杆 body** 的紧凑正则：`(?:<腿1>|<腿2>|…)_(?:<角色1>|…)`。

        契约事实派生（腿标记序 × 契约角色词序）—— 源配方写死
        `(?:FL|FR|RL|RR)_(?:hip|thigh|calf)`，同族同构机型得到同一串。
        用途：按 body 名给腿杆挂质量随机化这类"整腿若干 body"的项。
        """
        legs = "|".join(str(leg) for leg in self.leg_ids)
        roles = "|".join(str(role) for role in self.leg_pattern)
        pattern = f"(?:{legs})_(?:{roles})"
        resolved = {
            name for name in self.body_names if re.fullmatch(pattern, name) is not None
        }
        if not resolved:
            raise RuntimeError(
                f"{self.robot_id}: 腿杆 body 模式 {pattern!r} 在 MJCF body 清单里空匹配 —— "
                f"可用 body：{sorted(self.body_names)}"
            )
        return pattern

    def leg_link_body_pattern(self, family_role: str) -> str:
        """腿杆 **body** 的匹配正则（族角色 → 本机型 body 词干，`knee` → `.*_calf`）。

        用途：**碰撞几何未命名**的机型（碰撞几何由机型 `CollisionCfg` 在实体构建期
        重建、MJCF 里没有名字）没法按几何名装"腿杆/躯干触地"传感器 —— 这时按 body 名
        匹配，语义相同（"这根腿杆与地形的接触"），词干仍从契约派生。
        家族 MJCF 约定是"可碰撞几何名以 `_collision` 结尾"，本方法只服务偏离该约定的
        资产的同一语义表达，不判死任何技能。
        """
        token = self.family_role_token(family_role)
        resolved = {
            name
            for name in self.body_names
            if name.lower().endswith(f"_{token.lower()}")
        }
        if not resolved:
            raise RuntimeError(
                f"{self.robot_id}: 族角色 {family_role!r}（词干 {token!r}）在 MJCF body 清单里"
                f"找不到匹配（`*_{token}`）—— 该资产既没有命名碰撞几何、也没有可辨认的腿杆 body，"
                "需要腿杆触地传感器的技能在这里是能力缺口"
            )
        return f".*_{token}"

    def non_foot_body_pattern(self) -> str:
        """"非足端 body" 的匹配正则：`^(?!.*_<膝词干>).*`。

        来源：WTW 的 `nonfoot_ground_touch` 传感器写死 `^(?!.*_calf).*`（"除小腿/足端
        链接以外的任何 body 触地都算不期望接触"）。族级从契约派生词干 —— 四足族两者
        都得到 `calf`，但技能层不需要知道任何机型的拼法。
        """
        return rf"^(?!.*_{self.family_role_token('knee')}).*"

    def foot_link_bodies(self) -> tuple[str, ...]:
        """按契约腿序的**足端链接 body**（足端几何自己的父 body）。

        有些机型的足端链接有自己的 body（`<腿>_calf` 之外的 `<腿>_foot`），有些机型
        的足端就是小腿本体 —— 两种都从 MJCF 真值派生：**足端几何按定义挂在足端链接上**。
        找不到即报错（不静默换口径）。
        """
        model = self.base_entity_cfg().spec_fn().compile()
        by_name = {(model.geom(i).name or ""): i for i in range(model.ngeom)}
        picked: list[str] = []
        for geom in self.foot_geoms:
            index = by_name.get(geom)
            if index is None:
                raise RuntimeError(f"{self.robot_id}: 足端几何 {geom!r} 不在编译后的 MJCF 里")
            picked.append(str(model.body(int(model.geom_bodyid[index])).name))
        return tuple(picked)

    def foot_bodies(self) -> tuple[str, ...]:
        """按契约腿序的足端 **body** 名（`<腿>_<名含 foot token>`，如 lite3 的 `FL_FOOT`）。

        与 `foot_sites()` 同一约定，只是元素类型是 body：lite3 的 MJCF 没有足端 site，
        足端是 `*_FOOT` body（B31 裁决：扫描帧改用 body，射线原点仍在足端，语义不变）。
        找不到即报错（调用方要先问 `foot_scan_frames()`）。
        """
        picked: list[str] = []
        for leg in self.leg_ids:
            hits = [
                name
                for name in self.body_names
                if name.lower().startswith(f"{str(leg).lower()}{_LEG_PREFIX_SEPARATOR}")
                and family_roles.FOOT_TOKEN in name.lower()
            ]
            if not hits:
                raise RuntimeError(
                    f"{self.robot_id}: 腿 {leg} 找不到足端 body（族约定：<腿>_ 前缀且名含 "
                    f"{family_roles.FOOT_TOKEN!r} 的 body）—— 可用 body：{sorted(self.body_names)}"
                )
            picked.append(sorted(hits)[0])
        return tuple(picked)

    def foot_scan_frames(self) -> tuple[tuple[str, str], ...]:
        """足端高度扫描的帧（按契约腿序）：**优先 site，其次足端 body，都没有即空**。

        "空" = 能力缺口（go1 的足端就是 calf 体：既无 site 也无 `*_foot*` body）——
        需要它的技能按能力撤项，不静默换成别的口径。返回 `((帧类型, 名字), ...)`。
        """
        if self.has_foot_sites():
            return tuple(("site", name) for name in self.foot_sites())
        try:
            return tuple(("body", name) for name in self.foot_bodies())
        except RuntimeError:
            return ()

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

        **执行器谱只在 `actuator_source == "contract"` 时覆盖**：执行真值写在 MJCF 里的
        机型（契约 `actuator_profile` 只作声明、实体用 `XmlActuatorCfg` 包装）沿用自带执行器 ——
        按契约重建会往同一批关节再注入一次同名执行器，实体构建即崩。
        """
        cfg = deepcopy(self.base_entity_cfg())
        cfg.init_state.pos = (0.0, 0.0, float(self.init_base_height))
        cfg.init_state.joint_pos = dict(self.pose_map())
        if self.actuator_source != "contract":
            return cfg
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


def _spec_inventory(
    spec_fn: Callable[[], mujoco.MjSpec],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """编译一次 spec，取 (几何名, site 名, body 名) 三份清单（按模型序）——挑选的真值。"""
    model = spec_fn().compile()
    geoms = tuple(model.geom(i).name or "" for i in range(model.ngeom))
    sites = tuple(model.site(i).name or "" for i in range(model.nsite))
    bodies = tuple(model.body(i).name or "" for i in range(model.nbody))
    return geoms, sites, bodies


def _spec_root_collision_geoms(spec_fn: Callable[[], mujoco.MjSpec], root_body: str) -> tuple[str, ...]:
    """根 body **自己的**碰撞几何名（族 MJCF 约定：可碰撞几何以 `_collision` 结尾）。

    为什么按"归属 body"而不是按"名字前缀"挑：躯干几何的命名**不跟根 body 名**——
    go1 的根 body 叫 `base_link`，躯干几何却叫 `trunk_collision`。按名字前缀派生
    （第一版实现）会在 go1 上直接空匹配、把 jumper/AMP 两个档案的绑定构造炸掉；
    按"父 body 是根 body"挑则是纯结构事实，任何命名约定都对。
    """
    model = spec_fn().compile()
    root_id = next((i for i in range(model.nbody) if model.body(i).name == root_body), None)
    if root_id is None:
        raise RuntimeError(f"MJCF 里找不到根 body {root_body!r}")
    return tuple(
        model.geom(i).name
        for i in range(model.ngeom)
        if int(model.geom_bodyid[i]) == root_id
        and (model.geom(i).name or "").endswith(_COLLISION_SUFFIX)
    )


def _spec_root_body(spec_fn: Callable[[], mujoco.MjSpec]) -> str:
    """根 body = worldbody 的第一个子 body（MJCF 真值，契约不重复声明它）。"""
    spec = spec_fn()
    bodies = list(spec.worldbody.bodies)
    if not bodies:
        raise RuntimeError("MJCF 里 worldbody 没有子 body —— 无法确定根 body")
    return str(bodies[0].name)


def _actuator_source(base_entity_cfg: Callable[[], EntityCfg]) -> str:
    """执行真值在哪：基座实体的执行器**全是** `XmlActuatorCfg`（只包装 MJCF 既有执行器）
    即 `asset`，否则 `contract`（由契约 `actuator_profile` 重建理想 PD）。

    "全是"是刻意的：混用（一部分包装、一部分重建）说明这台机型的执行器谱是两处真值，
    族级技能层不做仲裁 —— 落到 `contract` 分支，行为与原先一致。
    """
    entity_cfg = base_entity_cfg()
    articulation = entity_cfg.articulation
    actuators = () if articulation is None else articulation.actuators
    if actuators and all(isinstance(item, XmlActuatorCfg) for item in actuators):
        return "asset"
    return "contract"


def _common_prefix(names: Sequence[str]) -> str:
    """一组几何名的公共前缀（去掉末尾分隔符）；无公共前缀时返回空串。"""
    prefix = names[0]
    for name in names[1:]:
        while prefix and not name.startswith(prefix):
            prefix = prefix[:-1]
    return prefix.rstrip(_LEG_PREFIX_SEPARATOR)


def _compact_collision_pattern(geoms: Sequence[str]) -> str:
    """一组碰撞几何名 → 紧凑正则：单名逐字转义，多名取公共前缀 + `.*_collision`。"""
    if len(geoms) == 1:
        return re.escape(geoms[0])
    return f"{_common_prefix(geoms)}.*{_COLLISION_SUFFIX}"


def _verify_trunk_pattern(
    robot_id: str,
    root_collision_geoms: Sequence[str],
    leg_ids: Sequence[str],
) -> None:
    """核对"紧凑写法"的解析集合 == 根 body 自己的几何清单（过匹配 / 吞腿杆都判红）。

    没有躯干碰撞几何的机型**不在构造期判红**：躯干触地只是某些技能需要的项
    （go1/b2 的 jumper / AMP 档案不需要），构造期就拒会让整个绑定不可用；
    真正要用它的技能在取 `trunk_collision_pattern()` 时拿到明确的"能力缺口"报错。
    """
    if not root_collision_geoms:
        return
    pattern = _compact_collision_pattern(root_collision_geoms)
    resolved = {name for name in root_collision_geoms if re.fullmatch(pattern, name)}
    if resolved != set(root_collision_geoms):
        raise ValueError(
            f"{robot_id}: 躯干碰撞模式的紧凑写法 {pattern!r} 未覆盖全部根 body 几何 "
            f"{sorted(root_collision_geoms)} —— 换逐名列举"
        )
    swallowed = [
        name
        for name in root_collision_geoms
        if any(name.lower().startswith(f"{str(leg).lower()}_") for leg in leg_ids)
    ]
    if swallowed:
        raise ValueError(
            f"{robot_id}: 躯干碰撞几何 {swallowed} 与腿标记撞名 —— 无法区分躯干与腿杆"
        )


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
    actuator_type = str(morphology.get("actuator_type") or "")
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
    default_action_scale = float((contract.get("action") or {}).get("action_scale") or 1.0)
    actuator_source = _actuator_source(base_entity_cfg)
    if actuator_source == "asset" and armature_override is not None:
        # 执行真值在 MJCF 的机型没有"重建执行器"这一步，`armature_override` 无处落地 ——
        # 静默忽略会把调用方声明的物理量丢掉，故显式判红。
        raise ValueError(
            f"{robot_id}: 该机型执行器写在 MJCF 里（XmlActuatorCfg 包装），"
            "armature_override 无处生效 —— armature 要在机型 MJCF 里改"
        )
    groups: list[ActuatorGroup] = []
    for role in leg_pattern:
        values = by_role.get(role)
        if not isinstance(values, Mapping):
            raise ValueError(f"{robot_id}: 契约 actuator_profile.by_role 缺角色 {role}")
        # 目标名正则**由关节名派生**（`FL_hip_joint` → `.*hip_joint`）：
        # 角色名本身不参与拼接，故契约换了角色词表也不用改技能层。
        suffix = role_suffix(_first_of_role(joint_order, role, leg_ids, robot_id), leg_ids)
        armature = values.get("armature")
        role_scale = values.get("action_scale")
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
                action_scale=(None if role_scale is None else float(role_scale)),
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

    geom_names, site_names, body_names = _spec_inventory(spec_fn)
    foot_geoms = family_roles.foot_geoms_for_legs(geom_names, leg_ids, foot_token)
    foot_legs = tuple(name.split("_")[0] for name in foot_geoms)
    root_body = _spec_root_body(spec_fn)
    root_collision_geoms = _spec_root_collision_geoms(spec_fn, root_body)
    # 紧凑写法的解析集合在构造期就对着真实几何清单核对（过匹配/吞腿杆都判红，
    # 不留到建环境时才发现）。没有躯干几何的机型不在此判红，见该函数 docstring。
    _verify_trunk_pattern(robot_id, root_collision_geoms, leg_ids)

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
        root_body=root_body,
        init_base_height=float(init_base_height),
        base_entity_cfg=base_entity_cfg,
        actuator_type=actuator_type,
        action_scale=default_action_scale,
        actuator_source=actuator_source,
        geom_names=geom_names,
        site_names=site_names,
        body_names=body_names,
        root_collision_geoms=root_collision_geoms,
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
