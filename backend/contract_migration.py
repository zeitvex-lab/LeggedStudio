"""契约 v2 → v3 迁移核心（T0.2/T1.3 共用）。

被两处消费：
  - tools/migrate_contract_v3.py（16 包批量迁移 CLI）
  - backend/model_api.py（导入 → 生成契约 v3 闭环）

函数均为纯数据变换：contract_v2 dict (+ 可选 simulation config) → contract_v3 dict。
`config` 缺失时（外部导入的裸模型）用 GENERIC_ACTUATOR 默认值并打 review 标记。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.role_resolver import RoleResolver, build_v3_contract  # noqa: E402

ROBOTS_DIR = ROOT / "assets" / "robots"
LEG_VOCAB = {"fl", "fr", "rl", "rr", "hl", "hr", "left", "right", "l", "r"}

# 人工校对 hint（报告 6 §4.5 异构包）：数字来自原 backend 特判/部署参考，落为数据。
# zex-w 浏览器部署参考把轮重建为速度执行器、全关节 ±17 N·m；"*" = 全角色兜底。
ROLE_HINTS = {
    "zex-w": {
        "*": {"effort": 17.0},
        "wheel": {"mode": "velocity", "effort": 17.0},
    },
}

# actuator_interface → 契约 v3 执行器模式
INTERFACE_MODE = {
    "torque": "torque",
    "position_target": "position",
    "velocity": "velocity",
}

# 已知 3 宽度观测名（机械定宽白名单）；关节类宽度 = len(actuated)；其余 → 放弃定宽
WIDTH_3 = {
    "base_lin_vel", "base_ang_vel", "projected_gravity", "commands", "command",
    "cmd", "gravity", "ang_vel", "velocity_command", "head_pose_command",
    "body_pose_command", "gait_phase",
}
JOINT_COMPONENTS = {
    "joint_pos", "joint_vel", "joint_pos_rel", "joint_vel_rel", "last_action",
    "actions", "noisy_joint_angles",
}


def split_joint(name: str) -> tuple[str | None, str]:
    """'FL_HipX_joint' → ('FL','hipx')；'abad_L_Joint' → ('L','abad')；'neck_pitch' → (None,'neck_pitch')。"""

    tokens = name.split("_")
    leg: str | None = None
    if tokens[0].lower() in LEG_VOCAB:
        leg, role_tokens = tokens[0], tokens[1:]
    elif len(tokens) > 1 and tokens[1].lower() in LEG_VOCAB:
        leg, role_tokens = tokens[1], tokens[:1] + tokens[2:]
    else:
        role_tokens = tokens
    if len(role_tokens) > 1 and role_tokens[-1].lower() == "joint":
        role_tokens = role_tokens[:-1]
    return leg, "_".join(role_tokens).lower()


def guess_morphology_id(legs: int, pattern: list[str], extras: list[str]) -> str:
    roles = set(pattern) | set(extras)
    if any(role.startswith("finger") for role in roles):
        return "hand"
    if legs == 4:
        return "wheel_leg_16dof" if "wheel" in roles else "quadruped_12dof"
    if legs == 2:
        return "humanoid" if roles & {"shoulder_pitch", "shoulder_roll", "elbow"} else "biped"
    return f"custom_{legs}x{len(pattern)}" if pattern else "custom"


def parse_joints(actuated: list[str]) -> tuple[list[dict], dict]:
    entries: list[dict] = []
    leg_order: list[str] = []
    role_order_by_leg: dict[str, list[str]] = {}
    extra_order: list[str] = []
    for name in actuated:
        leg, role = split_joint(name)
        if leg is None:
            if role not in extra_order:
                extra_order.append(role)
        else:
            if leg not in leg_order:
                leg_order.append(leg)
                role_order_by_leg[leg] = []
            if role not in role_order_by_leg[leg]:
                role_order_by_leg[leg].append(role)
        entries.append({"name": name, "leg": leg, "role": role})
    return entries, {"leg_order": leg_order, "roles_by_leg": role_order_by_leg, "extras": extra_order}


def derive_per_joint(config: dict, key: str, joints: list[dict]) -> dict[str, Any] | None:
    """config 的 role 键控 / 逐关节 / 遗留 'joint' catch-all → 逐关节 map。"""

    raw = config.get(key)
    if not isinstance(raw, dict) or not raw:
        return None
    first = next(iter(raw))
    if first in ("hip", "thigh", "calf", "wheel", "joint", "knee"):
        result: dict[str, Any] = {}
        for entry in joints:
            value = raw.get(entry["role"], raw.get("joint"))
            if value is not None:
                result[entry["name"]] = value
        return result if result else None
    # 逐关节：键必须都是关节名（大小写不敏感匹配）
    lowered = {k.lower(): v for k, v in raw.items()}
    result = {}
    for entry in joints:
        value = lowered.get(entry["name"].lower())
        if value is not None:
            result[entry["name"]] = value
    return result if result else None


def build_actuator_profile(config: dict, joints: list[dict]) -> tuple[dict, dict, int]:
    """返回 (by_role, by_joint, uniform_count)。角色内取值不一致的关节进 by_joint。"""

    per_joint_merged: dict[str, dict[str, Any]] = {}
    for key, param in (
        ("stiffness", "stiffness"),
        ("damping", "damping"),
        ("torque_limits", "effort"),
        ("armature", "armature"),
        ("velocity_limits", "velocity_limit"),
    ):
        per_joint = derive_per_joint(config, key, joints)
        if per_joint is None:
            continue
        for name, value in per_joint.items():
            per_joint_merged.setdefault(name, {})[param] = value

    by_role: dict[str, dict[str, Any]] = {}
    by_joint: dict[str, dict[str, Any]] = {}
    for entry in joints:
        name, role = entry["name"], entry["role"]
        params = per_joint_merged.get(name)
        if not params:
            continue
        existing = by_role.setdefault(role, {})
        conflict = False
        for key, value in params.items():
            if key in existing and existing[key] != value:
                conflict = True
            else:
                existing[key] = value
        if conflict:
            # 该关节与角色表冲突：从角色表撤出其参数差异，落 by_joint
            by_joint[name] = params
    return by_role, by_joint, len(per_joint_merged)


def find_reindex(config: dict, dof: int) -> list[int] | None:
    """递归搜 config 里的 joint_ids_map / reindex（如 m20）。"""

    stack = [config]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("joint_ids_map", "reindex_from_model") and isinstance(value, list):
                    if len(value) == dof and all(isinstance(i, int) for i in value):
                        return value
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(item for item in node if isinstance(item, (dict, list)))
    return None


def build_observation(v2: dict, joints: list[dict], wheels: int) -> tuple[list[dict], str | None]:
    """可机械定宽才给 components；Σwidth 必须等于 v2 dimension，否则整体留空。"""

    dof = len(joints)
    v2_obs = v2.get("observation") or {}
    dimension = int(v2_obs.get("dimension") or 0)
    derived: list[dict] = []
    source_map = {
        "base_lin_vel": "imu", "base_ang_vel": "imu", "projected_gravity": "imu",
        "gravity": "imu", "ang_vel": "imu",
        "commands": "cmd", "command": "cmd", "cmd": "cmd", "velocity_command": "cmd",
        "head_pose_command": "cmd", "body_pose_command": "cmd", "gait_phase": "cmd",
        "joint_pos": "actuated", "joint_vel": "actuated", "joint_pos_rel": "actuated",
        "joint_vel_rel": "actuated", "wheel_joint_pos_rel": "actuated",
        "wheel_joint_vel_rel": "actuated", "noisy_joint_angles": "actuated",
        "last_action": "action", "actions": "action",
    }
    derivable = True
    for name in v2_obs.get("components") or []:
        if name in WIDTH_3:
            width = 3
        elif name in JOINT_COMPONENTS:
            width = wheels if name.startswith("wheel_") else dof
        else:
            derivable = False
            break
        derived.append({"name": name, "width": width, "source": source_map[name]})
    if derivable and derived and dimension and sum(c["width"] for c in derived) != dimension:
        derivable = False
    return (derived if derivable else []), (None if derivable else "widths-need-review")




GENERIC_ACTUATOR = {"stiffness": 20.0, "damping": 0.5, "effort": 40.0, "mode": "position"}


def migrate_contract_dict(
    contract_v2: dict[str, Any],
    config: dict[str, Any] | None = None,
    *,
    package_id: str | None = None,
    generic_defaults: bool = False,
) -> dict[str, Any]:
    """v2 契约 (+ 可选 config) → v3 契约 dict，过 RoleResolver 自洽校验。

    generic_defaults=True（外部导入、无仿真配置）时用 GENERIC_ACTUATOR 兜底，
    并在 description 打上"待校准"标记。
    """

    config = config or {}
    joints, structure = parse_joints(contract_v2["joints"]["actuated_joints"])
    legs = structure["leg_order"]
    pattern = structure["roles_by_leg"][legs[0]] if legs else []
    extras = structure["extras"]
    for leg in legs[1:]:
        if structure["roles_by_leg"][leg] != pattern:
            raise SystemExit("各腿角色序列不一致，需人工校对")
    wheels = sum(1 for e in joints if e["role"] == "wheel")

    naming = "{LR}_{role}_joint"
    first = contract_v2["joints"]["actuated_joints"][0]
    if first.split("_")[0].lower() not in LEG_VOCAB:
        naming = "{role}_{LR}_joint"
    if not all(name.lower().endswith("joint") for name in contract_v2["joints"]["actuated_joints"]):
        naming = naming.replace("_joint", "")

    if generic_defaults and not any(config.get(k) for k in ("stiffness", "damping", "torque_limits")):
        by_role = {role: dict(GENERIC_ACTUATOR) for role in pattern + extras}
        note = "generic-actuator-defaults（导入默认值，训练前请校准）"
    else:
        by_role, by_joint, _ = build_actuator_profile(config, joints)
        if not by_role:
            raise ValueError("无法从 config 抽取执行器参数")
        interface_mode = INTERFACE_MODE.get(str(config.get("actuator_interface") or "").lower(), "position")
        for role, params in by_role.items():
            params.setdefault("mode", interface_mode)
        note = None
    dof = len(joints)
    contract = build_v3_contract(
        robot_id=contract_v2["robot_id"],
        morphology_id=guess_morphology_id(len(legs), pattern, extras),
        leg_ids=legs,
        leg_pattern=pattern,
        leg_naming=naming,
        by_role=by_role,
        by_joint=by_joint or None,
        actuated_entries=joints,
        joint_order=contract_v2["action"]["joint_order"],
        reindex_from_model=find_reindex(config, dof),
        action_scale=contract_v2["action"].get("action_scale") or config.get("action_scale"),
        observation_components=build_observation(contract_v2, joints, wheels)[0],
        observation_dimension=int((contract_v2.get("observation") or {}).get("dimension") or 0),
        control={
            "control_hz": config["control_hz"],
            "physics_hz": config["physics_hz"],
            "decimation": config["decimation"],
        } if all(k in config for k in ("control_hz", "physics_hz", "decimation")) else None,
        default_pose=contract_v2["joints"].get("default_pose"),
        contract_id=f"{contract_v2['robot_id']}_v3",
        family=contract_v2.get("family"),
        size_class=contract_v2.get("size_class"),
        locomotion_type=contract_v2.get("locomotion_type"),
        description=contract_v2.get("description", ""),
        tags=contract_v2.get("tags", []),
        source=contract_v2.get("source", ""),
    )
    if extras:
        contract["morphology"]["extra_roles"] = extras
    if wheels:
        contract["morphology"]["actuated_via"] = "leg_pattern×legs（含 wheel 角色）"
    if note:
        contract["description"] = (contract.get("description") + "；" if contract.get("description") else "") + note
    errors = RoleResolver(contract).validate()
    if errors:
        raise ValueError("v3 自洽校验失败：" + "；".join(errors))
    return contract


def apply_role_hints(contract: dict[str, Any], package_id: str) -> dict[str, Any]:
    """人工校对 hint 覆盖（覆盖机械推导值）。"""

    hints = ROLE_HINTS.get(package_id, {})
    by_role = contract["actuator_profile"].setdefault("by_role", {})
    for role, params in by_role.items():
        params.setdefault("mode", "position")
        for key, value in (hints.get(role) or hints.get("*") or {}).items():
            params[key] = value
    return contract
