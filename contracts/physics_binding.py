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
    "facts_from_contract",
    "facts_from_legacy_config",
    "physics_facts",
]

# 物理事实的规范字段：契约侧参数名 -> 对外统一名
PARAM_KEYS = (
    ("stiffness", "stiffness"),
    ("damping", "damping"),
    ("effort", "torque_limits"),
    ("armature", "armature"),
    ("friction_loss", "friction_loss"),
)
CONTROL_KEYS = ("control_hz", "physics_hz", "decimation")


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
