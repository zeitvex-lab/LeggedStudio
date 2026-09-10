"""B3 物理事实绑定：把三端消费的物理参数收敛到契约 v3 的单一真值。

背景（重构方案 §5.7-1、任务清单 B3）
------------------------------------
各包的 ``simulation/config.json`` 与契约 v3 的 ``actuator_profile`` / ``control``
长期**双写**，且 config 侧的键风格在包之间并不统一（实测）：

* ``deeprobotics_lite3`` / ``deeprobotics_m20``：``stiffness`` 等是**逐关节**键；
* ``unitree_go2`` / ``zex-w``：**角色键控** + ``joint`` 兜底；
* ``wuji_hand``：只有 ``joint`` 一个兜底键；``torque_limits`` 在 zex-w/wuji_hand **缺失**。

契约 v3 侧则是角色化的 ``actuator_profile.by_role``（default < by_role < by_joint
三级展开），且既有测试已证明其展开值与 config 逐关节相等。因此本模块提供**唯一读取
API**，让消费者不再各自解释 config 的键风格：

    facts = physics_facts(package_dir)
    facts["by_role"]["stiffness"]      # 角色键控（浏览器 control 载荷用）
    facts["by_joint"]["armature"]      # 逐关节展开（mjlab 装配用）
    facts["control_hz"]                # 控制频率三件套

真值优先级：``contract_v3.json`` → ``simulation/config.json``（未迁移包的兼容回落，
以 ``source="legacy_config"`` 标记，使迁移进度可观测，而不是静默双真值）。

本模块只依赖标准库与 ``contracts.role_resolver``。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts.role_resolver import RoleResolver

__all__ = [
    "PARAM_KEYS",
    "CONTROL_KEYS",
    "PAYLOAD_MAP_KEYS",
    "PAYLOAD_CONST_KEYS",
    "LEG_GROUP_ROLES",
    "facts_from_contract",
    "facts_from_legacy_config",
    "physics_facts",
    "payload_physics_view",
    "action_scale_facts",
    "payload_action_scale_view",
]

# 非轮角色在浏览器载荷里的**分组键**：旧 simulation/config.json 用的是
# {"leg": 0.5, "wheel": 5.0} 这种"腿/轮"两分组，而不是契约的角色名。前端可能按
# 该分组键查找，故载荷视图在"所有非轮角色同值"时补一个 leg 组键（同 joint 兜底思路）。
LEG_GROUP_ROLES = ("leg",)
WHEEL_ROLE = "wheel"

# 物理事实的规范字段：契约侧参数名 -> 对外统一名
PARAM_KEYS = (
    ("stiffness", "stiffness"),
    ("damping", "damping"),
    ("effort", "torque_limits"),
    ("armature", "armature"),
    ("friction_loss", "friction_loss"),
)
CONTROL_KEYS = ("control_hz", "physics_hz", "decimation")

# 浏览器载荷里的角色/关节键控映射与常量表（键名沿用前端既有命名）
PAYLOAD_MAP_KEYS = ("stiffness", "damping", "torque_limits")
PAYLOAD_CONST_KEYS = (("armature", "armature"), ("friction_loss", "frictionloss"))


def _expand(contract_v3: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return RoleResolver(contract_v3).expand_actuator_profile()


def facts_from_contract(contract_v3: dict[str, Any]) -> dict[str, Any]:
    """从契约 v3 抽出物理事实（单一真值路径）。

    同时给出角色键控与逐关节两种视图，避免各消费者自行改口径。
    """

    profile = contract_v3.get("actuator_profile") or {}
    by_role = profile.get("by_role") or {}
    default = profile.get("default") or {}
    by_joint_raw = profile.get("by_joint") or {}
    expanded = _expand(contract_v3)

    role_view: dict[str, dict[str, Any]] = {}
    joint_view: dict[str, dict[str, Any]] = {}
    for contract_key, name in PARAM_KEYS:
        role_view[name] = {
            role: params[contract_key]
            for role, params in by_role.items()
            if isinstance(params, dict) and contract_key in params
        }
        joint_view[name] = {
            joint: params[contract_key]
            for joint, params in expanded.items()
            if isinstance(params, dict) and contract_key in params
        }

    control = contract_v3.get("control") or {}
    facts: dict[str, Any] = {
        "source": "contract_v3",
        "by_role": role_view,
        "by_joint": joint_view,
        "default": {
            name: default[contract_key]
            for contract_key, name in PARAM_KEYS
            if contract_key in default
        },
        # 逐关节覆盖表（异例），迁移/对账时需要知道"哪些关节是特例"
        "by_joint_override": {
            name: {
                joint: params[contract_key]
                for joint, params in by_joint_raw.items()
                if isinstance(params, dict) and contract_key in params
            }
            for contract_key, name in PARAM_KEYS
        },
    }
    for key in CONTROL_KEYS:
        facts[key] = control.get(key)
    facts["actuator_type"] = (contract_v3.get("morphology") or {}).get("actuator_type")
    return facts


def facts_from_legacy_config(sim_cfg: dict[str, Any]) -> dict[str, Any]:
    """兼容回落：未迁移包仍从 ``simulation/config.json`` 取，但输出同一形状。

    config 侧键风格不统一（逐关节 / 角色键控 / ``joint`` 兜底），此处不做猜测式改写：
    ``by_joint`` 直接采用 config 原值（其键可能是关节名或角色名），并明确标记
    ``source="legacy_config"`` 与 ``needs_migration=True``。
    """

    def pick(name: str) -> dict[str, Any]:
        raw = sim_cfg.get(name)
        return dict(raw) if isinstance(raw, dict) else {}

    facts: dict[str, Any] = {
        "source": "legacy_config",
        "needs_migration": True,
        "by_role": {
            "stiffness": pick("stiffness"),
            "damping": pick("damping"),
            "torque_limits": pick("torque_limits"),
        },
        "by_joint": {
            "stiffness": pick("stiffness"),
            "damping": pick("damping"),
            "torque_limits": pick("torque_limits"),
            "armature": pick("armature"),
            "friction_loss": pick("frictionloss"),
        },
        "default": {},
        "by_joint_override": {},
        "actuator_type": sim_cfg.get("actuator_interface"),
    }
    for key in CONTROL_KEYS:
        facts[key] = sim_cfg.get(key)
    return facts


def payload_physics_view(facts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """浏览器 control 载荷视图（B3/2）。

    前端解析顺序（``web/sim2sim/app.js`` 的 ``controlValue``）：
        精确关节名 → jointSegment(名)（去腿前缀与 joint 后缀）→ 分组/角色 → ``joint`` 兜底

    历史 ``simulation/config.json`` 的键风格跨包不同（lite3/m20 逐关节、go2/zex-w
    角色键控 + ``joint`` 兜底、wuji_hand 仅 ``joint``），因此换源时若只给角色键，
    "精确关节名"这条路会失配并**静默回退到默认值**（表现为浏览器里策略抽搐，而非报错）。

    本视图刻意同时提供：
      * **角色键**（覆盖 分组/角色 查找路径）
      * **逐关节键**（覆盖 精确关节名 查找路径，取契约 by_joint 展开，优先级最高）
      * 角色内取值一致时补 ``joint``（延续旧 config 的兜底语义）

    这样两条查找路径命中同一数值，从而在**键形态改变**的同时保证**逐关节解析结果不变**。
    ``armature`` / ``frictionloss`` 额外保留 ``__default__``（模型 default 层兜底，
    覆盖非驱动 dof）。
    """

    view: dict[str, dict[str, Any]] = {}
    for name in PAYLOAD_MAP_KEYS:
        merged: dict[str, Any] = {}
        merged.update(facts["by_role"].get(name) or {})
        # by_joint 优先级最高（契约三级展开优先级 default < by_role < by_joint）
        merged.update(facts["by_joint"].get(name) or {})
        if merged and len(set(merged.values())) == 1:
            merged["joint"] = next(iter(merged.values()))
        view[name] = merged

    for fact_key, payload_key in PAYLOAD_CONST_KEYS:
        merged = dict(facts["by_joint"].get(fact_key) or {})
        default = (facts.get("default") or {}).get(fact_key)
        if default is not None:
            merged["__default__"] = default
        view[payload_key] = merged

    return view


def action_scale_facts(contract_v3: dict[str, Any]) -> dict[str, Any]:
    """action_scale 的事实（B5/2）：``{scalar, by_role, by_joint}``。

    真值归**契约**：`action.action_scale` 是标量缺省，`actuator_profile.by_role[]`
    是角色级权威，`by_joint` 是三级展开后的逐关节结果。

    为什么消费方不该再读 ``simulation/config.json``：轮足类机型的轮档位在训练契约
    内部就是**任务相关**的（实测 go2w：UniLab 类默认 10.0、rough 任务 5.0、官方部署
    yaml 35.0），仿真侧那份 config 只是其中一个快照，再读它就会与契约漂移。
    """

    profile = contract_v3.get("actuator_profile") or {}
    by_role = {
        role: params["action_scale"]
        for role, params in (profile.get("by_role") or {}).items()
        if isinstance(params, dict) and params.get("action_scale") is not None
    }
    return {
        "source": "contract_v3",
        "scalar": (contract_v3.get("action") or {}).get("action_scale"),
        "by_role": by_role,
        "by_joint": RoleResolver(contract_v3).action_scale_by_joint(),
    }


def payload_action_scale_view(facts: dict[str, Any]) -> dict[str, Any]:
    """浏览器 control 载荷的 action_scale 视图（B5/2）。

    前端已有**比标量更细**的两条查找路径（按角色 / 按关节），这比单一标量功能更多，
    因此保留该形态，只把来源换成契约。视图刻意同时提供：

      * ``action_scale_by_role``：角色键控；非轮角色同值时补 ``leg`` 组键，
        并在全部同值时补 ``joint`` 兜底（延续旧 config 的查找语义）；
      * ``action_scale_by_joint``：逐关节（优先级最高）；
      * ``action_scale``：标量缺省。

    这样"键形态改变"不会让前端**静默回退到默认值**（表现为策略抽搐而非报错）。
    """

    by_role = dict(facts.get("by_role") or {})
    by_joint = {name: float(value) for name, value in (facts.get("by_joint") or {}).items()}

    role_view = dict(by_role)
    wheel_values = {value for role, value in by_role.items() if role == WHEEL_ROLE}
    leg_values = {value for role, value in by_role.items() if role != WHEEL_ROLE}
    if leg_values and len(leg_values) == 1:
        for group in LEG_GROUP_ROLES:
            role_view.setdefault(group, next(iter(leg_values)))
    merged = {**role_view, **by_joint}
    if merged and len(set(merged.values())) == 1:
        merged["joint"] = next(iter(merged.values()))

    scalar = facts.get("scalar")
    if scalar is None:
        scalar = merged.get("joint") if merged else None
    return {
        "action_scale": float(scalar) if scalar is not None else 0.25,
        "action_scale_by_role": merged or {"joint": 0.25},
        "action_scale_by_joint": by_joint,
        "wheel_scale_declared": bool(wheel_values),
    }


def physics_facts(package_dir: str | Path) -> dict[str, Any]:
    """读取某机器人包的物理事实（契约 v3 优先，缺失则回落 config）。"""

    root = Path(package_dir)
    contract_path = root / "contract_v3.json"
    if contract_path.exists():
        contract_v3 = json.loads(contract_path.read_text(encoding="utf-8-sig"))
        return facts_from_contract(contract_v3)

    config_path = root / "simulation" / "config.json"
    if config_path.exists():
        sim_cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
        return facts_from_legacy_config(sim_cfg)

    return {
        "source": "missing",
        "needs_migration": True,
        "by_role": {},
        "by_joint": {},
        "default": {},
        "by_joint_override": {},
        **{key: None for key in CONTROL_KEYS},
    }
