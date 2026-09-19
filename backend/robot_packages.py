"""Robot package discovery for the Web, CLI and isolated MJLab worker.

Robot identity is data owned by a package.  The control plane never infers a
special task from ``robot_id``; it only reads the package capability manifest.

Discovery is *index-driven*: the list of available packages is backed by a
persistent JSON index under the workspace (``workspace/package_index.json``)
instead of a fresh filesystem scan on every read.  The index is updated
explicitly when a package is imported (``upsert_package``), saved
(``upsert_package``) or deleted (``remove_package``), or rebuilt eagerly via
``rebuild_package_index``.  Reading the index is a single JSON load, which
keeps list/queries fast and free of continuous directory scanning.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
_INDEX_FILENAME = "package_index.json"

# In-memory copy of the last loaded index so repeated reads inside a short
# window don't hit the disk every time.  It is NOT a freshness scan: it only
# mirrors the persistent index file and is refreshed on explicit writes.
# Cache shape: (workspace_key, records) so a changed LEGGED_STUDIO_WORKSPACE
# (e.g. tests with a temp workspace) always reflects the right index file.
_INDEX_CACHE: Any = None
_INDEX_CACHE_LOCK = threading.Lock()


# 委托到唯一实现（本模块内有局部变量叫 workspace_root，故沿用私有名，避免 LEGB 遮蔽）。
from backend.paths import workspace_root as _workspace_root
from backend.jsonio import read_json, load_json  # JSON 读取唯一实现



def _read_json(path: Path) -> dict[str, Any]:
    """读 JSON 对象；缺失 / 坏内容 / 非对象一律 ``{}``（"空清单"语义）。"""

    return read_json(path, default={}, require=dict)


def _public_path(path: Path) -> str:
    """Return a stable path for both source-tree and external workspace packages."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def validate_training_profile(profile: dict[str, Any]) -> list[str]:
    """Validate the robot-neutral profile contract without importing its code."""
    errors: list[str] = []
    if profile.get("schema_version") != "training-profile-1.0":
        errors.append("schema_version must be training-profile-1.0")
    if not str(profile.get("profile_id", "")).strip():
        errors.append("profile_id is required")
    if not str(profile.get("backend", "")).strip():
        errors.append("backend is required")
    entrypoints = profile.get("entrypoints")
    if not isinstance(entrypoints, dict):
        errors.append("entrypoints must be an object")
    else:
        for name in ("env", "runner"):
            value = str(entrypoints.get(name, ""))
            if value.count(":") != 1 or not all(value.split(":")):
                errors.append(f"entrypoints.{name} must use module:callable syntax")
        for name in ("runner_class", "configure"):
            value = entrypoints.get(name)
            if value is not None and (str(value).count(":") != 1 or not all(str(value).split(":"))):
                errors.append(f"entrypoints.{name} must use module:callable syntax")
    return errors


def package_for_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Return the package descriptor owning a contract.

    Imported packages use ``robot_package.json`` next to ``contract_legacy_v2.json``.
    Legacy built-in assets get a deterministic generic descriptor until their
    package manifest is added.
    """
    model = Path(str(contract.get("urdf", {}).get("path", "")))
    if not model.is_absolute():
        model = ROOT / model
    model = model.resolve()
    candidates = [model.parent / "robot_package.json", model.parent / "package.json"]
    candidates.extend(model.parents[i] / "robot_package.json" for i in range(min(3, len(model.parents))))
    descriptor: dict[str, Any] = {}
    package_path: Path | None = None
    for candidate in candidates:
        if candidate.exists():
            descriptor = _read_json(candidate)
            package_path = candidate.parent
            break
    if package_path is None:
        package_path = model.parent
    # Prefer the shipped package when an older persisted copy does not carry
    # the package-owned training profile/extension. This keeps existing local
    # installs upgradeable without requiring users to re-import Go2.
    package_id_hint = str(contract.get("robot_id") or package_path.name)
    shipped = ROOT / "assets" / "robots" / package_id_hint
    if shipped.is_dir() and (shipped / "robot_package.json").exists():
        current_score = int((package_path / "training" / "profiles").exists()) * 4 + int((package_path / "training" / "source").exists()) * 2 + int(bool(descriptor.get("extension_entrypoint")))
        shipped_descriptor = _read_json(shipped / "robot_package.json")
        shipped_score = int((shipped / "training" / "profiles").exists()) * 4 + int((shipped / "training" / "source").exists()) * 2 + int(bool(shipped_descriptor.get("extension_entrypoint")))
        if shipped_score > current_score:
            package_path = shipped
            descriptor = shipped_descriptor
    package_id = str(descriptor.get("package_id") or contract.get("robot_id") or package_path.name)
    result = {
        "schema_version": "robot-package-1.0",
        "package_id": package_id,
        "package_root": str(package_path),
        "contract_path": str(package_path / "contract_legacy_v2.json"),
        "asset_path": str((package_path / str((descriptor.get("model") or {}).get("path", "model/robot.xml"))).resolve()) if descriptor else str(model),
        "task_kind": "generic",
        "native_task_id": None,
        "extension_root": descriptor.get("extension_root"),
        "extension_entrypoint": descriptor.get("extension_entrypoint"),
        "capabilities": descriptor.get("capabilities", ["generic_mjlab"]),
        "descriptor_source": str(package_path / "robot_package.json") if descriptor else "inferred",
    }
    # Task execution is intentionally uniform: package source may contain
    # historical task modules, but the platform always trains through the
    # generic MJLab builder. Descriptor fields remain available as metadata.
    return {**descriptor, **result}


def robot_package_root(robot_id: str) -> Path:
    """机器人包根：优先取预设里登记的 `package_root`，退回内置 `assets/robots/<id>`。

    单一实现（此前只在 `backend/bundle_export.py` 里）：包根的解析规则只能有一处，
    否则"导出带的包"与"训练安装进的包"可能是两份不同目录。
    """

    try:
        from backend.robot_presets import get_robot_preset

        preset = get_robot_preset(robot_id) or {}
        root_value = str(((preset.get("robot_package") or {}).get("package_root") or ""))
        if root_value:
            candidate = Path(root_value)
            if candidate.is_dir():
                return candidate
    except Exception:  # 预设不可用时退回内置目录（不因预设问题阻断调用方）
        pass
    return ROOT / "assets" / "robots" / robot_id


def write_package_manifest(package_root: Path, *, package_id: str, task_kind: str = "generic", native_task_id: str | None = None, extension_root: str | None = None) -> Path:
    package_root.mkdir(parents=True, exist_ok=True)
    path = package_root / "robot_package.json"
    payload = {
        "schema_version": "robot-package-1.0",
        "package_id": package_id,
        "task_kind": task_kind,
        "native_task_id": native_task_id,
        "extension_root": extension_root,
        "capabilities": ["generic_mjlab"] + (["package_extension"] if native_task_id else []),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Persistent index
# ---------------------------------------------------------------------------

def _index_path() -> Path:
    return _workspace_root() / _INDEX_FILENAME


_INDEX_META_FILENAME = "package_index.meta.json"


def _package_roots() -> list[Path]:
    workspace_root = _workspace_root()
    return [workspace_root / "packages", ROOT / "assets" / "robots"]


#: 代码拥有的同步规则修订号。给同步加新职责（C6 基础文件补齐 / D7 加 morphology 视图与
#: contract.json 镜像 / B13 加 training/config.json 指针文件镜像 / B36 加 v2
#: contract_legacy_v2.json 契约镜像）时 bump 它，让既有安装的索引判为 stale 并重跑一次同步
#: （磁盘未变）。
#: 提为模块级常量，测试据此动态构造"旧版本 signature"，避免每次 bump 都要改测试。
SYNC_REVISION = "5"


def _package_signature() -> str:
    """Cheap freshness signature over both package roots.

    Covers: which package dirs exist, and the mtimes of each contract /
    manifest / profiles dir.  Any add / edit / delete flips the signature so
    the persisted index can be auto-refreshed (fixes "stale index" bugs where
    newly added robots never showed up in the desktop app).

    ``sync_rev`` is a code-owned revision of the content-sync rules: bump it
    whenever the sync itself gains a new duty so existing installs re-run the
    sync once even though nothing on disk changed (C6: base-file backfill).
    """
    parts: list[str] = [f"sync_rev:{SYNC_REVISION}"]
    for root in _package_roots():
        if not root.exists():
            parts.append(f"{root}:missing")
            continue
        try:
            entries = sorted(p.name for p in root.iterdir() if p.is_dir())
        except OSError:
            entries = []
        parts.append(f"{root}:{','.join(entries)}")
        for name in entries:
            pkg = root / name
            for rel in ("contract_legacy_v2.json", "robot_package.json"):
                f = pkg / rel
                try:
                    parts.append(f"{name}/{rel}:{int(f.stat().st_mtime_ns)}")
                except OSError:
                    parts.append(f"{name}/{rel}:-")
            profiles = pkg / "training" / "profiles"
            if profiles.is_dir():
                try:
                    count = sum(1 for x in profiles.glob("*.json"))
                    parts.append(f"{name}/profiles:{int(profiles.stat().st_mtime_ns)}:{count}")
                except OSError:
                    pass
    return "|".join(parts)


def _index_meta_path() -> Path:
    return _workspace_root() / _INDEX_META_FILENAME


def _index_is_stale() -> bool:
    meta = _read_json(_index_meta_path())
    return bool(meta) is False or meta.get("signature") != _package_signature()


def _write_index_meta(signature: str) -> None:
    path = _index_meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    import time
    path.write_text(json.dumps({"signature": signature, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False), encoding="utf-8")


def _read_index() -> list[dict[str, Any]]:
    """Return the persisted package records, or an empty list."""
    path = _index_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and isinstance(value.get("packages"), list):
            return value["packages"]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _write_index(records: list[dict[str, Any]]) -> None:
    """Atomically persist the package records to the workspace index."""
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    global _INDEX_CACHE
    _INDEX_CACHE = (str(_workspace_root()), [dict(item) for item in records])


# ---------------------------------------------------------------------------
# Serialisation / record building
# ---------------------------------------------------------------------------

def _record_fields() -> list[str]:
    # Canonical field list kept for stable serialisation of index records.  The
    # full contract and package descriptor are JSON-serialisable and safe to
    # persist, so a read of the index returns the same data a scan would build.
    return [
        "schema_version", "source", "robot_id", "package_id", "family",
        "size_class", "locomotion_type", "dof", "mass_kg", "contract_id",
        "contract_path", "asset_path", "training_config", "simulation_config",
        "training_profiles", "runtime_requirements", "source_runtime",
        "contract", "robot_package", "morphology",
    ]


def _build_record(
    package_root: Path,
    source_priority: int,
    contract: dict[str, Any],
    descriptor: dict[str, Any],
) -> dict[str, Any]:
    """Build a single serialisable package record from its on-disk package."""
    contract_path = package_root / "contract_legacy_v2.json"
    training_path = package_root / "training" / "config.json"
    simulation_path = package_root / "simulation" / "config.json"
    profile_dir = package_root / "training" / "profiles"
    profiles: list[dict[str, Any]] = []
    if profile_dir.exists():
        raw_profiles: list[tuple[Path, dict[str, Any]]] = []
        for profile_path in profile_dir.glob("*.json"):
            profile = _read_json(profile_path)
            if profile:
                raw_profiles.append((profile_path, profile))
        raw_profiles.sort(key=lambda item: (item[1].get("sort_order", 1000), item[0].name))
        for profile_path, profile in raw_profiles:
            errors = validate_training_profile(profile)
            profile_requirements = profile.get("runtime_requirements")
            if not isinstance(profile_requirements, dict):
                profile_requirements = descriptor.get("runtime_requirements", {})
            profiles.append({**profile, "runtime_requirements": profile_requirements, "path": _public_path(profile_path), "valid": not errors, "validation_errors": errors})
    descriptor_model = descriptor.get("model", {}) if isinstance(descriptor.get("model"), dict) else {}
    model_path = str(descriptor_model.get("path") or "model/robot.xml")
    asset_value = _public_path((package_root / model_path).resolve())
    robot_id = str(contract.get("robot_id") or descriptor.get("package_id") or package_root.name)
    # 磁盘 manifest 的 capabilities 是增量真值：合并去重（内置 descriptor 可能滞后）
    manifest_capabilities: list[str] = []
    manifest_path = package_root / "robot_package.json"
    if manifest_path.exists():
        manifest = _read_json(manifest_path) or {}
        manifest_capabilities = [str(x) for x in (manifest.get("capabilities") or [])]
    capabilities = list(dict.fromkeys([*(descriptor.get("capabilities") or []), *manifest_capabilities])) or ["generic_mjlab"]
    return {
        "schema_version": "robot-package-1.0",
        "source": "workspace" if source_priority else "bundled",
        "robot_id": robot_id,
        "package_id": str(descriptor.get("package_id") or robot_id),
        "family": contract.get("family", package_root.name),
        "size_class": contract.get("size_class", "M"),
        "locomotion_type": contract.get("locomotion_type", "P"),
        "dof": len(contract.get("joints", {}).get("actuated_joints", [])),
        "mass_kg": _package_mass_kg(contract, package_root),
        "contract_id": contract.get("contract_id"),
        "contract_path": _public_path(contract_path),
        "asset_path": asset_value,
        "training_config": _read_json(training_path) if training_path.exists() else {},
        "simulation_config": _read_json(simulation_path) if simulation_path.exists() else {},
        # D8：电机面板的物理事实改由契约真值 单一真值供给（与浏览器载荷同源同形状）。
        # 此前工作台读 simulation_config.stiffness/damping/...，而 B3 已把这组键从
        # sim config 移除——不切源，网格会变空（且 armature 从来读不到）。
        "physics": _physics_view(package_root),
        # D10：「动作缩放」卡片（标量 + 逐部位/逐关节）
        "action_scale": _action_scale_view(package_root),
        # P1：T-N 曲线（电机参数页签「高级参数」区，声明≠生效）
        "t_n_curve": _t_n_curve_view(package_root),
        "training_profiles": profiles,
        "runtime_requirements": descriptor.get("runtime_requirements", {}),
        "source_runtime": descriptor.get("source_runtime", {}),
        "contract": contract,
        "robot_package": {**descriptor, "capabilities": capabilities, "package_root": str(package_root), "contract_path": descriptor.get("contract_path", "contract_legacy_v2.json"), "model": descriptor_model or {"format": "mjcf", "path": "model/robot.xml", "assets_path": "model/assets"}, "training_config_path": descriptor.get("training_config_path", "training/config.json"), "simulation_config_path": descriptor.get("simulation_config_path", "simulation/config.json")},
        # D7：契约真值 的构型语义（形态/角色/执行器类型/足型/轮组）
        "morphology": _morphology_view(package_root),
    }



def _morphology_view(package_root: Path) -> dict[str, Any]:
    """D7：契约真值 的构型语义视图（形态 / 角色 / 执行器类型 / 足型 / 轮组）。

    真值在包内 ``contract.json`` 的 ``morphology`` 块 —— **不是** v2 ``contract_legacy_v2.json``
    （v2 无 morphology；``_build_record`` 的 ``contract`` 字段用的正是 v2，故此前 UI 看不到
    构型语义）。原样透传 morphology 块，并派生 ``roles``（leg_pattern + extra_roles 去重）与
    ``wheel_count``，供资产页卡片直接渲染。

    契约缺失时返回 ``{"source": "missing"}`` 的显式空视图（面板提示"未声明"而非显示空）；
    读取本身出错才返回 ``{}``——单包契约问题不该让整个包索引构建失败。
    """
    try:
        v3_path = package_root / "contract.json"
        if not v3_path.exists():
            return {"source": "missing"}
        v3 = json.loads(v3_path.read_text(encoding="utf-8-sig"))
        morphology = dict(v3.get("morphology") or {})
        leg_pattern = [str(r) for r in (morphology.get("leg_pattern") or [])]
        extra_roles = [str(r) for r in (morphology.get("extra_roles") or [])]
        roles: list[str] = []
        for role in [*leg_pattern, *extra_roles]:
            if role not in roles:
                roles.append(role)
        wheel_indices = morphology.get("wheel_indices") or []
        return {
            "source": "contract",
            **morphology,
            "roles": roles,
            "wheel_count": len(wheel_indices),
        }
    except Exception:
        return {}


def _physics_view(package_root: Path) -> dict[str, Any]:
    """D8：契约真值 派生的物理事实视图（与浏览器 payload 同源、同形状）。

    键：``stiffness`` / ``damping`` / ``torque_limits`` / ``armature`` / ``frictionloss``
    （每项都是 角色键 + 逐关节键 + ``joint`` 兜底）。

    契约缺失时返回 ``source="missing"`` 的**显式空视图**（面板据此提示"未声明"，
    而不是悄悄显示 0）；仅当读取过程本身出错才返回 ``{}``——单包契约问题不该让整个
    包索引构建失败。
    """
    try:
        from contracts.physics_binding import payload_physics_view, physics_facts

        facts = physics_facts(package_root)
        view = dict(payload_physics_view(facts))
        view["source"] = facts.get("source")
        view["needs_migration"] = bool(facts.get("needs_migration"))
        return view
    except Exception:
        return {}


def _action_scale_view(package_root: Path) -> dict[str, Any]:
    """D10：「动作缩放」卡片的数据源（契约真值 单一真值）。

    复用 :func:`contracts.physics_binding.payload_action_scale_view` —— 与浏览器
    载荷**同一实现**，避免 UI 与仿真出现两套展开口径（B5/2 起 action_scale 的
    唯一真值在契约：标量 ``action.action_scale`` + ``actuator_profile`` 分层）。

    契约缺失返回 ``{}``（面板显式提示"仅显示标量缺省"，不静默用 0.25 冒充已声明）。
    """
    try:
        from contracts.physics_binding import action_scale_facts, payload_action_scale_view

        v3_path = package_root / "contract.json"
        if not v3_path.exists():
            return {}
        v3 = json.loads(v3_path.read_text(encoding="utf-8-sig"))
        view = dict(payload_action_scale_view(action_scale_facts(v3)))
        view["source"] = "contract"
        return view
    except Exception:
        return {}


def _t_n_curve_view(package_root: Path) -> dict[str, Any]:
    """P1：T-N 曲线（高级参数）面板的数据源（契约真值 单一真值）。

    * ``actuator_model``：``ideal_pd``（缺省，**T-N 曲线一律不生效**）/ ``dc_motor``；
    * ``by_role`` / ``by_joint``：折线点列；``text_by_*``：面板紧凑文本（``rpm:扭矩``）；
    * ``derived``：折算出的 DC 标量（saturation_effort / velocity_limit_rad_s）——面板
      显示"填了这条曲线会得到什么"，避免用户只看曲线不知后果。

    曲线非法（非单调等）时返回 ``{"error": ...}`` 而不是空字典：**坏数据要看得见**。
    """
    try:
        from contracts.physics_binding import t_n_curve_facts, format_tn_curve_text

        facts = t_n_curve_facts(package_root)
        view = dict(facts)
        view["text_by_role"] = {
            role: format_tn_curve_text(points) for role, points in (facts.get("by_role") or {}).items()
        }
        view["text_by_joint"] = {
            joint: format_tn_curve_text(points) for joint, points in (facts.get("by_joint") or {}).items()
        }
        return view
    except Exception as exc:  # noqa: BLE001  坏 T-N 曲线不该让整条记录构建失败，但要显式暴露
        return {
            "error": str(exc),
            "actuator_model": "ideal_pd",
            "declared": False,
            "by_role": {},
            "by_joint": {},
            "derived": {},
        }


_MJCF_MASS_CACHE: dict[str, tuple[float, float]] = {}


def _mjcf_total_mass(mjcf_path: Path) -> float:
    """Sum inertial masses of a package MJCF without importing mujoco."""
    import re as _re
    stat = mjcf_path.stat()
    key = f"{mjcf_path}:{stat.st_mtime_ns}"
    cached = _MJCF_MASS_CACHE.get(key)
    if cached:
        return cached[0]
    total = 0.0
    try:
        text = mjcf_path.read_text(encoding="utf-8-sig")
        for match in _re.finditer(r'<inertial[^>]*mass="([0-9.eE+-]+)"', text):
            total += float(match.group(1))
    except (OSError, ValueError):
        total = 0.0
    _MJCF_MASS_CACHE[key] = (total, stat.st_mtime_ns)
    return total


def _package_mass_kg(contract: dict, package_root: Path) -> float:
    """Declared contract mass, with an MJCF inertial-sum fallback for 0/None."""
    declared = (contract.get("urdf") or {}).get("total_mass_kg") or 0.0
    if float(declared) > 0.0:
        return float(declared)
    model_rel = ((contract.get("robot_package") or {}).get("model") or {}).get("path") or contract.get("model_path")
    if not model_rel:
        return 0.0
    try:
        return round(_mjcf_total_mass(package_root / model_rel), 3)
    except (OSError, ValueError):
        return 0.0


def _scan_package_records() -> list[dict[str, Any]]:
    """Full filesystem scan + build of every package record.

    Used to bootstrap the index (first run) and by the explicit
    ``rebuild_package_index`` refresh.  Normal list/query reads do NOT call
    this and never touch the filesystem.
    """
    workspace_root = _workspace_root()
    # Persisted packages are authoritative. The source asset tree is only a
    # migration fallback for installations created before package discovery.
    roots = [workspace_root / "packages", ROOT / "assets" / "robots"]
    _sync_shipped_packages_into_workspace(roots)
    result: list[dict[str, Any]] = []
    # A package may exist both in the persisted workspace and in the shipped
    # assets tree. Prefer the persisted copy when it is complete; otherwise
    # fall back to the shipped package (for example, an older workspace copy
    # created before Go2 profiles were added).
    candidates: list[tuple[Path, int, dict[str, Any], dict[str, Any]]] = []
    for source_priority, root in enumerate(reversed(roots)):
        if not root.exists():
            continue
        for package_root in sorted(root.iterdir()):
            if not package_root.is_dir():
                continue
            contract_path = package_root / "contract_legacy_v2.json"
            descriptor_path = package_root / "robot_package.json"
            if not contract_path.exists() or not descriptor_path.exists():
                continue
            contract = _read_json(contract_path)
            descriptor = _read_json(descriptor_path)
            if not contract or not descriptor:
                continue
            candidates.append((package_root, source_priority, contract, descriptor))

    def candidate_score(item: tuple[Path, int, dict[str, Any], dict[str, Any]]) -> tuple[int, int, int, int]:
        path, source_priority, contract, descriptor = item
        robot_id = str(contract.get("robot_id") or descriptor.get("package_id") or path.name)
        completeness = (
            int((path / "training" / "profiles").exists()) * 4
            + int((path / "training" / "source").exists()) * 2
            + int(bool(descriptor.get("extension_entrypoint")))
        )
        try:
            modified = (path / "robot_package.json").stat().st_mtime_ns
        except OSError:
            modified = 0
        return source_priority, int(path.name == robot_id), completeness, modified

    selected: dict[str, tuple[Path, int, dict[str, Any], dict[str, Any]]] = {}
    for item in candidates:
        package_root, _, contract, descriptor = item
        robot_id = str(contract.get("robot_id") or descriptor.get("package_id") or package_root.name)
        current = selected.get(robot_id)
        if current is None or candidate_score(item) > candidate_score(current):
            selected[robot_id] = item

    for robot_id, (package_root, source_priority, contract, descriptor) in selected.items():
        result.append(_build_record(package_root, source_priority, contract, descriptor))
    result.sort(key=lambda item: (str(item.get("family", "")).casefold(), item["robot_id"]))
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_robot_packages() -> list[dict[str, Any]]:
    """Return the list of known robot packages.

    Reads the persistent workspace index — a single JSON load, not a
    filesystem scan.  Before reading, a cheap freshness signature over both
    package roots is compared against the index meta: any package added /
    edited / deleted on disk (shipped tree or workspace) auto-refreshes the
    index, so new robots always surface without manual rebuilds.
    """
    global _INDEX_CACHE
    workspace_key = str(_workspace_root())
    with _INDEX_CACHE_LOCK:
        cached = _INDEX_CACHE
    if cached is not None and cached[0] == workspace_key:
        return [dict(item) for item in cached[1]]
    records = _read_index()
    signature = _package_signature()
    if not records or _index_is_stale():
        # Bootstrap (fresh install) or on-disk changes since the last index
        # write: rebuild from disk so reality always wins over the index.
        records = _scan_package_records()
        if records or not _read_index():
            _write_index(records)
        # 扫描中的内容同步可能已改动受签名覆盖的文件（profiles 目录等），
        # 以扫描后的磁盘状态写入 meta，避免下一次读取立刻再重建一遍。
        signature = _package_signature()
        _write_index_meta(signature)
    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE = (workspace_key, [dict(item) for item in records])
    return [dict(item) for item in records]


def upsert_package(package_root: Path, source: str = "workspace") -> str | None:
    """Add or refresh a single package in the persistent index.

    Returns the package's ``robot_id``, or ``None`` if the directory is not a
    valid package (missing contract/descriptor).  This is the single write
    hook used by package import/save operations.
    """
    package_root = Path(package_root).resolve()
    contract_path = package_root / "contract_legacy_v2.json"
    descriptor_path = package_root / "robot_package.json"
    if not contract_path.exists() or not descriptor_path.exists():
        return None
    contract = _read_json(contract_path)
    descriptor = _read_json(descriptor_path)
    if not contract or not descriptor:
        return None
    source_priority = 0 if source == "bundled" else 1
    record = _build_record(package_root, source_priority, contract, descriptor)
    robot_id = record["robot_id"]
    if not robot_id:
        return None
    records = _read_index()
    records = [item for item in records if str(item.get("robot_id")) != robot_id]
    records.append(record)
    records.sort(key=lambda item: (str(item.get("family", "")).casefold(), item["robot_id"]))
    _write_index(records)
    return robot_id


def remove_package(robot_id: str) -> bool:
    """Remove a package from the persistent index by ``robot_id``."""
    if not robot_id:
        return False
    records = _read_index()
    remaining = [item for item in records if str(item.get("robot_id")) != robot_id]
    if len(remaining) == len(records):
        return False
    _write_index(remaining)
    return True


def sync_referenced_blobs(shipped_dir: Path, target_dir: Path) -> list[str]:
    """把副本 ``simulation/config.json`` **引用的**、却在副本里缺失的文件从源包补上。

    为什么按"引用"补、而不是按目录补：`deploy/` 这类目录**不在** ``simulation/`` 下，
    C6 的"补缺"规则覆盖不到它 —— 而 policy 的 ``path`` 完全可以指向那里
    （``wuji_hand`` 就是 `deploy/reorient-v2026.5.29/policy.onnx`）。结果副本留下
    "config 指向一个不存在的 onnx"：**运行时就 404**，发布门禁（``scripts/release-check.js``
    的 workspace 段）也会红。按引用补 = 恰好补到"能让 config 自洽"的那几个文件，
    既不搬整棵运行产物目录，也不漏。

    安全：只接受**相对路径**且不含 ``..``（副本可能来自历史/外部，路径不可信）；
    **源包也没有的文件不伪造** —— 照样缺着，让门禁与运行时如实报出来。
    返回补齐的相对路径列表。
    """
    import shutil

    config_path = target_dir / "simulation" / "config.json"
    if not config_path.is_file():
        return []
    config = _read_json(config_path)
    entries: list[dict] = []
    for key in ("policies", "demo_policies"):
        items = config.get(key)
        if isinstance(items, list):
            entries.extend(item for item in items if isinstance(item, dict))

    restored: list[str] = []
    for entry in entries:
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            continue
        if ".." in Path(relative).parts:
            continue
        dst_file = target_dir / relative
        if dst_file.exists():
            continue
        src_file = shipped_dir / relative
        if not src_file.is_file():
            continue  # 源包也没有 → 不伪造，让门禁如实报缺
        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
        except OSError:
            continue
        restored.append(Path(relative).as_posix())
    return restored


def _sync_shipped_packages_into_workspace(roots: list[Path]) -> int:
    """内置包 → workspace 副本的单向内容同步（refresh 时执行）。

    背景：运行时读取 workspace/packages/<id>（持久化权威），但开发期新增的
    profiles/capabilities/bridge 常只落在 assets/robots 源树里——曾因此出现
    capabilities 丢失、新 profile 不可见两类事故。这里把源树新增/更新的**内容文件**
    （profiles、bridge、schema 配置）单向复制过去；workspace 独有的运行产物
    （logs、模型、checkpoint）永不触碰。返回同步的文件数。

    C6 补齐（v0.42.0）：workspace 副本缺基础文件时从源树补——
    - ``simulation/`` 下缺失的文件（scene.xml、策略 onnx 等）按缺复制；
      workspace 独有文件（训练导出的策略等）不清理；
    - ``simulation/config.json`` 只做**增量合并**：源树新增的键（如后加的
      policies/demo_policies 声明段）并入副本，副本已有的键一律不动——
      用户在工作台改过的增益等以 workspace 为权威。曾因副本缺 policies
      声明导致 lite3 演示策略从首页消失。
    """
    import shutil

    shipped_root = ROOT / "assets" / "robots"
    packages_root = roots[0]  # already the workspace/packages directory
    synced = 0
    if not shipped_root.exists():
        return 0
    for shipped in sorted(shipped_root.iterdir()):
        if not shipped.is_dir():
            continue
        target = packages_root / shipped.name
        # B36：判据从「target/contract_legacy_v2.json 在」放宽为「target 是包副本」——以
        # robot_package.json（副本标记）为准。contract_legacy_v2.json 被误删的**残缺副本**
        # 也参与同步，由下面的契约镜像补齐、顺势治愈（原判据会让残缺副本永远
        # 无法自愈、静默回落源树，副本从此成僵尸残留）。纯 logs/checkpoint 之类
        # 残留目录（无 robot_package.json 标记）仍跳过，不制造假副本。
        if not target.is_dir() or not (target / "robot_package.json").exists():
            continue  # workspace 没有该包副本，让正常扫描直接用源树
        # 只同步"内容"子树，避开 logs/checkpoints 等运行产物
        for relative_root in ("training/profiles", "training/source"):
            src_dir = shipped / relative_root
            if not src_dir.exists():
                continue
            dst_dir = target / relative_root
            # 源树已删除的副本文件（如废弃的 profile）同步清除，保证
            # workspace 副本与源树的内容集合一致，不残留陈旧的训练入口。
            if dst_dir.is_dir():
                src_rel = {str(p.relative_to(src_dir)) for p in src_dir.rglob("*") if p.is_file()}
                for stale in dst_dir.rglob("*"):
                    if not stale.is_file() or "__pycache__" in stale.parts:
                        continue
                    rel = str(stale.relative_to(dst_dir))
                    if rel not in src_rel:
                        stale.unlink()
                        synced += 1
            for src_file in src_dir.rglob("*"):
                if not src_file.is_file() or "__pycache__" in src_file.parts:
                    continue
                dst_file = dst_dir / src_file.relative_to(src_dir)
                try:
                    if (not dst_file.exists()
                            or src_file.stat().st_size != dst_file.stat().st_size
                            or int(src_file.stat().st_mtime) > int(dst_file.stat().st_mtime)):
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        synced += 1
                except OSError:
                    continue
        # C6：simulation/ 基础文件补齐——只补缺，不覆盖、不清理。
        src_sim = shipped / "simulation"
        if src_sim.is_dir():
            for src_file in sorted(src_sim.rglob("*")):
                if not src_file.is_file() or "__pycache__" in src_file.parts:
                    continue
                relative = src_file.relative_to(src_sim)
                dst_file = target / "simulation" / relative
                if relative.as_posix() == "config.json":
                    if not dst_file.exists():
                        # 整文件缺失：无用户编辑可保留，整份复制
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(src_file, dst_file)
                            synced += 1
                        except OSError:
                            pass
                        continue
                    # 文件存在：增量合并——副本已有的键不动（用户编辑权威），
                    # 源树新增的键并入（声明段如 policies/demo_policies 可达）
                    src_cfg = _read_json(src_file)
                    dst_cfg = _read_json(dst_file)
                    added = {key: value for key, value in src_cfg.items() if key not in dst_cfg}
                    if added:
                        dst_cfg.update(added)
                        try:
                            dst_file.write_text(
                                json.dumps(dst_cfg, ensure_ascii=False, indent=2) + chr(10),
                                encoding="utf-8",
                            )
                            synced += 1
                        except (OSError, ValueError):
                            pass
                    continue
                if not dst_file.exists():
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(src_file, dst_file)
                        synced += 1
                    except OSError:
                        continue
        # `deploy/` 等**不在 simulation/ 下**的引用文件：按 config 的 `path` 引用补齐
        # （C6 只管 simulation/ 子树，管不到 deploy/ —— wuji_hand 的策略就在那里，
        # 副本缺它会让运行时 404、发布门禁红）。
        synced += len(sync_referenced_blobs(shipped, target))
        # 顶层 JSON 声明以源树为准：新增/变更字段覆盖过去，源树已删除的
        # 字段（如移除的 extension_entrypoint）也从副本里清除，避免 stale
        # workspace 副本用旧的扩展入口遮蔽源树更新。
        src_manifest = shipped / "robot_package.json"
        dst_manifest = target / "robot_package.json"
        if src_manifest.exists() and dst_manifest.exists():
            try:
                src_data = _read_json(src_manifest) or {}
                dst_data = _read_json(dst_manifest) or {}
                changed = False
                for key in ("capabilities", "display_name", "notes"):
                    if src_data.get(key) and dst_data.get(key) != src_data[key]:
                        merged = list(dict.fromkeys([*(dst_data.get(key) or []), *src_data[key]])) if key == "capabilities" else src_data[key]
                        if dst_data.get(key) != merged:
                            dst_data[key] = merged
                            changed = True
                for key in ("extension_entrypoint", "extension_root", "source_project"):
                    if dst_data.get(key) != src_data.get(key):
                        if src_data.get(key) is None:
                            dst_data.pop(key, None)
                        else:
                            dst_data[key] = src_data[key]
                        changed = True
                if changed:
                    dst_manifest.write_text(json.dumps(dst_data, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
                    synced += 1
            except (OSError, ValueError):
                pass
        # B36：v2 contract_legacy_v2.json 与 contract.json 同为**随包分发的契约/派生文件**——
        # 契约副本不得独立演化出第二套真值。运行时预设链（create 校验等）对已有
        # workspace 副本的包以**副本**为权威：镜像集若只有 contract.json（D7），
        # assets 侧对 v2 的修复（如 B29 wuji_hand observation.dimension 0→69）对存量
        # 安装不生效，被旧副本静默遮蔽（wuji_hand 现场实证：修复后首次 create 仍 400，
        # 手动用源树覆盖副本 + 重启后才 200）。照 D7 同一先例：全量覆盖（非合并）+
        # 内容级比较（一致不重写）+ OSError 容错。
        src_contract = shipped / "contract_legacy_v2.json"
        dst_contract = target / "contract_legacy_v2.json"
        if src_contract.exists():
            try:
                if (not dst_contract.exists()
                        or src_contract.read_text(encoding="utf-8-sig") != dst_contract.read_text(encoding="utf-8-sig")):
                    shutil.copy2(src_contract, dst_contract)
                    synced += 1
            except OSError:
                pass
        # D7：契约真值 是机器人生理学的**单一真值**（B2/B5），内置包的 workspace 副本应
        # **镜像源树**——副本曾因不同步 contract.json 而缺 actuator_type/foot_type/
        # wheel_indices（B4 后加的字段），导致 morphology 视图缺字段。全量覆盖（非合并）：
        # 契约不允许"副本独立演化"出第二套真值（与 robot_package.json 的字段合并不同）。
        src_v3 = shipped / "contract.json"
        dst_v3 = target / "contract.json"
        if src_v3.exists():
            try:
                if (not dst_v3.exists()
                        or src_v3.read_text(encoding="utf-8-sig") != dst_v3.read_text(encoding="utf-8-sig")):
                    shutil.copy2(src_v3, dst_v3)
                    synced += 1
            except OSError:
                pass
        # B13：training/config.json 已收口为**指针文件**（robot_id/contract_path/
        # profile_id/schema_version/backend，尺子 = tools/audit_training_config_layers.py），
        # 是随包分发的派生物而非用户编辑面——任务真值在 profiles/（Recipe 层），
        # 运行真值在 Run（B9），无任何代码读它的任务字段。副本同样**镜像源树**（D7 同一
        # 先例，全量覆盖非合并）：否则旧安装副本会永远保留已删除的 terrain/reward_scales
        # 等陈旧任务字段，演化出第二套真值。
        src_tcfg = shipped / "training" / "config.json"
        dst_tcfg = target / "training" / "config.json"
        if src_tcfg.exists():
            try:
                if not dst_tcfg.parent.exists():
                    dst_tcfg.parent.mkdir(parents=True, exist_ok=True)
                if (not dst_tcfg.exists()
                        or src_tcfg.read_text(encoding="utf-8-sig") != dst_tcfg.read_text(encoding="utf-8-sig")):
                    shutil.copy2(src_tcfg, dst_tcfg)
                    synced += 1
            except OSError:
                pass
    if synced:
        print(f"[robot_packages] synced {synced} content file(s) from shipped assets into workspace")
    return synced


def rebuild_package_index() -> list[dict[str, Any]]:
    """Rescan the filesystem and rewrite the persistent index.

    Intended for an explicit "refresh packages" action (or first-run
    bootstrap).  Normal reads never trigger a scan.
    """
    records = _scan_package_records()
    _write_index(records)
    return [dict(item) for item in records]


def invalidate_package_cache() -> None:
    """Compatibility hook — clear the in-memory mirror of the index.

    The next read reloads from the persistent index file.  Note that package
    import/save/delete should call ``upsert_package``/``remove_package`` so
    the persistent index stays in sync; this hook only drops the in-memory
    copy.
    """
    global _INDEX_CACHE
    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE = None
