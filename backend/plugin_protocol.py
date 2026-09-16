"""ls_plugin 插件协议 v1（T6.1，批次 6 / M7）。

协议对着已完成的契约 v3 设计（报告 8 方案二 E1"不凭空设计"）：
  - manifest：robot-package-1.1（capabilities/model/contract_v3_path/license/integrity）
  - 校验：目录结构 → manifest → 契约 v3 自洽 → 完整性哈希 → 许可声明
  - 匹配：三谓词数据交集（报告 6 §4.6）——
      requires_morphology ⊆ ｜ requires_roles ⊆ ｜ action_dim ==
  - 目录：catalog.json 汇总（ZIP hash 分发与许可门的消费形态，T6.3）

参考：UniLab 能力显式上收 + 异构子进程两原则（报告 7 §3）、1000frames 算法
manifest（报告 6 §1）、robot_lab framework 层（报告 4 §1 范式 B）。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from contracts.role_resolver import RoleResolver, RoleResolverError

MANIFEST_VERSIONS = {"robot-package-1.0", "robot-package-1.1"}
PACKAGE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_package(package_root: Path) -> dict[str, Any]:
    """插件包校验：errors 必须为空才算通过；warnings 不阻断。"""

    errors: list[str] = []
    warnings: list[str] = []
    package_root = Path(package_root)

    manifest = _load_json(package_root / "robot_package.json")
    if not manifest:
        return {"ok": False, "errors": [f"manifest 缺失或不可解析：{package_root / 'robot_package.json'}"], "warnings": warnings}

    if manifest.get("schema_version") not in MANIFEST_VERSIONS:
        errors.append(f"schema_version 必须是 {sorted(MANIFEST_VERSIONS)} 之一，得到 {manifest.get('schema_version')!r}")
    package_id = str(manifest.get("package_id") or "")
    if not PACKAGE_ID_PATTERN.fullmatch(package_id):
        errors.append(f"package_id {package_id!r} 不合法（^[a-z0-9][a-z0-9_-]*$）")

    model = manifest.get("model") or {}
    if not isinstance(model, dict) or not model.get("path"):
        errors.append("model.path 缺失")
    elif not (package_root / str(model["path"])).exists():
        errors.append(f"模型文件不存在: {model['path']}")

    for key, required in (("contract_path", True), ("simulation_config_path", False)):
        rel = manifest.get(key)
        if rel and not (package_root / str(rel)).exists():
            errors.append(f"{key} 指向的文件不存在: {rel}")
        elif required and not rel:
            errors.append(f"{key} 缺失")

    contract_v3 = _load_json(package_root / (manifest.get("contract_v3_path") or "contract_v3.json"))
    if not contract_v3:
        warnings.append("缺少 contract_v3.json——建议运行 tools/migrate_contract_v3.py 生成（T0.2）")
    else:
        resolver_errors = RoleResolver(contract_v3).validate()
        errors.extend(f"契约 v3: {item}" for item in resolver_errors)

    integrity = manifest.get("integrity") or {}
    if isinstance(integrity, dict) and integrity.get("model_sha256"):
        model_file = package_root / str(model.get("path") or "model/robot.xml")
        if model_file.exists() and _sha256(model_file) != integrity["model_sha256"]:
            errors.append("integrity.model_sha256 与实际模型文件不一致——包被篡改或哈希过期")

    license_info = manifest.get("license") or {}
    if not (isinstance(license_info, dict) and license_info.get("spdx")):
        warnings.append("license.spdx 未声明——分发（T6.3 许可门）前必须补齐")

    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "package_id": package_id or None, "package_root": str(package_root)}


def _norm(value: Any) -> set[str]:
    return {str(item) for item in value or []}


def match_profiles(robot_contract_v3: dict, profiles: list[dict]) -> dict[str, Any]:
    """三谓词匹配（报告 6 §4.6）：morphology ⊆ / roles ⊆ / action_dim ==。

    未声明需求字段的 profile 视为通用（与 1000frames morphology=""=通用一致）。
    """

    morphology = (robot_contract_v3.get("morphology") or {}).get("id")
    robot_roles = {entry["role"] for entry in (robot_contract_v3.get("joints") or {}).get("actuated", [])}
    action_dim = len((robot_contract_v3.get("action") or {}).get("joint_order") or [])
    results = []
    for profile in profiles:
        requires_morphology = _norm(profile.get("requires_morphology"))
        requires_roles = _norm(profile.get("requires_roles"))
        required_dim = profile.get("action_dim") or profile.get("min_obs_dimension")
        reasons = []
        if requires_morphology and morphology not in requires_morphology:
            reasons.append(f"morphology {morphology!r} 不在 {sorted(requires_morphology)}")
        if requires_roles and not requires_roles.issubset(robot_roles):
            reasons.append(f"缺少角色 {sorted(requires_roles - robot_roles)}")
        if isinstance(required_dim, int) and required_dim not in (0, None) and required_dim != action_dim:
            reasons.append(f"action_dim {required_dim} != {action_dim}")
        results.append({
            "profile_id": profile.get("profile_id"),
            "compatible": not reasons,
            "reasons": reasons,
        })
    return {"robot_id": robot_contract_v3.get("robot_id"), "morphology": morphology, "profiles": results}


def generate_catalog(package_roots: list[Path]) -> dict[str, Any]:
    """T6.3：catalog.json 汇总（含哈希与许可声明，供分发与许可门）。"""

    entries = []
    for root in package_roots:
        root = Path(root)
        report = validate_package(root)
        manifest = _load_json(root / "robot_package.json") or {}
        model_file = root / str((manifest.get("model") or {}).get("path") or "model/robot.xml")
        entries.append({
            "package_id": manifest.get("package_id") or root.name,
            "version": manifest.get("version"),
            "schema_version": manifest.get("schema_version"),
            "license": (manifest.get("license") or {}).get("spdx"),
            "model_sha256": _sha256(model_file) if model_file.exists() else None,
            "profile_count": len((record.get("training_profiles") if (record := _load_json(root / "training" / "config.json")) else None) or []),
            "valid": report["ok"],
            "package_root": str(root),
        })
    return {"schema_version": "ls-plugin-catalog-1.0", "generated_at": datetime.now().isoformat(timespec="seconds"), "packages": entries}


def scaffold_package(target_dir: Path, package_id: str) -> Path:
    """脚手架：生成最小可校验插件包骨架（外部开发者半天出包的起点）。"""

    target_dir = Path(target_dir) / package_id
    if target_dir.exists():
        raise ValueError(f"目标目录已存在: {target_dir}")
    (target_dir / "model").mkdir(parents=True)
    from backend.contract_migration import migrate_contract_dict

    draft_v2 = {
        "schema_version": "robot-contract-2.0",
        "robot_id": package_id,
        "joints": {
            "actuated_joints": [
                f"{leg}_{role}_joint"
                for leg in ("FL", "FR", "RL", "RR")
                for role in ("hip", "thigh", "calf")
            ]
        },
        "observation": {"dimension": 45, "components": ["base_ang_vel", "projected_gravity", "commands", "joint_pos", "joint_vel", "last_action"]},
        "action": {"dimension": 12, "joint_order": [f"{leg}_{role}_joint" for leg in ("FL", "FR", "RL", "RR") for role in ("hip", "thigh", "calf")], "action_scale": 0.25},
        "family": package_id,
        "size_class": "M",
        "locomotion_type": "P",
    }
    draft_v2["joints"]["default_pose"] = [0.0] * 12
    contract_v3 = migrate_contract_dict(draft_v2, None, generic_defaults=True)
    (target_dir / "contract_v3.json").write_text(json.dumps(contract_v3, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target_dir / "contract.json").write_text(json.dumps(draft_v2, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "robot-package-1.1",
        "package_id": package_id,
        "display_name": package_id,
        "capabilities": ["mujoco_sim"],
        "model": {"format": "mjcf", "path": "model/robot.xml"},
        "contract_path": "contract.json",
        "contract_v3_path": "contract_v3.json",
        # I5：脚手架**不替包作者主张许可**。原值是硬写的 {"spdx": "MIT", "redistribution":
        # "allowed"} —— 那是"我们核验过你可以再分发"的声明，而实际上谁都没核验过。
        # 如实写"未声明"，由包作者自己填。
        "license": {
            "spdx": None,
            "source": None,
            "redistribution": "unknown",
        },
    }
    (target_dir / "robot_package.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target_dir / "model" / "robot.xml").write_text(
        '<mujoco model="skeleton"><worldbody><body name="base"><geom type="sphere" size="0.1"/></body></worldbody></mujoco>\n',
        encoding="utf-8",
    )
    return target_dir
