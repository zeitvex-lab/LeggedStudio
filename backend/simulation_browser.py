"""Browser simulation configuration helpers.

Pure helper functions for building browser-safe simulation configs from robot
package assets. No router/session state -- only data transformation and asset
inspection. Extracted from the legacy god file ``simulation_api.py`` to reduce
its size and enable independent testing.
"""

from __future__ import annotations

import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Sequence

from fastapi import HTTPException

from backend.robot_presets import get_robot_preset
from contracts.role_resolver import RoleResolver

# Browser transfer limits and consts (moved from simulation_api.py)
BROWSER_MESH_LIMIT_BYTES = 40 * 1024 * 1024
BROWSER_MESH_SUFFIXES = {".obj", ".stl", ".dae", ".ply", ".msh"}
#: 会被 MuJoCo 引用、需要下发给浏览器的地图资产后缀（贴图 + 网格）。
#: 刻意用**白名单**而不是"排除 .xml"：后者会把 README.md / _index.json 也带下去。
BROWSER_MAP_ASSET_SUFFIXES = BROWSER_MESH_SUFFIXES | {".png", ".jpg", ".jpeg", ".bmp", ".tga"}
BROWSER_INITIAL_KEYFRAME = "__browser_init__"
REPO_ROOT = Path(__file__).resolve().parents[1]
# 公共地图库（assets/maps/README.md）：环境专用 XML，不含机器人 include。
MAPS_ROOT = REPO_ROOT / "assets" / "maps"
MAP_INDEX = MAPS_ROOT / "_index.json"


def browser_package(robot_id: str) -> tuple[Path, dict[str, Any]]:
    """Resolve a robot package root and its preset entry by robot id."""
    preset = get_robot_preset(robot_id)
    if not preset:
        normalized = robot_id.replace("_", "-").lower()
        from backend.robot_presets import list_robot_presets
        preset = next((item for item in list_robot_presets() if str(item.get("robot_id", "")).lower().replace("_", "-") == normalized), None)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Unknown robot package: {robot_id}")
    package = preset.get("robot_package") or {}
    root = Path(str(package.get("package_root", ""))).resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Robot package files not found: {robot_id}")
    model_info = package.get("model") if isinstance(package.get("model"), dict) else {}
    model_path = root / str(model_info.get("path") or "model/robot.xml")
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Robot package has no browser MJCF model: {robot_id}")
    return root, preset


def browser_package_root(robot_id: str) -> Path:
    """Return the package root for a robot id."""
    return browser_package(robot_id)[0]


def read_simulation_config(root: Path) -> dict[str, Any]:
    """Read ``simulation/config.json`` if present, else ``{}``."""
    path = root / "simulation" / "config.json"
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def browser_asset_bytes(root: Path) -> int:
    """Total bytes of package assets under ``model/assets``."""
    assets = root / "model" / "assets"
    return sum(item.stat().st_size for item in assets.rglob("*") if item.is_file()) if assets.exists() else 0


def acceptance_report_path(root: Path, policy_rel_path: str) -> Path:
    """Acceptance convention: ``<onnx stem>.acceptance.json`` beside the policy.

    Policies normally live in ``simulation/policies/`` (so this is the historical
    location), but deploy-bundle policies live elsewhere (e.g. Wuji's
    ``deploy/<version>/policy.onnx``); resolving relative to the policy keeps
    both layouts working.
    """
    policy = Path(policy_rel_path.replace("\\", "/"))
    return root / policy.with_name(f"{policy.stem}.acceptance.json")


def load_acceptance_report(root: Path, policy_rel_path: str) -> dict[str, Any] | None:
    """Load the acceptance JSON report if valid."""
    path = acceptance_report_path(root, policy_rel_path)
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return report if isinstance(report, dict) and report.get("modes") else None


def acceptance_health_check(root: Path, policy_rel_path: str) -> dict[str, Any] | None:
    """Fold an acceptance report into a single policy health check."""
    report = load_acceptance_report(root, policy_rel_path)
    if not report:
        return None
    passed = int(report.get("passed") or 0)
    total = int(report.get("total") or 0)
    ok = total > 0 and passed == total
    errs = [round(m["vel_track_err"], 2) for m in report.get("modes", []) if isinstance(m.get("vel_track_err"), (int, float))]
    err_hint = f" · 跟踪误差≤{min(errs)}~{max(errs)}" if errs else ""
    return {
        "id": "acceptance",
        "ok": ok,
        "message": f"验收 {passed}/{total} 模式通过{err_hint}（{report.get('seconds_per_mode', '?')}s/模式）",
    }


def browser_asset_files(root: Path) -> tuple[list[str], list[str], int]:
    """Select package assets using the browser's per-mesh transfer limit."""
    assets = root / "model" / "assets"
    included: list[str] = []
    omitted_meshes: list[str] = []
    included_bytes = 0
    if not assets.exists():
        return included, omitted_meshes, included_bytes
    for item in sorted(assets.rglob("*")):
        if not item.is_file():
            continue
        relative = str(item.relative_to(root)).replace("\\", "/")
        if item.suffix.lower() in BROWSER_MESH_SUFFIXES and item.stat().st_size >= BROWSER_MESH_LIMIT_BYTES:
            omitted_meshes.append(relative)
            continue
        included.append(relative)
        included_bytes += item.stat().st_size
    return included, omitted_meshes, included_bytes


def initial_key_qpos(document: ET.Element, preset: dict[str, Any], simulation_config: dict[str, Any]) -> list[float]:
    """Compute the initial keyframe qpos from contract default pose + base height."""
    contract = preset.get("contract") or {}
    order = list(contract.get("action", {}).get("joint_order") or contract.get("joints", {}).get("actuated_joints") or [])
    pose = list(contract.get("joints", {}).get("default_pose") or [])
    pose_order = str(contract.get("joints", {}).get("default_pose_order") or "").lower()
    if pose_order == "tree" and len(pose) == len(contract.get("joints", {}).get("actuated_joints") or []):
        pose = [dict(zip(contract["joints"]["actuated_joints"], pose)).get(name, 0.0) for name in order]
    pose_by_name = {name: float(value) for name, value in zip(order, pose)}
    requested_height = simulation_config.get("initial_base_height")
    values: list[float] = []

    def floats(value: str | None, fallback: list[float]) -> list[float]:
        try:
            parsed = [float(item) for item in (value or "").split()]
        except ValueError:
            parsed = []
        return parsed if len(parsed) == len(fallback) else list(fallback)

    def visit_body(body: ET.Element) -> None:
        for joint in list(body):
            if joint.tag not in {"joint", "freejoint"}:
                continue
            joint_type = "free" if joint.tag == "freejoint" else (joint.get("type") or "hinge").lower()
            if joint_type == "free":
                position = floats(body.get("pos"), [0.0, 0.0, 0.0])
                if requested_height is not None:
                    position[2] = float(requested_height)
                values.extend(position)
                values.extend(floats(body.get("quat"), [1.0, 0.0, 0.0, 0.0]))
            elif joint_type == "ball":
                values.extend([1.0, 0.0, 0.0, 0.0])
            else:
                values.append(pose_by_name.get(joint.get("name") or "", float(joint.get("ref") or 0.0)))
        for child in body.findall("./body"):
            visit_body(child)

    worldbody = document.find("worldbody")
    if worldbody is not None:
        for body in worldbody.findall("./body"):
            visit_body(body)
    return values


def mesh_aabb(path: Path) -> tuple[list[float], list[float]] | None:
    """Return the (min, max) corners of a binary/ASCII STL or OBJ mesh."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3

    def absorb(vertex: Sequence[float]) -> None:
        for axis in range(3):
            lo[axis] = min(lo[axis], vertex[axis])
            hi[axis] = max(hi[axis], vertex[axis])

    if path.suffix.lower() == ".stl" and len(data) >= 84:
        count = int.from_bytes(data[80:84], "little")
        if count > 0 and len(data) >= 84 + count * 50:
            for index in range(count):
                offset = 84 + index * 50 + 12  # skip the normal vector
                for corner in range(3):
                    absorb(struct.unpack_from("<3f", data, offset + corner * 12))
            return lo, hi
    text = data.decode("utf-8", "ignore")
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and (parts[0] == "vertex" or parts[0] == "v"):
            try:
                absorb([float(parts[1]), float(parts[2]), float(parts[3])])
            except ValueError:
                return None
    if lo[0] == float("inf"):
        return None
    return lo, hi


def proxy_geom(geom: ET.Element, body_name: str, mesh_path: Path | None = None) -> None:
    """Replace one unavailable mesh geom with a fitting primitive."""
    geom.attrib.pop("mesh", None)
    name = body_name.lower()
    if "base" in name or "trunk" in name:
        geom.set("type", "box")
    elif "wheel" in name:
        geom.set("type", "cylinder")
    else:
        geom.set("type", "capsule")
    aabb = mesh_aabb(mesh_path) if mesh_path is not None else None
    if aabb is None:
        if "base" in name or "trunk" in name:
            geom.set("size", "0.16 0.10 0.06")
        elif "wheel" in name:
            geom.set("size", "0.06 0.025")
        else:
            geom.set("size", "0.035 0.10")
        return
    lo, hi = aabb
    base_pos = [float(value) for value in (geom.get("pos") or "0 0 0").split()[:3]]
    while len(base_pos) < 3:
        base_pos.append(0.0)
    centre = [(lo[axis] + hi[axis]) / 2 for axis in range(3)]
    half = [max((hi[axis] - lo[axis]) / 2, 0.01) for axis in range(3)]
    geom.set("pos", " ".join(f"{base_pos[axis] + centre[axis]:.4f}" for axis in range(3)))
    if geom.get("type") == "capsule" and half[2] > 0:
        geom.set("size", f"{min(half[0], half[1]):.4f} {max(half[2] - min(half[0], half[1]), 0.01):.4f}")
    else:
        geom.set("size", " ".join(f"{value:.4f}" for value in half))


def browser_model_xml(root: Path, model_path: Path, preset: dict[str, Any]) -> str:
    """Return a browser-safe model while retaining every mesh below the size limit."""
    source = model_path.read_text(encoding="utf-8-sig")
    document = ET.fromstring(source)
    # 执行器不再由运行时重建：包内 MJCF 已用 `tools/bake_mjcf_physics.py` 按契约固化
    # （此前这里是"猴子补丁"——整段删掉 <actuator> 再按契约重建，于是"工作台里看到的
    #  MJCF"与"真正跑的物理"不是同一份）。现在浏览器只加载；契约与 MJCF 是否漂移
    #  交给校验器显式报出，而不是靠改写掩盖。
    compiler = document.find("compiler")
    mesh_dir = (compiler.get("meshdir") if compiler is not None else "") or ""
    oversized_files: dict[str, Path] = {}
    for asset in document.findall(".//asset"):
        for mesh in list(asset.findall("mesh")):
            file_name = mesh.get("file") or ""
            candidate = (model_path.parent / mesh_dir / file_name).resolve()
            if candidate.is_file() and candidate.suffix.lower() in BROWSER_MESH_SUFFIXES and candidate.stat().st_size >= BROWSER_MESH_LIMIT_BYTES:
                oversized_files[mesh.get("name") or Path(file_name).stem] = candidate
                asset.remove(mesh)
    if oversized_files:
        for body in document.findall(".//body"):
            for geom in body.findall("./geom"):
                mesh_path = oversized_files.get(geom.get("mesh") or "")
                if mesh_path is not None:
                    proxy_geom(geom, body.get("name") or "", mesh_path)

    simulation_config = read_simulation_config(root)
    configured_keyframe = str(simulation_config.get("initial_keyframe") or "").strip()
    configured_key = next((key for key in document.findall(".//key") if key.get("name") == configured_keyframe), None)
    if not configured_keyframe or configured_key is None:
        qpos = initial_key_qpos(document, preset, simulation_config)
        if qpos:
            keyframe = document.find("keyframe")
            if keyframe is None:
                keyframe = ET.SubElement(document, "keyframe")
            for existing in list(keyframe.findall(f"key[@name='{BROWSER_INITIAL_KEYFRAME}']")):
                keyframe.remove(existing)
            ET.SubElement(keyframe, "key", {"name": BROWSER_INITIAL_KEYFRAME, "qpos": " ".join(f"{value:.12g}" for value in qpos)})
    return ET.tostring(document, encoding="unicode")


def find_package_root_quiet(preset: dict[str, Any]) -> Path | None:
    """Return package root if present and exists, else None."""
    try:
        root = Path(str((preset.get("robot_package") or {}).get("package_root", ""))).resolve()
        return root if root.exists() else None
    except (TypeError, ValueError, OSError):
        return None


def read_contract_v3(root: Path | None) -> dict[str, Any] | None:
    """Read ``contract_v3.json`` if present, else None."""
    if root is None:
        return None
    path = root / "contract_v3.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def browser_scene_file(root: Path, entry: dict[str, Any]) -> str:
    """Build a self-contained primitive terrain scene from a config-registered entry.

    include 改写必须按**场景在浏览器 FS 里的执行目录**来定，不能一律剥 ``../``：

    * 场景以 ``simulation/`` 前缀下发（wuji_hand 的 ``simulation/scene.xml`` 等，
      terrains 条目的 path 带目录前缀）→ 在 FS 里位于 ``/platform/simulation/`` 下，
      磁盘上的 ``../model/X`` **本来就是对的**（模型在 ``/platform/model/``）——
      剥掉 ``../`` 反而指向不存在的 ``/platform/model``（G1 全机型浏览器实测缺陷 B：
      wuji_hand 两个场景 XML 编译失败、整机起不来）；
    * 场景直接从 FS 根执行（历史 go2 内置布局，path 无目录前缀）→ ``model/...`` 才对，
      沿用旧的剥 ``../`` 改写。
    """
    path = REPO_ROOT / entry["path"] if entry.get("repo_path") else root / entry["path"]
    entry_path = str(entry.get("path") or "").replace("\\", "/").lstrip("/")
    scenes_under_simulation = entry_path.startswith("simulation/")
    document = ET.fromstring(path.read_text(encoding="utf-8-sig"))
    model_include = {str(entry.get("robot_include") or ""), "robot.xml"}
    for include in document.findall("include"):
        include_file = str(include.get("file", "")).replace("\\", "/")
        if scenes_under_simulation:
            # 场景在 /platform/simulation/ 下执行：../model/ 是正确引用，原样保留；
            # 仅当被写成相对 FS 根的 model/X 时才补回 ../（防一种写法漂移）。
            if include_file.startswith("model/"):
                include.set("file", f"../{include_file}")
        elif include_file.startswith("../model/"):
            include.set("file", include_file[len("../") :])
        elif Path(include_file).name in model_include:
            include.set("file", "model/robot.xml")
    for texture in document.findall(".//texture[@file]"):
        texture.attrib.pop("file", None)
        texture.set("builtin", "checker")
        texture.set("rgb1", "0.62 0.66 0.70")
        texture.set("rgb2", "0.34 0.38 0.42")
        texture.set("width", "64")
        texture.set("height", "64")
    return ET.tostring(document, encoding="unicode")


def common_map_asset_files() -> list[str]:
    """公共地图库里的**非 XML 资产**（贴图等），返回相对 ``maps/`` 的路径。

    **为什么必须一并下发**：地图 XML 会引用 ``./imgs/label_*.png``（斜坡编号贴图）。
    若只下发 ``maps/<id>.xml``，浏览器侧编译这些地图就会报
    ``Error opening file 'imgs/label_1.png'`` —— 与后端曾经踩过的坑**一模一样**
    （``assets/maps/imgs/`` 当初没跟着 xml 一起拷过来），只是这次发生在**浏览器的
    虚拟文件系统**里：同样静默、同样难查。

    只挑**资产后缀**（贴图/网格）：``README.md`` / ``_index.json`` 是文档与后端索引，
    不该进下发清单（它们不被 MuJoCo 引用，白占带宽）。
    """
    if not MAPS_ROOT.exists():
        return []
    return sorted(
        str(item.relative_to(MAPS_ROOT)).replace("\\", "/")
        for item in MAPS_ROOT.rglob("*")
        if item.is_file() and item.suffix.lower() in BROWSER_MAP_ASSET_SUFFIXES
    )


def read_common_map_asset(asset_rel: str) -> bytes | None:
    """读公共地图库里的静态资产（``asset_rel`` 是 ``maps/`` 之后的部分）。

    返回 ``None`` 表示不存在或**越界** —— 路径穿越防护：解析后必须**落在 MAPS_ROOT 之内**。
    """
    root = MAPS_ROOT.resolve()
    candidate = (root / asset_rel).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate.read_bytes()


def common_map_entries() -> list[dict[str, Any]]:
    """公共地图库清单 → 统一 terrain entry（path 以 ``maps/`` 前缀下发）。"""
    try:
        index = json.loads(MAP_INDEX.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    entries: list[dict[str, Any]] = []
    for item in index.get("maps") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        map_id = str(item["id"])
        entries.append({
            "id": map_id,
            "label": str(item.get("label") or map_id),
            "path": f"maps/{map_id}.xml",
            "browser_scene": True,
            "repo_path": False,
            "source": "common-map-library",
        })
    return entries


def map_scene_xml(map_id: str, robot_include: str = "../model/robot.xml") -> str:
    """公共地图 → 按机型注入机器人 include 的自包含场景 XML。

    地图文件是纯环境（assets/maps/README.md）；机器人由服务端按当前机型注入，
    include 路径相对浏览器 FS 中地图所在目录（``maps/``）——平台布局为
    ``/platform/maps`` 机器人位于 ``/platform/model``，go2 内置布局由前端在
    ``/working/model/robot.xml`` 落一份副本保证同一 include 也能解析。
    """
    path = MAPS_ROOT / f"{map_id}.xml"
    if not path.is_file() or MAPS_ROOT.resolve() not in path.resolve().parents:
        raise HTTPException(status_code=404, detail=f"common map not found: {map_id}")
    document = ET.fromstring(path.read_text(encoding="utf-8-sig"))
    if document.find("include") is None:
        include = ET.Element("include", {"file": robot_include})
        document.insert(0, include)
    # meshdir 相对主文件（地图）所在目录解析；主文件不带 compiler 时，被包含
    # robot.xml 的 meshdir 无法把 mesh 指回 model/assets（实测 stairs 场景
    # 报 model/base_link.STL 缺失）。与包内可用场景（simulation/*.xml 均带
    # compiler meshdir="../model/assets"）保持同一模式：缺就补。
    if document.find("compiler") is None or not document.find("compiler").get("meshdir"):
        compiler = document.find("compiler")
        if compiler is None:
            compiler = ET.Element("compiler")
            document.insert(1, compiler)
        compiler.set("meshdir", "../model/assets")
    return ET.tostring(document, encoding="unicode")


def terrain_entries(simulation_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Package config terrains/scenes → unified entry list."""
    configured = simulation_config.get("terrains") or simulation_config.get("scenes") or []
    entries: list[dict[str, Any]] = []
    for item in configured:
        if isinstance(item, str):
            path = item.replace("\\", "/")
            entries.append({"id": Path(path).stem, "path": path})
        elif isinstance(item, dict) and item.get("path"):
            path = str(item["path"]).replace("\\", "/")
            entries.append({
                "id": str(item.get("id") or Path(path).stem),
                "label": item.get("label"),
                "path": path,
                "browser_scene": bool(item.get("browser_scene")),
                "repo_path": bool(item.get("repo_path")),
                "robot_include": item.get("robot_include"),
            })
    return entries


# Re-export the private helpers under their historical names for compatibility
# with existing imports in ``simulation_api.py``.
_browser_package = browser_package
_browser_package_root = browser_package_root
_browser_asset_bytes = browser_asset_bytes
_read_simulation_config = read_simulation_config
_acceptance_report_path = acceptance_report_path
_load_acceptance_report = load_acceptance_report
_acceptance_health_check = acceptance_health_check
_browser_asset_files = browser_asset_files
_initial_key_qpos = initial_key_qpos
_mesh_aabb = mesh_aabb
_proxy_geom = proxy_geom
_browser_model_xml = browser_model_xml
_find_package_root_quiet = find_package_root_quiet
_read_contract_v3 = read_contract_v3
_browser_scene_file = browser_scene_file
_terrain_entries = terrain_entries
