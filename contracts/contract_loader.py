"""Unified contract loading for the training pipeline (v2/v3 convergence).

Contract v3 (``contract.json``) carries the morphology/role/actuator semantic
layer and is the canonical source for joint order, control timing, action scale,
size class, locomotion and the per-joint actuator parameter expansion.  Contract
v2 (``contract_legacy_v2.json``) still carries the data-complete record the training stack
needs (URDF path, default pose, joint limits, observation component names).

This module lets the training pipeline consume **one** merged contract by:
  1. preferring v3 for the semantic authority fields, and
  2. filling the remaining data from v2, then
  3. exposing the merged result as a plain dict plus accessor helpers.

Everything here is pure Python (no torch / training stack), so the control plane
and adapters can safely import it.  This is the convergence seam: call sites
that used to branch between v2/v3 now read a single merged record.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts.jsonio import load_json
from contracts.locomotion_view import locomotion_type_from_contract
from contracts.role_resolver import RoleResolver


class ContractLoadError(RuntimeError):
    """Raised when neither a valid v2 nor v3 contract can be loaded."""


def _read_json(path: Path) -> dict[str, Any]:
    """读 JSON 对象（编码与失败语义见 ``contracts/jsonio``）；**非对象即报错**。"""

    value = load_json(path)
    if not isinstance(value, dict):
        raise ContractLoadError(f"Contract is not a JSON object: {path}")
    return value


def load_contract(package_dir: Path) -> dict[str, Any] | None:
    """Return the v3 contract dict if present and resolvable, else None."""
    path = package_dir / "contract.json"
    if not path.exists():
        return None
    data = _read_json(path)
    # Validate role semantics; a malformed v3 should fall back rather than crash.
    RoleResolver(data).validate()
    return data


def load_legacy_contract(package_dir: Path) -> dict[str, Any] | None:
    """Return the v2 contract dict if present, else None."""
    path = package_dir / "contract_legacy_v2.json"
    if not path.exists():
        return None
    return _read_json(path)


def merge_legacy_over_contract(v3: dict[str, Any] | None, v2: dict[str, Any] | None) -> dict[str, Any]:
    """Merge the v3 semantic authority over the v2 data-complete record.

    Returns a single contract dict.  v3 wins for joint order, control timing,
    action dimension/scale, size class, locomotion, default pose and observation
    dimension/kind; v2 supplies the remainder (URDF, joint limits, observation
    component names) when v3 does not carry them.
    """
    base: dict[str, Any] = dict(v2 or {})
    if v3 is None:
        return base

    resolver = RoleResolver(v3)
    for key in ("robot_id", "family"):
        if v3.get(key):
            base[key] = v3[key]

    # ---- 参数单一家（B2/2）：以下各项的"家"在 v3，v2 侧只做投影 ----
    # 判据同 B2：谁表达能力强谁当真值，另一份退化为派生视图，结构上消除漂移。

    # 1) morphology：v3 的构型层（含 B4 的 foot_type / wheel_indices / actuator_type 与
    #    mass_source）。此前本函数**整个丢弃**它，导致这些字段到不了任何消费者。
    morphology = dict(v3.get("morphology") or {})
    if morphology:
        base["morphology"] = morphology

    # 2) locomotion_type：v3 的四值枚举表达不了"双足 + 足底 + 踝"这类组合，
    #    实测 microduck 因此两侧都漂移成 "P"。由 morphology 派生，不采信存量值。
    derived_loco = locomotion_type_from_contract(v3)
    if derived_loco:
        base["locomotion_type"] = derived_loco

    # 3) size_class：真值是"质量桶"，由 urdf.total_mass_kg 经 size_class_for_mass 派生
    #    （契约 models 的规范实现，AssetRecord 亦强制声明值等于派生值）。存量声明值会漂移
    #    ——实测 lite3 声明 L 而质量仅 6.25kg（应为 S）、g1 声明 L 而 33.3kg（应为 M）。
    #    局部导入以避免与 contracts.models 的循环引用。
    from contracts.models import size_class_for_mass

    urdf = dict(base.get("urdf") or {})
    derived_size = size_class_for_mass(urdf.get("total_mass_kg"))
    if derived_size is not None:
        base["size_class"] = derived_size.value

    # 4) mass_source：真值是 morphology.mass_source（类型化枚举 mjcf_compiled|urdf_inertial）；
    #    v2 的 urdf.mass_source 历史上是自由文本（manual/estimated/mj_model/mjcf-sum/
    #    mjcf_inertial_sum），保留为**投影**供 v2 消费方读取，使其与真值不再可能分歧。
    if morphology.get("mass_source"):
        urdf["mass_source"] = morphology["mass_source"]
    if urdf:
        base["urdf"] = urdf

    # Joint order + default pose from v3.
    actuated_names = resolver.actuated_names
    if actuated_names:
        joints = dict(base.get("joints") or {})
        joints["actuated_joints"] = actuated_names
        v3_pose = (v3.get("joints") or {}).get("default_pose") or v3.get("default_pose")
        if v3_pose is not None:
            joints["default_pose"] = v3_pose
        base["joints"] = joints

    # Action authority.
    action = resolver.expand_action()
    if action.get("joint_order"):
        act = dict(base.get("action") or {})
        act["joint_order"] = action["joint_order"]
        if action.get("dimension") is not None:
            act["dimension"] = action["dimension"]
        if action.get("action_scale") is not None:
            act["action_scale"] = action["action_scale"]
        base["action"] = act

    # Control timing authority.
    if v3.get("control"):
        ctrl = dict(base.get("control") or {})
        ctrl.update({k: val for k, val in v3["control"].items() if val is not None})
        base["control"] = ctrl

    # Observation authority: merge v3 的字段级表述（components/history/normalizer/
    # conditional_fields/recurrent_state，来自 PolicyContract 观测字段级收敛）到最终契约。
    # v3 components 非空时以 v3 字段级表述为准；为空（v2 迁移的 history/视觉观测无法
    # 机械定宽）时保留 v2 的组件名，但透传 v3 的历史帧/归一化等字段级元数据。
    obs = resolver.expand_observation()
    if obs.get("dimension") is not None:
        base_obs = dict(base.get("observation") or {})
        base_obs["dimension"] = obs["dimension"]
        if obs.get("kind"):
            base_obs["kind"] = obs["kind"]
        v3_obs = v3.get("observation") or {}
        if v3_obs.get("components"):
            base_obs["components"] = v3_obs["components"]
        for meta_key in ("history_length", "history_order", "history_reset", "normalizer",
                         "conditional_fields", "recurrent_state"):
            if v3_obs.get(meta_key) is not None:
                base_obs[meta_key] = v3_obs[meta_key]
        # 条件字段/循环状态互斥校验：存在其一则伴随全部字段级表述。
        base["observation"] = base_obs

    # Expose the v3 role-expanded actuator profile when present.
    profile = resolver.expand_actuator_profile()
    if profile:
        base["actuator_profile"] = profile
        base["actuator_profile_expanded"] = profile

    if v3.get("contract_id"):
        base["contract_id"] = v3["contract_id"]
    elif "contract_id" not in base:
        base["contract_id"] = str(v2.get("contract_id") or (base.get("robot_id") or "contract"))
    return base


def load_training_contract(package_dir: Path) -> dict[str, Any]:
    """Load the merged v2/v3 contract dict for a robot package directory.

    Raises :class:`ContractLoadError` when no contract file is present.
    """
    v3 = load_contract(package_dir)
    v2 = load_legacy_contract(package_dir)
    if v3 is None and v2 is None:
        raise ContractLoadError(f"No contract found in {package_dir}")
    return merge_legacy_over_contract(v3, v2)
