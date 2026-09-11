#!/usr/bin/env python3
"""Extract MuJoCo-compiled truth facts for URDF dataset validation."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import mujoco


MESH_EXTENSIONS = {
    ".dae",
    ".glb",
    ".gltf",
    ".msh",
    ".obj",
    ".ply",
    ".stl",
    ".xml",
}

GEOM_TYPE_NAMES = {
    int(mujoco.mjtGeom.mjGEOM_PLANE): "plane",
    int(mujoco.mjtGeom.mjGEOM_HFIELD): "hfield",
    int(mujoco.mjtGeom.mjGEOM_SPHERE): "sphere",
    int(mujoco.mjtGeom.mjGEOM_CAPSULE): "capsule",
    int(mujoco.mjtGeom.mjGEOM_ELLIPSOID): "ellipsoid",
    int(mujoco.mjtGeom.mjGEOM_CYLINDER): "cylinder",
    int(mujoco.mjtGeom.mjGEOM_BOX): "box",
    int(mujoco.mjtGeom.mjGEOM_MESH): "mesh",
}

JOINT_TYPE_NAMES = {
    int(mujoco.mjtJoint.mjJNT_FREE): "free",
    int(mujoco.mjtJoint.mjJNT_BALL): "ball",
    int(mujoco.mjtJoint.mjJNT_SLIDE): "slide",
    int(mujoco.mjtJoint.mjJNT_HINGE): "hinge",
}


@dataclass(frozen=True)
class ManifestEntry:
    relative_path: str
    source_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def norm_path(value: str) -> str:
    return os.path.normpath(value).replace("\\", "/")


def read_manifest(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def discover_assets(dataset_root: str, manifest: dict[str, Any]) -> list[str]:
    assets: set[str] = set()
    for raw_path in manifest.get("assetPaths", []):
        absolute_path = raw_path
        if not os.path.isabs(absolute_path):
            absolute_path = os.path.join(dataset_root, raw_path)
        if os.path.isfile(absolute_path):
            assets.add(norm_path(os.path.abspath(absolute_path)))

    for current_root, _dirs, files in os.walk(dataset_root):
        for filename in files:
            if os.path.splitext(filename)[1].lower() in MESH_EXTENSIONS:
                assets.add(norm_path(os.path.abspath(os.path.join(current_root, filename))))

    return sorted(assets)


def to_relative_asset_path(dataset_root: str, absolute_path: str) -> str:
    try:
        return norm_path(os.path.relpath(absolute_path, dataset_root))
    except ValueError:
        return norm_path(absolute_path)


def reference_suffixes(package_name: str, relative_path: str) -> list[str]:
    relative_path = norm_path(unquote(relative_path)).lstrip("/")
    segments = [segment for segment in relative_path.split("/") if segment]
    refs = []
    if package_name and relative_path:
        refs.append(f"{package_name}/{relative_path}".lower())
    if relative_path:
        refs.append(relative_path.lower())
    for index in range(len(segments)):
        refs.append("/".join(segments[index:]).lower())
    return list(dict.fromkeys(refs))


def common_prefix_count(left: str, right: str) -> int:
    left_segments = [segment for segment in left.lower().split("/") if segment]
    right_segments = [segment for segment in right.lower().split("/") if segment]
    count = 0
    for left_segment, right_segment in zip(left_segments, right_segments):
        if left_segment != right_segment:
            break
        count += 1
    return count


def resolve_package_reference(
    raw_uri: str,
    source_path: str,
    dataset_root: str,
    assets: list[str],
) -> str:
    without_scheme = raw_uri[len("package://") :]
    package_name, _, relative_path = without_scheme.partition("/")
    refs = reference_suffixes(package_name, relative_path)
    if not refs:
        return raw_uri

    matches: list[tuple[int, int, str]] = []
    source_rel = to_relative_asset_path(dataset_root, source_path)
    for asset_path in assets:
        asset_rel = to_relative_asset_path(dataset_root, asset_path)
        asset_rel_lower = asset_rel.lower()
        for ref in refs:
            if asset_rel_lower == ref or asset_rel_lower.endswith(f"/{ref}"):
                matches.append((ref.count("/") + 1, common_prefix_count(asset_rel, source_rel), asset_path))
                break

    if not matches:
        return raw_uri

    matches.sort(key=lambda row: (row[0], row[1], -len(row[2])), reverse=True)
    best_score = matches[0][:2]
    best_paths = [path for ref_score, prefix_score, path in matches if (ref_score, prefix_score) == best_score]
    unique_paths = sorted(set(best_paths))
    return unique_paths[0] if len(unique_paths) == 1 else matches[0][2]


def resolve_mesh_reference(raw_uri: str, source_path: str, dataset_root: str, assets: list[str]) -> str:
    raw_uri = raw_uri.strip()
    if raw_uri.startswith("package://"):
        return resolve_package_reference(raw_uri, source_path, dataset_root, assets)
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", raw_uri):
        return raw_uri
    if os.path.isabs(raw_uri):
        return norm_path(raw_uri)

    source_relative = norm_path(os.path.abspath(os.path.join(os.path.dirname(source_path), raw_uri)))
    if os.path.exists(source_relative):
        return source_relative
    return raw_uri


def rewrite_mesh_paths(text: str, source_path: str, dataset_root: str, assets: list[str]) -> str:
    pattern = re.compile(r"(<mesh\b[^>]*\bfilename\s*=\s*)([\"'])(.*?)(\2)", re.IGNORECASE)

    def replace(match: re.Match[str]) -> str:
        resolved = resolve_mesh_reference(match.group(3), source_path, dataset_root, assets)
        return f"{match.group(1)}{match.group(2)}{resolved}{match.group(2)}"

    return pattern.sub(replace, text)


def ensure_compiler(text: str, *, include_visuals: bool) -> str:
    discardvisual = "false" if include_visuals else "true"

    def rewrite_compiler(match: re.Match[str]) -> str:
        tag = match.group(0)
        for name, value in (("discardvisual", discardvisual), ("fusestatic", "false")):
            attr_pattern = re.compile(rf"\b{name}\s*=\s*([\"']).*?\1", re.IGNORECASE)
            if attr_pattern.search(tag):
                tag = attr_pattern.sub(f'{name}="{value}"', tag)
            else:
                tag = tag[:-1] + f' {name}="{value}">'
        return tag

    if re.search(r"<compiler\b", text, re.IGNORECASE):
        return re.sub(r"<compiler\b[^>]*>", rewrite_compiler, text, count=1, flags=re.IGNORECASE)

    if re.search(r"<mujoco\b", text, re.IGNORECASE):
        compiler = f'<compiler discardvisual="{discardvisual}" fusestatic="false"/>'
        return re.sub(r"(<mujoco\b[^>]*>)", rf"\1\n{compiler}", text, count=1, flags=re.IGNORECASE)

    block = f'<mujoco><compiler discardvisual="{discardvisual}" fusestatic="false"/></mujoco>'
    return re.sub(r"(<robot\b[^>]*>)", rf"\1\n{block}", text, count=1, flags=re.IGNORECASE)


def to_list(value: Any) -> list[Any]:
    return value.tolist() if hasattr(value, "tolist") else list(value)


def object_name(model: mujoco.MjModel, obj_type: mujoco.mjtObj, index: int) -> str | None:
    return mujoco.mj_id2name(model, obj_type, index)


def body_records(model: mujoco.MjModel) -> list[dict[str, Any]]:
    records = []
    for body_id in range(model.nbody):
        parent_id = int(model.body_parentid[body_id])
        records.append(
            {
                "id": body_id,
                "name": object_name(model, mujoco.mjtObj.mjOBJ_BODY, body_id),
                "parentId": parent_id,
                "parentName": object_name(model, mujoco.mjtObj.mjOBJ_BODY, parent_id),
                "pos": to_list(model.body_pos[body_id]),
                "quatWxyz": to_list(model.body_quat[body_id]),
            }
        )
    return records


def joint_records(model: mujoco.MjModel) -> list[dict[str, Any]]:
    records = []
    for joint_id in range(model.njnt):
        body_id = int(model.jnt_bodyid[joint_id])
        joint_type = int(model.jnt_type[joint_id])
        records.append(
            {
                "id": joint_id,
                "name": object_name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id),
                "type": JOINT_TYPE_NAMES.get(joint_type, f"unknown:{joint_type}"),
                "bodyId": body_id,
                "bodyName": object_name(model, mujoco.mjtObj.mjOBJ_BODY, body_id),
                "pos": to_list(model.jnt_pos[joint_id]),
                "axis": to_list(model.jnt_axis[joint_id]),
                "range": to_list(model.jnt_range[joint_id]),
                "limited": bool(model.jnt_limited[joint_id]),
            }
        )
    return records


def geom_dimensions(model: mujoco.MjModel, geom_id: int) -> list[float]:
    geom_type = int(model.geom_type[geom_id])
    size = to_list(model.geom_size[geom_id])
    if geom_type == int(mujoco.mjtGeom.mjGEOM_BOX):
        return [float(size[0] * 2), float(size[1] * 2), float(size[2] * 2)]
    if geom_type == int(mujoco.mjtGeom.mjGEOM_CYLINDER):
        return [float(size[0]), float(size[1] * 2), 0.0]
    if geom_type == int(mujoco.mjtGeom.mjGEOM_CAPSULE):
        return [float(size[0]), float(size[1] * 2), 0.0]
    if geom_type == int(mujoco.mjtGeom.mjGEOM_SPHERE):
        return [float(size[0]), 0.0, 0.0]
    if geom_type == int(mujoco.mjtGeom.mjGEOM_MESH):
        mesh_id = int(model.geom_dataid[geom_id])
        if 0 <= mesh_id < model.nmesh:
            return [float(value) for value in model.mesh_scale[mesh_id]]
        return [1.0, 1.0, 1.0]
    return [float(size[0]), float(size[1]), float(size[2])]


def geom_records(model: mujoco.MjModel) -> list[dict[str, Any]]:
    records = []
    for geom_id in range(model.ngeom):
        body_id = int(model.geom_bodyid[geom_id])
        geom_type = int(model.geom_type[geom_id])
        contype = int(model.geom_contype[geom_id])
        conaffinity = int(model.geom_conaffinity[geom_id])
        mesh_id = int(model.geom_dataid[geom_id])
        records.append(
            {
                "id": geom_id,
                "name": object_name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id),
                "bodyId": body_id,
                "bodyName": object_name(model, mujoco.mjtObj.mjOBJ_BODY, body_id),
                "type": GEOM_TYPE_NAMES.get(geom_type, f"unknown:{geom_type}"),
                "section": "visual" if contype == 0 and conaffinity == 0 else "collision",
                "pos": to_list(model.geom_pos[geom_id]),
                "quatWxyz": to_list(model.geom_quat[geom_id]),
                "size": to_list(model.geom_size[geom_id]),
                "dimensions": geom_dimensions(model, geom_id),
                "contype": contype,
                "conaffinity": conaffinity,
                "group": int(model.geom_group[geom_id]),
                "meshId": mesh_id if mesh_id >= 0 else None,
                "meshName": object_name(model, mujoco.mjtObj.mjOBJ_MESH, mesh_id)
                if mesh_id >= 0
                else None,
                "meshPos": to_list(model.mesh_pos[mesh_id]) if mesh_id >= 0 else None,
                "meshQuatWxyz": to_list(model.mesh_quat[mesh_id]) if mesh_id >= 0 else None,
            }
        )
    return records


def compile_urdf(text: str, *, include_visuals: bool) -> dict[str, Any]:
    mode = "visual" if include_visuals else "collision"
    try:
        model = mujoco.MjModel.from_xml_string(ensure_compiler(text, include_visuals=include_visuals))
        return {
            "ok": True,
            "mode": mode,
            "error": None,
            "counts": {
                "nbody": int(model.nbody),
                "ngeom": int(model.ngeom),
                "njnt": int(model.njnt),
                "nmesh": int(model.nmesh),
                "nq": int(model.nq),
                "nv": int(model.nv),
                "nu": int(model.nu),
            },
            "bodies": body_records(model),
            "joints": joint_records(model),
            "geoms": geom_records(model),
        }
    except Exception as exc:  # noqa: BLE001 - this is a truth extractor.
        return {
            "ok": False,
            "mode": mode,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=4),
            "counts": None,
            "bodies": [],
            "joints": [],
            "geoms": [],
        }


def manifest_entries(manifest: dict[str, Any], dataset_root: str) -> list[ManifestEntry]:
    entries = []
    for row in manifest.get("files", []):
        relative_path = norm_path(str(row["relativePath"]))
        source_path = str(row.get("sourcePath") or os.path.join(dataset_root, relative_path))
        if not os.path.isabs(source_path):
            source_path = os.path.join(dataset_root, source_path)
        entries.append(ManifestEntry(relative_path=relative_path, source_path=norm_path(os.path.abspath(source_path))))
    return entries


def main() -> int:
    args = parse_args()
    manifest = read_manifest(args.manifest)
    dataset_root = norm_path(os.path.abspath(manifest["datasetRoot"]))
    assets = discover_assets(dataset_root, manifest)
    results = []

    for entry in manifest_entries(manifest, dataset_root):
        try:
            with open(entry.source_path, "r", encoding="utf-8", errors="replace") as handle:
                source_text = handle.read()
            rewritten_text = rewrite_mesh_paths(source_text, entry.source_path, dataset_root, assets)
            collision = compile_urdf(rewritten_text, include_visuals=False)
            visual = compile_urdf(rewritten_text, include_visuals=True)
            results.append(
                {
                    "relativePath": entry.relative_path,
                    "sourcePath": entry.source_path,
                    "collision": collision,
                    "visual": visual,
                }
            )
        except Exception as exc:  # noqa: BLE001 - keep extracting remaining files.
            results.append(
                {
                    "relativePath": entry.relative_path,
                    "sourcePath": entry.source_path,
                    "collision": {"ok": False, "mode": "collision", "error": str(exc), "bodies": [], "joints": [], "geoms": []},
                    "visual": {"ok": False, "mode": "visual", "error": str(exc), "bodies": [], "joints": [], "geoms": []},
                }
            )

    report = {
        "generatedAt": manifest.get("generatedAt"),
        "mujocoVersion": getattr(mujoco, "__version__", "unknown"),
        "datasetRoot": dataset_root,
        "assetCount": len(assets),
        "results": results,
    }
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
