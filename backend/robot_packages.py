"""Robot package discovery and persistent index shared by all entry points."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from backend.jsonio import read_json
from backend.package_records import build_package_record, package_completeness
from backend.package_sync import package_signature, sync_shipped_packages
from backend.paths import workspace_root as _workspace_root


ROOT = Path(__file__).resolve().parents[1]
_INDEX_FILENAME = "package_index.json"
_INDEX_META_FILENAME = "package_index.meta.json"
_INDEX_CACHE: Any = None
_INDEX_CACHE_LOCK = threading.Lock()


def _read_json(path: Path) -> dict[str, Any]:
    return read_json(path, default={}, require=dict)


def package_for_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Locate the package owning a contract, including incomplete legacy copies."""
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
    package_id_hint = str(contract.get("robot_id") or package_path.name)
    shipped = ROOT / "assets" / "robots" / package_id_hint
    if shipped.is_dir() and (shipped / "robot_package.json").exists():
        shipped_descriptor = _read_json(shipped / "robot_package.json")
        if package_completeness(shipped, shipped_descriptor) > package_completeness(package_path, descriptor):
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
    return {**descriptor, **result}


def robot_package_root(robot_id: str) -> Path:
    """宽容定位：沿用统一解析规则，失败时返回内置候选路径，由调用方判断是否存在。"""
    try:
        from backend.package_locator import resolve_package_root

        candidate = resolve_package_root(robot_id)
        if candidate.is_dir():
            return candidate
    except Exception:  # 预设不可用时仍保留调用方的目录级回退。
        pass
    return ROOT / "assets" / "robots" / robot_id


def _index_path() -> Path:
    return _workspace_root() / _INDEX_FILENAME


def _index_meta_path() -> Path:
    return _workspace_root() / _INDEX_META_FILENAME


def _package_roots() -> list[Path]:
    return [_workspace_root() / "packages", ROOT / "assets" / "robots"]


def _package_signature() -> str:
    return package_signature(_package_roots())


def _index_is_stale(signature: str | None = None) -> bool:
    meta = _read_json(_index_meta_path())
    if not meta:
        return True
    if signature is None:
        signature = _package_signature()
    return meta.get("signature") != signature


def _write_index_meta(signature: str) -> None:
    import time

    path = _index_meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"signature": signature, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False), encoding="utf-8")


def _read_index() -> list[dict[str, Any]]:
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
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    global _INDEX_CACHE
    _INDEX_CACHE = (str(_workspace_root()), [dict(item) for item in records])


def _scan_package_records() -> list[dict[str, Any]]:
    roots = _package_roots()
    sync_shipped_packages(roots[1], roots[0])
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
        try:
            modified = (path / "robot_package.json").stat().st_mtime_ns
        except OSError:
            modified = 0
        return source_priority, int(path.name == robot_id), package_completeness(path, descriptor), modified

    selected: dict[str, tuple[Path, int, dict[str, Any], dict[str, Any]]] = {}
    for item in candidates:
        package_root, _, contract, descriptor = item
        robot_id = str(contract.get("robot_id") or descriptor.get("package_id") or package_root.name)
        current = selected.get(robot_id)
        if current is None or candidate_score(item) > candidate_score(current):
            selected[robot_id] = item
    result = [
        build_package_record(package_root, source_priority, contract, descriptor, repo_root=ROOT)
        for package_root, source_priority, contract, descriptor in selected.values()
    ]
    result.sort(key=lambda item: (str(item.get("family", "")).casefold(), item["robot_id"]))
    return result


def list_robot_packages() -> list[dict[str, Any]]:
    """Load the workspace index, synchronizing packages only when it is stale."""
    global _INDEX_CACHE
    workspace_key = str(_workspace_root())
    with _INDEX_CACHE_LOCK:
        cached = _INDEX_CACHE
    if cached is not None and cached[0] == workspace_key:
        return [dict(item) for item in cached[1]]
    records = _read_index()
    signature = _package_signature()
    if not records or _index_is_stale(signature):
        records = _scan_package_records()
        if records or not _read_index():
            _write_index(records)
        # 同步可能改动被签名覆盖的文件，元数据必须反映同步后的磁盘状态。
        _write_index_meta(_package_signature())
    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE = (workspace_key, [dict(item) for item in records])
    return [dict(item) for item in records]


def upsert_package(package_root: Path, source: str = "workspace") -> str | None:
    """Refresh one valid package in the index; return its robot id or None."""
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
    record = build_package_record(package_root, source_priority, contract, descriptor, repo_root=ROOT)
    robot_id = record["robot_id"]
    if not robot_id:
        return None
    records = [item for item in _read_index() if str(item.get("robot_id")) != robot_id]
    records.append(record)
    records.sort(key=lambda item: (str(item.get("family", "")).casefold(), item["robot_id"]))
    _write_index(records)
    return robot_id


def remove_package(robot_id: str) -> bool:
    """Remove a package from the persistent index by robot id."""
    if not robot_id:
        return False
    records = _read_index()
    remaining = [item for item in records if str(item.get("robot_id")) != robot_id]
    if len(remaining) == len(records):
        return False
    _write_index(remaining)
    return True


def rebuild_package_index() -> list[dict[str, Any]]:
    """Synchronize packages and rebuild the index and its freshness metadata."""
    records = _scan_package_records()
    _write_index(records)
    _write_index_meta(_package_signature())
    return [dict(item) for item in records]


def invalidate_package_cache() -> None:
    """Discard the memory mirror; the next read checks the persistent index."""
    global _INDEX_CACHE
    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE = None
