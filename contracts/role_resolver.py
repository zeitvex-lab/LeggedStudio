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

    大小写不敏感：现存 16 包同一模板有 '{LR}_{role}_joint' / '{LR}_{role}_JOINT' /
    '{role}_{LR}_Joint' 等大小写变体（agibot_d1/limx_tron1）；role 解析后统一小写。
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
