"""Contract v3 role resolver.

契约 v3 的跨字段自洽校验与角色展开引擎。数据模型见
``contracts/schema/robot-contract-3.0.schema.json``（唯一真值源）。

- 自洽校验：legs×leg_pattern 覆盖、leg_naming 模板匹配、Σcomponents.width == dimension、
  reindex_from_model 置换、by_joint 键 ⊆ 驱动关节、physics/decimation 一致。
- 展开：actuator_profile 的 default < by_role < by_joint 三级合并为逐关节参数，
  观测组件声明展开为带宽度的有序列表。

参考：1000framesai.com 的 control_defaults-by-role + reindex 一等字段（00_Survey
报告 6 §1）、robot_mujoco(MATRiX) 的 MJCF default-class-per-role 写法（报告 9 §2.2）。

本模块只依赖标准库，控制面与训练适配器都可以安全导入。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "robot-contract-3.0"
SCHEMA_PATH = Path(__file__).parent / "schema" / "robot-contract-3.0.schema.json"

ROBOT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ROLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
LEG_ID_PATTERN = re.compile(r"^[A-Za-z0-9]+$")

# ---- B4（§2.1.1 rev.2）Morphology 内核字段的取值域与 fail-closed 口径 ----
# 这些字段缺一不可：缺了就会让"同一 role、不同执行器/足型"的机型（TRON1 PF/SF/WF、
# M20/Go2W/ZEX-W 轮组、MicroDuck 腿/轮双形态）在训练与部署两侧被静默按同一种方式处理。
ACTUATOR_TYPES = ("position", "velocity", "hybrid", "bam")
FOOT_TYPES = ("point", "sole", "wheel")
MASS_SOURCES = ("mjcf_compiled", "urdf_inertial")
# 非腿式构型（灵巧手）：不声明 foot_type。
NON_LEGGED_MORPHOLOGY_IDS = ("hand",)

_ACTUATOR_PARAM_KEYS = (
    "stiffness",
    "damping",
    "effort",
    "velocity_limit",
    "armature",
    "friction_loss",
    "mode",
    "action_scale",
)


class RoleResolverError(ValueError):
    """契约 v3 结构或自洽校验失败。"""


def validate_robot_id(value: str) -> None:
    """robot_id 必须全小写，允许 snake_case 与连字符（现存包两种都有）。"""

    if not isinstance(value, str) or not ROBOT_ID_PATTERN.fullmatch(value):
        raise RoleResolverError(
            f"robot_id {value!r} 不合法：需匹配 ^[a-z0-9][a-z0-9_-]*$（如 unitree_go2 / zex-w）"
        )


def naming_pattern(leg_naming: str) -> re.Pattern[str]:
    """把 '{LR}_{role}_joint' 这类模板编译为带 leg/role 命名分组的正则。

    大小写不敏感：现存包同一模板有 '{LR}_{role}_joint' / '{LR}_{role}_JOINT' /
    '{role}_{LR}_Joint' 等大小写变体（如 limx_tron1）；role 解析后统一小写。
    """

    if "{LR}" not in leg_naming or "{role}" not in leg_naming:
        raise RoleResolverError(
            f"leg_naming {leg_naming!r} 必须同时包含 {{LR}} 与 {{role}} 占位符"
        )
    pieces = []
    for token in re.split(r"(\{LR\}|\{role\})", leg_naming):
        if token == "{LR}":
            pieces.append(r"(?P<leg>[A-Za-z0-9]+)")
        elif token == "{role}":
            pieces.append(r"(?P<role>[A-Za-z][A-Za-z0-9_]*)")
        elif token:
            pieces.append(re.escape(token))
    return re.compile("^" + "".join(pieces) + "$", re.IGNORECASE)


def _merge_params(*layers: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for layer in layers:
        if not layer:
            continue
        for key, value in layer.items():
            if key in _ACTUATOR_PARAM_KEYS and value is not None:
                merged[key] = value
    return merged


class RoleResolver:
    """契约 v3 的校验与展开。输入为契约 dict（schema 见 robot-contract-3.0）。"""

    def __init__(self, contract: dict[str, Any]):
        if not isinstance(contract, dict):
            raise RoleResolverError("契约必须是 dict")
        self.contract = contract

    # ---------- 结构访问 ----------

    @property
    def morphology(self) -> dict[str, Any]:
        return self.contract["morphology"]

    @property
    def actuated(self) -> list[dict[str, Any]]:
        return self.contract["joints"]["actuated"]

    @property
    def actuated_names(self) -> list[str]:
        return [entry["name"] for entry in self.actuated]

    @property
    def roles(self) -> list[str]:
        seen: list[str] = []
        for entry in self.actuated:
            if entry["role"] not in seen:
                seen.append(entry["role"])
        return seen

    def actuated_by_role(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for entry in self.actuated:
            grouped.setdefault(entry["role"], []).append(entry["name"])
        return grouped

    # ---------- 展开 ----------

    def action_scale_by_joint(self) -> dict[str, float]:
        """B5：action_scale 的角色展开视图 ``{joint_name: scale}``。

        `action.action_scale` 只是**标量缺省**（"这台机器人的标准动作档位"），而角色间
        的真实档位并不相同——unitree_g1 髋俯仰 0.55 / 腕俯仰 0.07；轮足类 leg 0.5 /
        wheel 35.0。标量表达不了这些差异，所以角色级声明（
        ``actuator_profile.by_role[].action_scale``）才是权威视图。

        未声明该角色的关节回落到 ``action.action_scale``，再回落到 0.25。
        """

        declared = {
            joint: float(params["action_scale"])
            for joint, params in self.expand_actuator_profile().items()
            if params.get("action_scale") is not None
        }
        fallback = (self.contract.get("action") or {}).get("action_scale")
        fallback = float(fallback) if fallback is not None else 0.25
        return {name: declared.get(name, fallback) for name in self.actuated_names}

    def expand_actuator_profile(self) -> dict[str, dict[str, Any]]:
        """default < by_role < by_joint 三级合并，返回 {joint_name: params}。"""

        profile = self.contract.get("actuator_profile") or {}
        default = profile.get("default") or {}
        by_role = profile.get("by_role") or {}
        by_joint = profile.get("by_joint") or {}
        expanded: dict[str, dict[str, Any]] = {}
        for entry in self.actuated:
            expanded[entry["name"]] = _merge_params(
                default, by_role.get(entry["role"]), by_joint.get(entry["name"])
            )
        return expanded

    def expand_observation(self) -> dict[str, Any]:
        """返回校验过宽度自洽的观测声明 {kind, components, dimension}。

        components 为空表示宽度声明待补全（v2 迁移的 history/视觉类观测），
        此时只透传 dimension 不做 Σwidth 校验。
        """

        observation = self.contract.get("observation") or {}
        components = observation.get("components") or []
        total = sum(int(component["width"]) for component in components)
        declared = observation.get("dimension")
        if components and declared is not None and declared != total:
            raise RoleResolverError(
                f"observation.dimension={declared} 与 Σcomponents.width={total} 不一致"
            )
        return {
            "kind": observation.get("kind"),
            "components": components,
            "dimension": declared if declared is not None else total,
        }

    def expand_action(self) -> dict[str, Any]:
        """返回动作声明；reindex_from_model 非恒等时校验其为合法置换。"""

        action = self.contract.get("action") or {}
        order = list(action.get("joint_order") or [])
        reindex = action.get("reindex_from_model")
        if reindex is not None:
            n = len(order)
            if sorted(reindex) != list(range(n)):
                raise RoleResolverError(
                    f"action.reindex_from_model 必须是 0..{n - 1} 的置换，得到 {reindex!r}"
                )
        declared = action.get("dimension")
        if declared is not None and declared != len(order):
            raise RoleResolverError(
                f"action.dimension={declared} 与 len(joint_order)={len(order)} 不一致"
            )
        return {**action, "joint_order": order}

    # ---------- 自洽校验 ----------

    def validate(self) -> list[str]:
        """返回全部问题（空列表 = 通过）；跨字段规则都集中在这里。"""

        errors: list[str] = []
        contract = self.contract

        if contract.get("schema_version") != SCHEMA_VERSION:
            errors.append(
                f"schema_version 必须是 {SCHEMA_VERSION!r}，得到 {contract.get('schema_version')!r}"
            )
        try:
            validate_robot_id(contract.get("robot_id"))
        except RoleResolverError as exc:
            errors.append(str(exc))

        errors.extend(self._validate_morphology())
        errors.extend(self._validate_morphology_kernel())
        errors.extend(self._validate_joints())
        errors.extend(self._validate_actuator_profile())
        errors.extend(self._validate_observation())
        errors.extend(self._validate_action())
        errors.extend(self._validate_control())
        return errors

    def ensure_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise RoleResolverError("契约 v3 自洽校验失败：" + "；".join(errors))

    def _validate_morphology(self) -> list[str]:
        errors: list[str] = []
        morphology = self.morphology
        for key in ("id", "legs", "leg_pattern", "leg_naming"):
            if key not in morphology:
                errors.append(f"morphology.{key} 缺失")
                return errors
        if not ROLE_NAME_PATTERN.fullmatch(morphology["id"]):
            errors.append(f"morphology.id {morphology['id']!r} 不合法")
        legs = morphology["legs"]
        pattern = morphology["leg_pattern"]
        if not isinstance(legs, int) or legs < 0:
            errors.append("morphology.legs 必须是非负整数")
            return errors
        if len(set(pattern)) != len(pattern):
            errors.append("morphology.leg_pattern 有重复角色")
        for role in pattern:
            if not ROLE_NAME_PATTERN.fullmatch(role):
                errors.append(f"leg_pattern 角色 {role!r} 不合法")
        try:
            naming_pattern(morphology["leg_naming"])
        except RoleResolverError as exc:
            errors.append(str(exc))
        if legs > 0 and pattern:
            declared_ids = morphology.get("leg_ids") or []
            if declared_ids and len(declared_ids) != legs:
                errors.append(
                    f"morphology.leg_ids 数量({len(declared_ids)})与 legs({legs}) 不一致"
                )
        return errors

    def _validate_morphology_kernel(self) -> list[str]:
        """B4 fail-closed：actuator_type / foot_type / wheel_indices / mass_source。

        依据 §2.1.1 rev.2（字段定义）与 §5.8.4（"缺字段在 verify 阶段显式报错，
        不静默降级"）。wheel_indices 还要与 action.joint_order × joints.role 对账，
        避免"声明了轮组却指到腿关节"这类只在真机上炸的错。
        """

        errors: list[str] = []
        morphology = self.morphology
        morphology_id = morphology.get("id")

        actuator_type = morphology.get("actuator_type")
        if actuator_type not in ACTUATOR_TYPES:
            errors.append(
                f"morphology.actuator_type 缺失或非法（{actuator_type!r}）：需为 {ACTUATOR_TYPES} 之一"
            )

        legs = int(morphology.get("legs") or 0)
        is_legged = legs > 0 and morphology_id not in NON_LEGGED_MORPHOLOGY_IDS
        foot_type = morphology.get("foot_type")
        if is_legged:
            if foot_type not in FOOT_TYPES:
                errors.append(
                    f"morphology.foot_type 缺失或非法（{foot_type!r}）：腿式构型需为 {FOOT_TYPES} 之一"
                )
        elif foot_type is not None:
            errors.append(f"morphology.foot_type 不适用于非腿式构型 {morphology_id!r}")

        mass_source = morphology.get("mass_source")
        if mass_source not in MASS_SOURCES:
            errors.append(
                f"morphology.mass_source 缺失或非法（{mass_source!r}）：需为 {MASS_SOURCES} 之一"
            )

        pattern = morphology.get("leg_pattern") or []
        raw_indices = morphology.get("wheel_indices")
        if "wheel" in pattern:
            if not isinstance(raw_indices, list) or not raw_indices:
                errors.append(
                    "morphology.wheel_indices 缺失或为空：leg_pattern 含 wheel 时必须声明轮关节槽位"
                )
            else:
                if any(not isinstance(index, int) or index < 0 for index in raw_indices):
                    errors.append("morphology.wheel_indices 必须是非负整数下标")
                elif len(set(raw_indices)) != len(raw_indices):
                    errors.append("morphology.wheel_indices 存在重复下标")
                elif legs and len(raw_indices) != legs:
                    errors.append(
                        f"morphology.wheel_indices 数量({len(raw_indices)})与 legs({legs}) 不一致"
                    )
                else:
                    order = (self.contract.get("action") or {}).get("joint_order") or []
                    if order:
                        if any(index >= len(order) for index in raw_indices):
                            errors.append(
                                f"morphology.wheel_indices 超出 action.joint_order 范围(0..{len(order) - 1})"
                            )
                        else:
                            roles = {
                                entry["name"]: entry.get("role")
                                for entry in self.actuated
                                if entry.get("name")
                            }
                            wheel_slots = sorted(
                                index
                                for index, name in enumerate(order)
                                if roles.get(name) == "wheel"
                            )
                            if sorted(raw_indices) != wheel_slots:
                                errors.append(
                                    f"morphology.wheel_indices {sorted(raw_indices)} 与 wheel 角色实际槽位 "
                                    f"{wheel_slots} 不一致"
                                )
        elif raw_indices:
            errors.append("morphology.wheel_indices 非空但 leg_pattern 不含 wheel 角色")

        return errors

    def _template_matches(self) -> tuple[list[str], list[tuple[str, str]]]:
        """只对 leg 归属关节做模板匹配；leg=null 的 extra_roles 关节不受 leg_naming 约束。"""

        regex = naming_pattern(self.morphology["leg_naming"])
        bad: list[str] = []
        parsed: list[tuple[str, str]] = []
        for entry in self.actuated:
            if entry.get("leg") is None:
                continue
            match = regex.fullmatch(entry["name"])
            if match is None:
                bad.append(entry["name"])
                continue
            # role 统一小写（模板大小写不敏感：AGIBOT 的 ABAD 与 unitree 的 hip 同层）
            parsed.append((match.group("leg"), match.group("role").lower()))
        return bad, parsed

    def _validate_joints(self) -> list[str]:
        errors: list[str] = []
        joints = self.contract["joints"]
        actuated = joints["actuated"]
        names = [entry.get("name") for entry in actuated]
        if any(not name for name in names):
            errors.append("joints.actuated 存在无名条目")
        elif len(set(names)) != len(names):
            errors.append("joints.actuated 关节名重复")

        legs = self.morphology["legs"]
        pattern = self.morphology["leg_pattern"]
        extra_roles = self.morphology.get("extra_roles") or []

        bad, parsed = self._template_matches()
        for name in bad:
            errors.append(
                f"关节名 {name!r} 不匹配 leg_naming 模板 {self.morphology['leg_naming']!r}"
            )

        # leg=null 的 extra 关节：role 必须在 extra_roles 中声明，且不受 leg_naming 约束
        extra_declared = set(extra_roles)
        for entry in actuated:
            if entry.get("leg") is None and entry["role"] not in extra_declared:
                errors.append(
                    f"extra 关节 {entry['name']} 的角色 {entry['role']!r} 未在 morphology.extra_roles 声明"
                )

        if legs > 0 and pattern and not bad:
            expected: set[tuple[str, str]] = set()
            leg_ids = self.morphology.get("leg_ids") or sorted(
                {leg for leg, _ in parsed}
            )
            for leg in leg_ids:
                for role in pattern:
                    expected.add((leg, role))
            legful = [entry for entry in actuated if entry.get("leg") is not None]
            for entry, (leg, role) in zip(legful, parsed):
                declared = (entry.get("leg"), entry["role"])
                if declared != (leg, role):
                    errors.append(
                        f"关节 {entry['name']} 声明 leg={entry.get('leg')!r}/role={entry['role']!r}"
                        f" 与命名解析 leg={leg!r}/role={role!r} 不一致"
                    )
            actual = {(leg, role) for leg, role in parsed if role in pattern}
            missing = expected - actual
            if missing:
                errors.append(
                    f"腿模式覆盖不完整，缺少 {sorted(missing)}（legs×leg_pattern 自洽）"
                )
            surplus_roles = {role for _, role in parsed} - set(pattern)
            undeclared = surplus_roles - extra_declared
            if undeclared:
                errors.append(
                    f"角色 {sorted(undeclared)} 不在 leg_pattern/extra_roles 中声明"
                )
            if entry_legs := {entry.get("leg") for entry in legful}:
                if legs and len(entry_legs) != legs:
                    errors.append(
                        f"实际腿数({len(entry_legs)})与 morphology.legs({legs}) 不一致"
                    )
        elif legs == 0:
            for entry in actuated:
                if entry.get("leg") is not None:
                    errors.append(
                        f"legs=0 时关节 {entry['name']} 不应声明 leg"
                    )
        return errors

    def _validate_actuator_profile(self) -> list[str]:
        errors: list[str] = []
        profile = self.contract.get("actuator_profile") or {}
        if not any(profile.get(key) for key in ("default", "by_role", "by_joint")):
            errors.append("actuator_profile 至少要有 default/by_role/by_joint 之一")
        by_joint = profile.get("by_joint") or {}
        known = set(self.actuated_names)
        for name in by_joint:
            if name not in known:
                errors.append(f"actuator_profile.by_joint 键 {name!r} 不是驱动关节")
        declared_roles = set(self.roles) | set(self.morphology.get("extra_roles") or [])
        for role in profile.get("by_role") or {}:
            if role not in declared_roles:
                errors.append(f"actuator_profile.by_role 角色 {role!r} 未在契约中声明")
        covered: set[str] = set()
        if any(profile.get("default") or {}):
            covered.add("*")
        covered |= set(profile.get("by_role") or {})
        for role in self.roles:
            if "*" in covered or role in covered:
                continue
            uncovered_joints = [
                name for name in self.actuated_by_role()[role] if name not in by_joint
            ]
            if uncovered_joints:
                errors.append(f"角色 {role!r} 没有任何执行器参数来源（default/by_role/by_joint）")
        return errors

    def _validate_observation(self) -> list[str]:
        errors: list[str] = []
        observation = self.contract.get("observation") or {}
        components = observation.get("components") or []
        names = [component.get("name") for component in components]
        if len(set(names)) != len(names):
            errors.append("observation.components 名称重复")
        try:
            self.expand_observation()
        except RoleResolverError as exc:
            errors.append(str(exc))
        return errors

    def _validate_action(self) -> list[str]:
        errors: list[str] = []
        action = self.contract.get("action") or {}
        order = action.get("joint_order") or []
        if sorted(order) != sorted(self.actuated_names):
            errors.append(
                "action.joint_order 与 joints.actuated 的关节集合不一致"
            )
        try:
            self.expand_action()
        except RoleResolverError as exc:
            errors.append(str(exc))
        return errors

    def _validate_control(self) -> list[str]:
        errors: list[str] = []
        control = self.contract.get("control") or {}
        control_hz = control.get("control_hz")
        physics_hz = control.get("physics_hz")
        decimation = control.get("decimation")
        if control_hz and physics_hz:
            if physics_hz % control_hz != 0:
                errors.append("physics_hz 必须是 control_hz 的整数倍")
            elif decimation and decimation != physics_hz // control_hz:
                errors.append(
                    f"decimation={decimation} 与 physics_hz/control_hz="
                    f"{physics_hz // control_hz} 不一致"
                )
        return errors


def role_values_from_per_joint(
    per_joint: dict[str, Any], leg_naming: str
) -> dict[str, Any] | None:
    """从逐关节数值反推 by_role 表；角色内取值不一致时返回 None（需 by_joint 覆盖）。

    迁移脚本（T0.2）用它把现有 16 包的逐关节 map 机械收敛为角色表；
    测试用它证明「同一份角色表展开 == 现契约数值」。
    """

    regex = naming_pattern(leg_naming)
    grouped: dict[str, set[Any]] = {}
    for name, value in per_joint.items():
        match = regex.fullmatch(name)
        if match is None:
            return None
        grouped.setdefault(match.group("role"), set()).add(value)
    table: dict[str, Any] = {}
    for role, values in grouped.items():
        if len(values) != 1:
            return None
        table[role] = next(iter(values))
    return table


def action_scale_for_contract(contract: Any) -> float | dict[str, float]:
    """B5：消费方取 action_scale 的唯一入口。

    角色内取值一致时退回 ``float``（与旧标量行为**逐值等价**，不改变既有训练）；
    角色间分化时返回 ``{joint_name: scale}``——mjlab 的
    ``BaseActionCfg.scale: float | dict[str, float]`` 接受 dict。

    这样"工作台改契约 ⇒ 训练用同一份数"，不再出现"改了没生效"。
    """

    data: Any = contract
    if not isinstance(data, dict):
        dumper = getattr(data, "model_dump", None)
        data = dumper() if callable(dumper) else dict(getattr(data, "__dict__", {}))
    per_joint = RoleResolver(data).action_scale_by_joint()
    if not per_joint:
        return 0.25
    values = set(per_joint.values())
    return next(iter(values)) if len(values) == 1 else per_joint


def _derive_actuator_type(leg_pattern: list[str]) -> str:
    """B4 推导：含 wheel 角色即 hybrid（轮足腿 position + 轮 velocity），否则 position。"""

    return "hybrid" if "wheel" in leg_pattern else "position"


def _derive_foot_type(morphology_id: str | None, leg_pattern: list[str]) -> str | None:
    """B4 推导：非腿式返回 None；wheel 角色→wheel；含 ankle* 角色→sole；其余→point。"""

    if morphology_id in NON_LEGGED_MORPHOLOGY_IDS:
        return None
    if "wheel" in leg_pattern:
        return "wheel"
    if any(str(role).startswith("ankle") for role in leg_pattern):
        return "sole"
    return "point"


def _morphology_kernel(
    *,
    morphology_id: str | None,
    leg_pattern: list[str],
    actuated: list[dict[str, Any]],
    joint_order: list[str],
    actuator_type: str | None,
    foot_type: str | None,
    wheel_indices: list[int] | None,
    mass_source: str | None,
) -> dict[str, Any]:
    """B4 内核字段：显式入参优先，缺省按构型推导（迁移/合成契约路径）。

    ``wheel_indices`` 的推导口径是"角色来源"而非硬编码槽位：在 joint_order 中找
    role == wheel 的位置，因此对 fl/fr/hl/hr、FR/FL/RR/RL 等任意关节序都成立。
    """

    roles = {entry["name"]: entry.get("role") for entry in actuated}
    derived_indices = [
        index for index, name in enumerate(joint_order) if roles.get(name) == "wheel"
    ]
    kernel: dict[str, Any] = {
        "actuator_type": actuator_type or _derive_actuator_type(leg_pattern),
        "wheel_indices": list(wheel_indices) if wheel_indices is not None else derived_indices,
        "mass_source": mass_source or "mjcf_compiled",
    }
    resolved_foot = foot_type if foot_type is not None else _derive_foot_type(morphology_id, leg_pattern)
    if resolved_foot is not None:
        kernel["foot_type"] = resolved_foot
    return kernel


def build_v3_contract(
    *,
    robot_id: str,
    morphology_id: str,
    leg_ids: Iterable[str],
    leg_pattern: Iterable[str],
    leg_naming: str,
    by_role: dict[str, dict[str, Any]],
    default_params: dict[str, Any] | None = None,
    by_joint: dict[str, dict[str, Any]] | None = None,
    joint_order: Iterable[str] | None = None,
    reindex_from_model: list[int] | None = None,
    action_scale: float | None = None,
    observation_kind: str | None = None,
    observation_components: list[dict[str, Any]] | None = None,
    observation_dimension: int | None = None,
    control: dict[str, Any] | None = None,
    default_pose: list[float] | None = None,
    actuated_entries: list[dict[str, Any]] | None = None,
    actuator_type: str | None = None,
    foot_type: str | None = None,
    wheel_indices: list[int] | None = None,
    mass_source: str | None = None,
    **metadata: Any,
) -> dict[str, Any]:
    """从紧凑输入组装契约 v3 dict。

    默认驱动关节由 leg_ids×leg_pattern×模板展开（合成场景）；迁移/对接真实模型时传
    ``actuated_entries=[{name, leg, role}, ...]``（name 必须与模型 1:1，大小写保留）。
    """

    leg_ids = list(leg_ids)
    leg_pattern = list(leg_pattern)
    if actuated_entries is not None:
        actuated = [dict(entry) for entry in actuated_entries]
    else:
        actuated = []
        for leg in leg_ids:
            for role in leg_pattern:
                actuated.append(
                    {"name": leg_naming.replace("{LR}", leg).replace("{role}", role),
                     "leg": leg,
                     "role": role}
                )
    if joint_order is None:
        joint_order = [entry["name"] for entry in actuated]
    action: dict[str, Any] = {"joint_order": list(joint_order)}
    if reindex_from_model is not None:
        action["reindex_from_model"] = list(reindex_from_model)
    if action_scale is not None:
        action["action_scale"] = action_scale
    observation: dict[str, Any] = {
        "components": list(observation_components or []),
        "dimension": observation_dimension
        if observation_dimension is not None
        else sum(int(c["width"]) for c in observation_components or []),
    }
    if observation_kind:
        observation["kind"] = observation_kind
    contract: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "robot_id": robot_id,
        "morphology": {
            "id": morphology_id,
            "legs": len(leg_ids),
            "leg_pattern": leg_pattern,
            "leg_naming": leg_naming,
            "leg_ids": leg_ids,
            "actuated_via": "leg_pattern×legs" if leg_pattern else "extra_roles",
            **_morphology_kernel(
                morphology_id=morphology_id,
                leg_pattern=leg_pattern,
                actuated=actuated,
                joint_order=list(joint_order),
                actuator_type=actuator_type,
                foot_type=foot_type,
                wheel_indices=wheel_indices,
                mass_source=mass_source,
            ),
        },
        "joints": {"actuated": actuated},
        "actuator_profile": {
            "by_role": by_role,
            **({"default": default_params} if default_params else {}),
            **({"by_joint": by_joint} if by_joint else {}),
        },
        "action": action,
        "observation": observation,
        **({"control": control} if control else {}),
        **metadata,
    }
    if default_pose is not None:
        contract["joints"]["default_pose"] = list(default_pose)
    return contract


def load_schema() -> dict[str, Any]:
    """读取 schema 真值源（供生成器与一致性测试使用）。"""

    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)
