"""Package record projections, independent of discovery and index storage."""

from __future__ import annotations

from pathlib import Path

from backend.jsonio import load_json, read_json


def _read_json(path: Path) -> dict:
    return read_json(path, default={}, require=dict)


def _public_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return str(resolved)


def validate_training_profile(profile: dict) -> list[str]:
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


def package_completeness(package_root: Path, descriptor: dict) -> int:
    return (int((package_root / "training" / "profiles").exists()) * 4
            + int((package_root / "training" / "source").exists()) * 2
            + int(bool(descriptor.get("extension_entrypoint"))))


def _morphology_view(truth: dict | None) -> dict:
    if truth is None:
        return {"source": "missing"}
    morphology = dict(truth.get("morphology") or {})
    roles = [str(r) for r in (morphology.get("leg_pattern") or [])]
    roles += [str(r) for r in (morphology.get("extra_roles") or [])]
    return {"source": "contract", **morphology, "roles": list(dict.fromkeys(roles)),
            "wheel_count": len(morphology.get("wheel_indices") or [])}


def _physics_view(package_root: Path, truth: dict | None) -> dict:
    from contracts.physics_binding import facts_from_contract, payload_physics_view, physics_facts

    facts = physics_facts(package_root) if truth is None else facts_from_contract(truth)
    return {**dict(payload_physics_view(facts)), "source": facts.get("source"),
            "needs_migration": bool(facts.get("needs_migration"))}


def _action_scale_view(truth: dict | None) -> dict:
    from contracts.physics_binding import action_scale_facts, payload_action_scale_view

    if truth is None:
        return {}
    return {**dict(payload_action_scale_view(action_scale_facts(truth))), "source": "contract"}


def _t_n_curve_view(package_root: Path, truth: dict | None) -> dict:
    from contracts.physics_binding import t_n_curve_facts, t_n_curve_facts_from_contract, format_tn_curve_text

    facts = t_n_curve_facts(package_root) if truth is None else t_n_curve_facts_from_contract(truth)
    return {**dict(facts), **{
        f"text_by_{kind}": {name: format_tn_curve_text(points)
                            for name, points in (facts.get(f"by_{kind}") or {}).items()}
        for kind in ("role", "joint")
    }}


def _t_n_curve_error(exc: Exception) -> dict:
    return {"error": str(exc), "actuator_model": "ideal_pd", "declared": False,
            "by_role": {}, "by_joint": {}, "derived": {}}


def package_contract_views(package_root: Path) -> dict:
    """Read one contract snapshot; isolate each projection's failures."""
    views = {"physics": {}, "action_scale": {}, "t_n_curve": {}, "morphology": {}}
    try:
        path = package_root / "contract.json"
        truth = None
        if path.exists():
            truth = load_json(path)
            # A present non-object (including JSON null) is not a missing contract.
            truth.get("actuator_profile")
    except Exception as exc:
        views["t_n_curve"] = _t_n_curve_error(exc)
        return views
    for name, project in (
        ("physics", lambda: _physics_view(package_root, truth)),
        ("action_scale", lambda: _action_scale_view(truth)),
        ("t_n_curve", lambda: _t_n_curve_view(package_root, truth)),
        ("morphology", lambda: _morphology_view(truth)),
    ):
        try:
            views[name] = project()
        except Exception as exc:
            views[name] = _t_n_curve_error(exc) if name == "t_n_curve" else {}
    return views


_MJCF_MASS_CACHE: dict[str, tuple[float, float]] = {}


def _mjcf_total_mass(mjcf_path: Path) -> float:
    """Sum inertial masses without importing MuJoCo."""
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


def _training_profiles(package_root: Path, descriptor: dict, repo_root: Path) -> list[dict]:
    profile_dir = package_root / "training" / "profiles"
    raw_profiles = []
    if profile_dir.exists():
        for path in profile_dir.glob("*.json"):
            profile = _read_json(path)
            if profile:
                raw_profiles.append((path, profile))
    raw_profiles.sort(key=lambda item: (item[1].get("sort_order", 1000), item[0].name))
    profiles = []
    for path, profile in raw_profiles:
        errors = validate_training_profile(profile)
        requirements = profile.get("runtime_requirements")
        if not isinstance(requirements, dict):
            requirements = descriptor.get("runtime_requirements", {})
        profiles.append({**profile, "runtime_requirements": requirements,
                         "path": _public_path(path, repo_root), "valid": not errors,
                         "validation_errors": errors})
    return profiles


def build_package_record(package_root: Path, source_priority: int, contract: dict,
                         descriptor: dict, *, repo_root: Path) -> dict:
    profiles = _training_profiles(package_root, descriptor, repo_root)
    descriptor_model = descriptor.get("model", {}) if isinstance(descriptor.get("model"), dict) else {}
    model_path = str(descriptor_model.get("path") or "model/robot.xml")
    asset_value = _public_path((package_root / model_path).resolve(), repo_root)
    robot_id = str(contract.get("robot_id") or descriptor.get("package_id") or package_root.name)
    manifest_capabilities = []
    manifest_path = package_root / "robot_package.json"
    if manifest_path.exists():
        manifest = _read_json(manifest_path) or {}
        manifest_capabilities = [str(x) for x in (manifest.get("capabilities") or [])]
    capabilities = list(dict.fromkeys([*(descriptor.get("capabilities") or []), *manifest_capabilities])) or ["generic_mjlab"]
    training_path = package_root / "training" / "config.json"
    simulation_path = package_root / "simulation" / "config.json"
    views = package_contract_views(package_root)
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
        "contract_path": _public_path(package_root / "contract_legacy_v2.json", repo_root),
        "asset_path": asset_value,
        "training_config": _read_json(training_path) if training_path.exists() else {},
        "simulation_config": _read_json(simulation_path) if simulation_path.exists() else {},
        "physics": views["physics"],
        "action_scale": views["action_scale"],
        "t_n_curve": views["t_n_curve"],
        "training_profiles": profiles,
        "runtime_requirements": descriptor.get("runtime_requirements", {}),
        "source_runtime": descriptor.get("source_runtime", {}),
        "contract": contract,
        "robot_package": {
            **descriptor, "capabilities": capabilities, "package_root": str(package_root),
            "contract_path": descriptor.get("contract_path", "contract_legacy_v2.json"),
            "model": descriptor_model or {"format": "mjcf", "path": "model/robot.xml", "assets_path": "model/assets"},
            "training_config_path": descriptor.get("training_config_path", "training/config.json"),
            "simulation_config_path": descriptor.get("simulation_config_path", "simulation/config.json"),
        },
        "morphology": views["morphology"],
    }
