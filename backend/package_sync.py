"""Shipped-package signatures and one-way synchronization of existing copies."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from backend.jsonio import dumps, read_json

#: 同步语义版本：改了"副本该跟源树一致的内容集合"就 +1（否则已装副本不会重扫）。
#: 7 = `model.training_path`（训练资产声明）也要镜像。
SYNC_REVISION = "7"
_POLICY_LIST_KEYS = ("policies", "demo_policies")


def _file_signature(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return "-"
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def _tree_digest(directory: Path) -> str:
    if not directory.is_dir():
        return "-"
    hasher = hashlib.sha1()
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            info = path.stat()
        except OSError:
            continue
        line = f"{path.relative_to(directory).as_posix()}:{info.st_size}:{info.st_mtime_ns}\n"
        hasher.update(line.encode("utf-8"))
    return hasher.hexdigest()[:16]


def package_signature(roots: list[Path]) -> str:
    """Return the legacy freshness signature, preserving the supplied root order."""
    parts: list[str] = [f"sync_rev:{SYNC_REVISION}"]
    for root in roots:
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
                try:
                    parts.append(f"{name}/{rel}:{int((pkg / rel).stat().st_mtime_ns)}")
                except OSError:
                    parts.append(f"{name}/{rel}:-")
            for rel in ("model", "training/profiles", "training/source"):
                parts.append(f"{name}/{rel}@{_tree_digest(pkg / rel)}")
            for rel in ("simulation/config.json", "training/config.json"):
                parts.append(f"{name}/{rel}@{_file_signature(pkg / rel)}")
    return "|".join(parts)


def _remove_stale_files(source: Path, target: Path, *, skip_source_cache: bool = False) -> int:
    if not target.is_dir():
        return 0
    source_paths = {
        str(path.relative_to(source)) for path in source.rglob("*")
        if path.is_file() and (not skip_source_cache or "__pycache__" not in path.parts)
    }
    removed = 0
    for stale in target.rglob("*"):
        if not stale.is_file() or "__pycache__" in stale.parts:
            continue
        if str(stale.relative_to(target)) not in source_paths:
            stale.unlink()
            removed += 1
    return removed


def _copy_changed_files(source: Path, target: Path, *, sort_files: bool = False) -> int:
    files = source.rglob("*")
    copied = 0
    for src_file in sorted(files) if sort_files else files:
        if not src_file.is_file() or "__pycache__" in src_file.parts:
            continue
        dst_file = target / src_file.relative_to(source)
        try:
            if (not dst_file.exists()
                    or src_file.stat().st_size != dst_file.stat().st_size
                    or int(src_file.stat().st_mtime) > int(dst_file.stat().st_mtime)):
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1
        except OSError:
            continue
    return copied


def _mirror_text_files(
    source: Path, target: Path, relatives: tuple[str, ...], *, create_parent: bool = False,
) -> int:
    copied = 0
    for relative in relatives:
        src_file, dst_file = source / relative, target / relative
        if not src_file.exists():
            continue
        try:
            if create_parent and not dst_file.parent.exists():
                dst_file.parent.mkdir(parents=True, exist_ok=True)
            if (not dst_file.exists()
                    or src_file.read_text(encoding="utf-8-sig") != dst_file.read_text(encoding="utf-8-sig")):
                shutil.copy2(src_file, dst_file)
                copied += 1
        except OSError:
            pass
    return copied


def _merge_simulation_config(source: Path, target: Path) -> int:
    incoming = read_json(source, default={}, require=dict)
    current = read_json(target, default={}, require=dict)
    changed = False
    for key, value in incoming.items():
        if key not in current:
            current[key] = value
            changed = True
            continue
        if key not in _POLICY_LIST_KEYS:
            continue
        existing = current[key]
        if not isinstance(existing, list) or not isinstance(value, list):
            continue
        known_ids = {
            item.get("id") for item in existing
            if isinstance(item, dict) and item.get("id")
        }
        appended = [
            item for item in value
            if isinstance(item, dict) and item.get("id") and item["id"] not in known_ids
        ]
        if appended:
            current[key] = existing + appended
            changed = True
    if changed:
        try:
            target.write_text(dumps(current), encoding="utf-8")
            return 1
        except (OSError, ValueError):
            pass
    return 0


def _backfill_simulation(source: Path, target: Path) -> int:
    if not source.is_dir():
        return 0
    synced = 0
    for src_file in sorted(source.rglob("*")):
        if not src_file.is_file() or "__pycache__" in src_file.parts:
            continue
        relative = src_file.relative_to(source)
        dst_file = target / relative
        if dst_file.exists():
            if relative.as_posix() == "config.json":
                synced += _merge_simulation_config(src_file, dst_file)
            continue
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src_file, dst_file)
            synced += 1
        except OSError:
            continue
    return synced


def sync_referenced_blobs(shipped_dir: Path, target_dir: Path) -> list[str]:
    """Backfill missing relative policy references only when the shipped file exists."""
    config_path = target_dir / "simulation" / "config.json"
    if not config_path.is_file():
        return []
    config = read_json(config_path, default={}, require=dict)
    entries: list[dict] = []
    for key in _POLICY_LIST_KEYS:
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
            continue
        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
        except OSError:
            continue
        restored.append(Path(relative).as_posix())
    return restored


def _merge_manifest(source: Path, target: Path) -> int:
    if not source.exists() or not target.exists():
        return 0
    try:
        incoming = read_json(source, default={}, require=dict) or {}
        current = read_json(target, default={}, require=dict) or {}
        changed = False
        for key in ("capabilities", "display_name", "notes"):
            if incoming.get(key) and current.get(key) != incoming[key]:
                merged = (list(dict.fromkeys([*(current.get(key) or []), *incoming[key]]))
                          if key == "capabilities" else incoming[key])
                if current.get(key) != merged:
                    current[key] = merged
                    changed = True
        for key in ("extension_entrypoint", "extension_root", "source_project"):
            if current.get(key) != incoming.get(key):
                if incoming.get(key) is None:
                    current.pop(key, None)
                else:
                    current[key] = incoming[key]
                changed = True
        # **训练资产声明**（`model.training_path`）是出厂事实，与 `extension_*` 同级：
        # 运行时包根是副本，副本清单缺这条声明 ⇒ 训练侧装配退回 `model.path`，
        # 拿上游那份 MJCF 去撞族约定（go2：足端几何名不含 `foot` 直接判红）。
        # 只同步这一个键 —— `model.path` / `assets_path` 仍归副本自己（导入包会改写它们）。
        incoming_model = incoming.get("model") if isinstance(incoming.get("model"), dict) else {}
        declared_training = (incoming_model or {}).get("training_path")
        if isinstance(current.get("model"), dict) and current["model"].get("training_path") != declared_training:
            if declared_training is None:
                current["model"].pop("training_path", None)
            else:
                current["model"]["training_path"] = declared_training
            changed = True
        if changed:
            target.write_text(dumps(current), encoding="utf-8")
            return 1
    except (OSError, ValueError):
        pass
    return 0


def sync_shipped_packages(shipped_root: Path, packages_root: Path) -> int:
    """Sync existing marked copies without discovering roots or writing an index."""
    synced = 0
    if not shipped_root.exists():
        return 0
    for shipped in sorted(shipped_root.iterdir()):
        if not shipped.is_dir():
            continue
        target = packages_root / shipped.name
        if not target.is_dir() or not (target / "robot_package.json").exists():
            continue
        # Missing source trees stay untouched; training deletes first, model copies first.
        for relative in ("training/profiles", "training/source"):
            source_tree, target_tree = shipped / relative, target / relative
            if source_tree.exists():
                synced += _remove_stale_files(source_tree, target_tree)
                synced += _copy_changed_files(source_tree, target_tree)
        synced += _backfill_simulation(shipped / "simulation", target / "simulation")
        synced += len(sync_referenced_blobs(shipped, target))
        synced += _merge_manifest(shipped / "robot_package.json", target / "robot_package.json")
        synced += _mirror_text_files(shipped, target, ("contract_legacy_v2.json", "contract.json"))
        source_model, target_model = shipped / "model", target / "model"
        if source_model.is_dir():
            synced += _copy_changed_files(source_model, target_model, sort_files=True)
            synced += _remove_stale_files(source_model, target_model, skip_source_cache=True)
        synced += _mirror_text_files(shipped, target, ("training/config.json",), create_parent=True)
    if synced:
        print(f"[robot_packages] synced {synced} content file(s) from shipped assets into workspace")
    return synced
