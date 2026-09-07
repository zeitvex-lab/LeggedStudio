"""Interactive MuJoCo sessions for basic teleoperation and map replay.

The session is intentionally backend-neutral: Web and CLI send a high-level
command or a normalized action vector, and receive a serializable frame. A
future native mjlab viewer can consume the same frame contract without
changing the control API.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import struct
import subprocess
import sys
import time
import uuid
import threading
import base64
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import mujoco
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from adapters.mjlab.mujoco_env import ContractMujocoEnv
from backend.robot_presets import get_robot_preset
from backend.scenario_maps import MAPS
from contracts.scenario_contract import ScenarioContract


router = APIRouter(prefix="/api/simulation", tags=["simulation"])


def _get_robot_definition(robot_id: str) -> dict[str, Any] | None:
    preset = get_robot_preset(robot_id)
    if preset is not None:
        return preset
    packages_root = Path(__file__).resolve().parents[1] / "workspace" / "packages"
    for contract_path in packages_root.glob("*/contract.json"):
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if contract.get("robot_id") == robot_id:
            return {"robot_id": robot_id, "family": contract.get("family", robot_id), "contract": contract, "asset_path": contract.get("urdf", {}).get("path", "")}
    return None


def _scene_geoms(map_id: str) -> list[dict[str, Any]]:
    """Create lightweight MuJoCo collision geometry for the selected map."""
    geoms: list[dict[str, Any]] = [{"name": "map_floor", "size": [10.0, 10.0, 0.03], "pos": [0.0, 0.0, -0.03]}]
    item = MAPS[map_id]
    if map_id == "warehouse":
        for index, (x, y, width, depth) in enumerate(item.get("obstacles", [])):
            geoms.append({"name": f"warehouse_obstacle_{index}", "size": [width / 2, depth / 2, 0.45], "pos": [x, y, 0.45]})
    elif map_id == "rough":
        for index, x in enumerate((1.5, 3.0, 4.5, 6.0)):
            geoms.append({"name": f"rough_bump_{index}", "size": [0.35, 1.5, 0.08 + 0.03 * (index % 2)], "pos": [x, 0.0, 0.08 + 0.03 * (index % 2)]})
    elif map_id == "stairs":
        for index in range(5):
            geoms.append({"name": f"stair_{index}", "size": [0.45, 1.5, 0.08 * (index + 1)], "pos": [1.2 + index * 0.9, 0.0, 0.08 * (index + 1)]})
    return geoms


class SimulationSessionRequest(BaseModel):
    robot_id: str = "unitree_go2"
    contract: dict[str, Any] | None = None
    map_id: str = "flat"
    mode: str = Field(default="basic", pattern="^(basic|navigation)$")
    episode_length_s: float = Field(default=60.0, gt=0.0, le=600.0)
    seed: int = 0
    scenario: dict[str, Any] | None = None


class SimulationStepRequest(BaseModel):
    command: dict[str, float] = Field(default_factory=lambda: {"vx": 0.0, "vy": 0.0, "wz": 0.0})
    action: list[float] | None = None


@dataclass
class SimulationSession:
    session_id: str
    robot_id: str
    map_id: str
    mode: str
    env: ContractMujocoEnv
    step_index: int = 0
    last_frame: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def reset(self) -> dict[str, Any]:
        self.env.reset()
        self.step_index = 0
        self.last_frame = self._frame(np.zeros(self.env.action_dim, dtype=np.float32), 0.0, False, {})
        return self.last_frame

    def command_to_action(self, command: dict[str, float]) -> np.ndarray:
        """Map a high-level velocity command to a stable normalized test gait."""
        vx = float(np.clip(command.get("vx", 0.0), -1.0, 1.0))
        vy = float(np.clip(command.get("vy", 0.0), -1.0, 1.0))
        wz = float(np.clip(command.get("wz", 0.0), -1.0, 1.0))
        action = np.zeros(self.env.action_dim, dtype=np.float32)
        phase = self.step_index * 0.25
        joint_order = list(self.env.contract.action.joint_order)
        for index, joint_name in enumerate(joint_order):
            name = joint_name.lower()
            leg = index // 4 if len(joint_order) >= 16 else index // 3
            offset = 0.0 if leg % 2 == 0 else math.pi
            if "wheel" in name:
                action[index] = np.clip(0.55 * vx + 0.15 * vy + 0.1 * wz, -1.0, 1.0)
            elif name.endswith("hip_joint"):
                action[index] = np.clip(0.08 * vy + 0.06 * wz, -1.0, 1.0)
            elif name.endswith("thigh_joint"):
                action[index] = np.clip(0.20 * vx * math.sin(phase + offset), -1.0, 1.0)
            else:
                action[index] = np.clip(-0.25 * abs(vx) * max(0.0, math.sin(phase + offset)), -1.0, 1.0)
        return action

    def step(self, request: SimulationStepRequest) -> dict[str, Any]:
        self.env.set_commands(request.command)
        action = np.asarray(request.action, dtype=np.float32) if request.action is not None else self.command_to_action(request.command)
        if action.size != self.env.action_dim:
            raise ValueError(f"action dimension must be {self.env.action_dim}")
        _, reward, done, info = self.env.step(action.reshape(1, -1))
        self.step_index += 1
        self.last_frame = self._frame(action, float(reward[0]), bool(done[0]), info)
        return self.last_frame

    def _frame(self, action: np.ndarray, reward: float, done: bool, info: dict[str, Any]) -> dict[str, Any]:
        position = info.get("base_position", np.zeros((1, 3), dtype=np.float32))
        velocity = info.get("base_velocity", np.zeros(1, dtype=np.float32))
        return {
            "session_id": self.session_id,
            "robot_id": self.robot_id,
            "map_id": self.map_id,
            "mode": self.mode,
            "step": self.step_index,
            "position": np.asarray(position[0]).tolist() if np.asarray(position).ndim > 1 else np.asarray(position).tolist(),
            "velocity_x": float(np.asarray(velocity).reshape(-1)[0]),
            "reward": reward,
            "done": done,
            "action": action.tolist(),
            "timestamp": time.time(),
            "time": float(self.step_index * self.env.contract.control.decimation / self.env.contract.control.physics_hz),
            "command": self.env.commands[0].tolist(),
            "observation": self.env._observations()[0].tolist(),
            "reward_components": {key: float(np.asarray(value).reshape(-1)[0]) for key, value in info.get("reward_components", {}).items()},
            "contacts": int(getattr(self.env.data[0], "ncon", 0)),
            "joint_positions": np.asarray(info.get("joint_positions", []))[0].tolist() if np.asarray(info.get("joint_positions", [])).ndim > 1 else [],
            "joint_velocities": np.asarray(info.get("joint_velocities", []))[0].tolist() if np.asarray(info.get("joint_velocities", [])).ndim > 1 else [],
            "base_quaternion": np.asarray(info.get("base_quaternion", []))[0].tolist() if np.asarray(info.get("base_quaternion", [])).ndim > 1 else [],
            "control": np.asarray(info.get("control", []))[0].tolist() if np.asarray(info.get("control", [])).ndim > 1 else [],
        }

    def render(self, width: int = 960, height: int = 640) -> str:
        """Render the current MuJoCo state for the Web Play-style viewport."""
        render_width = min(width, int(getattr(self.env.model.vis.global_, "offwidth", width)))
        render_height = min(height, int(getattr(self.env.model.vis.global_, "offheight", height)))
        renderer = mujoco.Renderer(self.env.model, height=max(120, render_height), width=max(160, render_width))
        renderer.update_scene(self.env.data[0], camera=-1)
        pixels = renderer.render()
        renderer.close()
        from PIL import Image
        stream = io.BytesIO()
        Image.fromarray(np.asarray(pixels, dtype=np.uint8)).save(stream, format="PNG")
        return base64.b64encode(stream.getvalue()).decode("ascii")


sessions: dict[str, SimulationSession] = {}
sessions_lock = threading.Lock()
SESSION_TTL_SECONDS = 30 * 60
# Go2's bundled path already streams a 7.8 MB OBJ to the same browser runtime,
# so individual meshes up to ~12 MB compile fine. The limit only guards against
# pathological single files; meshes above it fall back to primitive proxies.
BROWSER_MESH_LIMIT_BYTES = 12 * 1024 * 1024
BROWSER_MESH_SUFFIXES = {".obj", ".stl", ".dae", ".ply", ".msh"}
BROWSER_INITIAL_KEYFRAME = "__browser_init__"
GO2_BROWSER_SCENES = (
    "flat.xml",
    "stairs.xml",
    "cross_stairs.xml",
    "high_platforms.xml",
    "cross_slope.xml",
    "race_track.xml",
)
GO2_TERRAIN_ROOT = Path(__file__).resolve().parents[1] / "web" / "sim2sim" / "assets" / "go2"


def _cleanup_sessions() -> None:
    now = time.time()
    with sessions_lock:
        expired = [key for key, value in sessions.items() if now - value.created_at > SESSION_TTL_SECONDS]
        for key in expired:
            session = sessions.pop(key)
            session.env.close()


@router.get("/maps")
async def list_maps() -> dict[str, Any]:
    return {"maps": list(MAPS.values()), "count": len(MAPS)}


def _browser_package(robot_id: str) -> tuple[Path, dict[str, Any]]:
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


def _browser_package_root(robot_id: str) -> Path:
    return _browser_package(robot_id)[0]


def _browser_asset_bytes(root: Path) -> int:
    assets = root / "model" / "assets"
    return sum(item.stat().st_size for item in assets.rglob("*") if item.is_file()) if assets.exists() else 0


def _read_simulation_config(root: Path) -> dict[str, Any]:
    path = root / "simulation" / "config.json"
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _acceptance_report_path(root: Path, policy_rel_path: str) -> Path:
    """验收指标约定：<onnx 文件名去扩展名>.acceptance.json，与策略同目录。"""
    policy_file = Path(policy_rel_path.replace("\\", "/")).name
    return root / "simulation" / "policies" / f"{Path(policy_file).stem}.acceptance.json"


def _load_acceptance_report(root: Path, policy_rel_path: str) -> dict[str, Any] | None:
    path = _acceptance_report_path(root, policy_rel_path)
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return report if isinstance(report, dict) and report.get("modes") else None


def _acceptance_health_check(root: Path, policy_rel_path: str) -> dict[str, Any] | None:
    """把验收报告折算成一条策略健康检查（mjlab evaluate 三件套的产物）。"""
    report = _load_acceptance_report(root, policy_rel_path)
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


@router.post("/policies/acceptance")
async def run_policy_acceptance(payload: dict[str, Any]) -> dict[str, Any]:
    """对机器人包内已导出的 ONNX 策略跑验收评估（定种子固定指令滚出）。

    在隔离的 mjlab 适配器 venv 里执行 policy_acceptance.py（依赖 mujoco+onnxruntime），
    指标写入策略同目录的 <stem>.acceptance.json，随 browser-config 下发为健康检查。
    """
    robot_id = str(payload.get("robot_id") or "")
    policy_id = str(payload.get("policy_id") or "")
    if not robot_id or not policy_id:
        raise HTTPException(status_code=400, detail="robot_id 与 policy_id 必填")
    root, _preset = _browser_package(robot_id)
    sim_cfg = _read_simulation_config(root)
    policies = sim_cfg.get("policies") if isinstance(sim_cfg.get("policies"), list) else []
    policy = next((p for p in policies if isinstance(p, dict) and p.get("id") == policy_id), None)
    if not policy:
        raise HTTPException(status_code=404, detail=f"包内不存在策略: {policy_id}")
    policy_rel = str(policy["path"]).replace("\\", "/")
    policy_path = root / policy_rel
    if not policy_path.exists():
        raise HTTPException(status_code=404, detail=f"策略文件缺失: {policy_rel}")
    output = _acceptance_report_path(root, policy_rel)

    script = Path(__file__).resolve().parents[1] / "adapters" / "mjlab" / "policy_acceptance.py"
    venv_dir = Path(__file__).resolve().parents[1] / "adapters" / "mjlab" / ".venv"
    venv_python = venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    python_exe = str(venv_python) if venv_python.exists() else sys.executable
    command = [python_exe, str(script), "--package", str(root), "--policy", str(policy_path), "--output", str(output)]
    try:
        completed = await asyncio.wait_for(
            asyncio.to_thread(
                subprocess.run, command, capture_output=True, text=True, timeout=900, cwd=str(script.parent.parent)
            ),
            timeout=920,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="验收评估超时（>920s）")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()[-6:]
        raise HTTPException(status_code=500, detail="验收评估失败: " + " | ".join(detail))
    report = _load_acceptance_report(root, policy_rel)
    if not report:
        raise HTTPException(status_code=500, detail="验收评估未产出指标文件")
    return report


def _browser_asset_files(root: Path) -> tuple[list[str], list[str], int]:
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


def _initial_key_qpos(document: ET.Element, preset: dict[str, Any], simulation_config: dict[str, Any]) -> list[float]:
    contract = preset.get("contract") or {}
    order = list(contract.get("action", {}).get("joint_order") or contract.get("joints", {}).get("actuated_joints") or [])
    pose = list(contract.get("joints", {}).get("default_pose") or [])
    # default_pose 可能按模型树序（joints.actuated_joints）而非 action.joint_order 给出：
    # action 块若带显式 default_pose（action.default_pose + default_pose_order="sdk"），优先用它配 zip。
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


def _mesh_aabb(path: Path) -> tuple[list[float], list[float]] | None:
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


def _proxy_geom(geom: ET.Element, body_name: str, mesh_path: Path | None = None) -> None:
    """Replace one unavailable mesh geom with a fitting primitive.

    The proxy must sit where the real mesh sits: imported MJCFs reference the
    mesh at its file coordinates (geom pos stays 0 and MuJoCo applies the
    centring offset itself), so the box is placed at the mesh bounding-box
    centre with the matching half extents instead of a hardcoded guess.
    """
    geom.attrib.pop("mesh", None)
    name = body_name.lower()
    if "base" in name or "trunk" in name:
        geom.set("type", "box")
    elif "wheel" in name:
        geom.set("type", "cylinder")
    else:
        geom.set("type", "capsule")
    aabb = _mesh_aabb(mesh_path) if mesh_path is not None else None
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


def _browser_model_xml(root: Path, model_path: Path, preset: dict[str, Any]) -> str:
    """Return a browser-safe model while retaining every mesh below the size limit.

    The source package stays untouched. Visual mesh geoms are replaced before
    transfer only when their individual file reaches the transfer limit.
    """
    source = model_path.read_text(encoding="utf-8-sig")
    document = ET.fromstring(source)
    _configure_browser_actuators(document, preset)
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
                    _proxy_geom(geom, body.get("name") or "", mesh_path)

    simulation_config = _read_simulation_config(root)
    configured_keyframe = str(simulation_config.get("initial_keyframe") or "").strip()
    configured_key = next((key for key in document.findall(".//key") if key.get("name") == configured_keyframe), None)
    if not configured_keyframe or configured_key is None:
        qpos = _initial_key_qpos(document, preset, simulation_config)
        if qpos:
            keyframe = document.find("keyframe")
            if keyframe is None:
                keyframe = ET.SubElement(document, "keyframe")
            for existing in list(keyframe.findall(f"key[@name='{BROWSER_INITIAL_KEYFRAME}']")):
                keyframe.remove(existing)
            ET.SubElement(keyframe, "key", {"name": BROWSER_INITIAL_KEYFRAME, "qpos": " ".join(f"{value:.12g}" for value in qpos)})
    return ET.tostring(document, encoding="unicode")


def _configure_browser_actuators(document: ET.Element, preset: dict[str, Any]) -> None:
    """Normalize actuator semantics for the browser runtime.

    Package MJCFs come from different simulators.  The browser controller uses
    the same contracts as the reference projects: Go2 receives external PD
    torque through ``motor`` actuators, while ZEX-W receives position targets
    for its legs and velocity targets for its wheels.  MicroDuck already ships
    the position actuators used by ``microduck-simulator`` and is left intact.
    """
    robot_id = str(preset.get("robot_id") or "").lower().replace("_", "-")
    if robot_id not in {"unitree-go2", "zex-w"}:
        return
    contract = preset.get("contract") or {}
    order = list(
        contract.get("action", {}).get("joint_order")
        or contract.get("joints", {}).get("actuated_joints")
        or []
    )
    if not order:
        return
    actuator = document.find("actuator")
    if actuator is None:
        actuator = ET.SubElement(document, "actuator")
    for child in list(actuator):
        actuator.remove(child)

    if robot_id == "unitree-go2":
        limits = {"hip": 23.7, "thigh": 23.7, "calf": 35.55}
        for joint_name in order:
            group = "calf" if "calf" in str(joint_name).lower() else ("hip" if "hip" in str(joint_name).lower() else "thigh")
            limit = limits[group]
            ET.SubElement(
                actuator,
                "motor",
                {
                    "name": str(joint_name).removesuffix("_joint"),
                    "joint": str(joint_name),
                    "gear": "1",
                    "forcelimited": "true",
                    "forcerange": f"{-limit:g} {limit:g}",
                },
            )
        return

    # ZEX-W's source XML uses general actuators with an embedded PD loop.  The
    # policy, however, emits target positions/velocities and the reference
    # sim2sim rebuilds these as native MuJoCo position/velocity actuators.
    for joint_name in order:
        name = str(joint_name)
        if "wheel" in name.lower():
            ET.SubElement(
                actuator,
                "velocity",
                {
                    "name": name,
                    "joint": name,
                    "kv": "1",
                    "forcelimited": "true",
                    "forcerange": "-17 17",
                },
            )
        else:
            ET.SubElement(
                actuator,
                "position",
                {
                    "name": name,
                    "joint": name,
                    "kp": "50",
                    "kv": "1.5",
                    "forcelimited": "true",
                    "forcerange": "-17 17",
                },
            )


def _go2_browser_scene(scene_name: str) -> str:
    """Build a self-contained primitive terrain scene for the package model."""
    source_path = GO2_TERRAIN_ROOT / scene_name
    document = ET.fromstring(source_path.read_text(encoding="utf-8-sig"))
    for include in document.findall("include"):
        if include.get("file") == "go2.xml":
            include.set("file", "model/robot.xml")
    for texture in document.findall(".//texture[@file]"):
        texture.attrib.pop("file", None)
        texture.set("builtin", "checker")
        texture.set("rgb1", "0.62 0.66 0.70")
        texture.set("rgb2", "0.34 0.38 0.42")
        texture.set("width", "64")
        texture.set("height", "64")
    return ET.tostring(document, encoding="unicode")


@router.get("/browser-config/{robot_id}")
async def browser_simulation_config(robot_id: str) -> dict[str, Any]:
    """Return the browser-native MuJoCo/Three.js package manifest."""
    root, preset = _browser_package(robot_id)
    canonical_robot_id = str(preset.get("robot_id") or robot_id)
    contract = preset.get("contract") or {}
    order = list(contract.get("action", {}).get("joint_order") or contract.get("joints", {}).get("actuated_joints") or [])
    default_pose = list(contract.get("joints", {}).get("default_pose") or [0.0] * len(order))
    # 与 _initial_key_qpos 同规则：joints.default_pose 若标注为模型树序，先重排到 action.joint_order。
    pose_order = str(contract.get("joints", {}).get("default_pose_order") or "").lower()
    if pose_order == "tree" and len(default_pose) == len(contract.get("joints", {}).get("actuated_joints") or []):
        tree_map = dict(zip(contract["joints"]["actuated_joints"], default_pose))
        default_pose = [tree_map.get(name, 0.0) for name in order]
    simulation_config = _read_simulation_config(root)
    policy: dict[str, Any] = {
        "disabled": True,
        "contract": {"obs_dim": 0, "action_dim": len(order), "history_len": 1},
    }
    asset_bytes = _browser_asset_bytes(root)
    browser_assets, omitted_meshes, browser_asset_bytes = _browser_asset_files(root)
    lightweight_preview = bool(omitted_meshes)
    preview_mode = "hybrid_visual_meshes" if lightweight_preview else "visual_meshes"
    if canonical_robot_id == "unitree_go2":
        scenes = list(GO2_BROWSER_SCENES)
        terrain_options = [
            {"id": Path(path).stem, "label": Path(path).stem.replace("_", " ").title(), "path": path}
            for path in scenes
        ]
    else:
        configured_scenes = simulation_config.get("terrains") or simulation_config.get("scenes") or []
        terrain_options = []
        for item in configured_scenes:
            if isinstance(item, str):
                path = item.replace("\\", "/")
                terrain_options.append({"id": Path(path).stem, "label": Path(path).stem.replace("_", " ").title(), "path": path})
            elif isinstance(item, dict) and item.get("path"):
                path = str(item["path"]).replace("\\", "/")
                terrain_options.append({
                    "id": str(item.get("id") or Path(path).stem),
                    "label": str(item.get("label") or item.get("id") or Path(path).stem.replace("_", " ").title()),
                    "path": path,
                })
        if not terrain_options:
            scene_files = sorted((root / "simulation").glob("scene*.xml"))
            terrain_options = [
                {
                    "id": path.stem,
                    "label": "Default scene" if path.name == "scene.xml" else path.stem.removeprefix("scene_").replace("_", " ").title(),
                    "path": "scene.xml" if path.name == "scene.xml" else str(path.relative_to(root)).replace("\\", "/"),
                }
                for path in scene_files
            ]
        if not terrain_options:
            terrain_options = [{"id": "default", "label": "Default scene", "path": "scene.xml"}]
        scenes = [item["path"] for item in terrain_options]
    package = preset.get("robot_package") or {}
    model_info = package.get("model") if isinstance(package.get("model"), dict) else {}
    model_rel = str(model_info.get("path") or "model/robot.xml").replace("\\", "/")
    model_variants = simulation_config.get("model_variants") if isinstance(simulation_config.get("model_variants"), list) else []
    public_models: list[dict[str, Any]] = []
    for item in model_variants:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = str(item["path"]).replace("\\", "/")
        public_models.append({
            "id": str(item.get("id") or Path(path).stem),
            "label": str(item.get("label") or item.get("id") or Path(path).stem),
            "path": path,
            "preview_mode": preview_mode,
        })
    if not public_models:
        public_models = [{
            "id": "default",
            "label": str(model_info.get("label") or Path(model_rel).stem),
            "path": model_rel,
            "preview_mode": preview_mode,
        }]

    # ONNX files are fetched by ONNX Runtime, not copied into MuJoCo's virtual
    # filesystem. Keeping them out of this list makes the robot visible before
    # a potentially large policy download starts.
    files = list(dict.fromkeys([*scenes, model_rel, *(item["path"] for item in public_models)]))
    if canonical_robot_id != "unitree_go2":
        files.extend(
            str(item.relative_to(root)).replace("\\", "/")
            for item in sorted((root / "simulation").glob("*.xml"))
            if item.is_file() and item.name != "scene.xml"
        )
    files.extend(browser_assets)
    package_policies = simulation_config.get("policies") if isinstance(simulation_config.get("policies"), list) else []
    default_policy_contract = simulation_config.get("policy_contract") if isinstance(simulation_config.get("policy_contract"), dict) else {}
    public_policies: list[dict[str, Any]] = []
    for item in package_policies:
        if isinstance(item, dict) and item.get("path"):
            policy_path = str(item["path"]).replace("\\", "/")
            entry_checks: list[dict[str, Any]] = [{"id": "package", "ok": True, "message": "Package policy manifest"}]
            acceptance_check = _acceptance_health_check(root, policy_path)
            if acceptance_check:
                entry_checks.append(acceptance_check)
            public_policies.append({
                "id": str(item.get("id") or Path(policy_path).stem),
                "label": str(item.get("label") or item.get("id") or Path(policy_path).stem),
                "url": f"/api/simulation/browser-package/{canonical_robot_id}/{policy_path}",
                "path": policy_path,
                "obs_dim": int(item.get("obs_dim") or contract.get("observation", {}).get("dimension") or 0),
                "action_dim": int(item.get("action_dim") or len(order)),
                "history_len": int(item.get("history_len") or 1),
                "acceptance": _load_acceptance_report(root, policy_path),
                "contract": {
                    **default_policy_contract,
                    **(item.get("contract") if isinstance(item.get("contract"), dict) else {}),
                    "obs_dim": int(item.get("obs_dim") or contract.get("observation", {}).get("dimension") or 0),
                    "action_dim": int(item.get("action_dim") or len(order)),
                    "history_len": int(item.get("history_len") or 1),
                },
            })
    if package_policies:
        selected_policy = next((item for item in package_policies if isinstance(item, dict) and item.get("path")), None)
        if selected_policy:
            policy_path = str(selected_policy["path"]).replace("\\", "/")
            selected_checks: list[dict[str, Any]] = [{"id": "package", "ok": True, "message": "Package policy manifest"}]
            selected_acceptance = _acceptance_health_check(root, policy_path)
            selected_ok = True
            if selected_acceptance:
                selected_checks.append(selected_acceptance)
                selected_ok = bool(selected_acceptance["ok"])
            policy = {
                "id": str(selected_policy.get("id") or Path(policy_path).stem),
                "disabled": False,
                "onnx_url": f"/api/simulation/browser-package/{canonical_robot_id}/{policy_path}",
                "checkpoint_iteration": selected_policy.get("checkpoint_iteration"),
                "health": {"status": "pass" if selected_ok else "warn", "checks": selected_checks},
                "contract": {
                    **default_policy_contract,
                    **(selected_policy.get("contract") if isinstance(selected_policy.get("contract"), dict) else {}),
                    "obs_dim": int(selected_policy.get("obs_dim") or contract.get("observation", {}).get("dimension") or 0),
                    "action_dim": int(selected_policy.get("action_dim") or len(order)),
                    "history_len": int(selected_policy.get("history_len") or 1),
                    "action_scale": float(contract.get("action", {}).get("action_scale", 0.25)),
                },
            }
    if canonical_robot_id == "unitree_go2":
        go2_policy_url = "/web/sim2sim/models/go2_moe_cts_high_slope_164k.onnx"
        policy = {
            "id": "go2-baseline-164k",
            "disabled": False,
            "onnx_url": go2_policy_url,
            "checkpoint_iteration": 164000,
            "health": {"status": "pass", "checks": [{"id": "bundled", "ok": True, "message": "Bundled Go2 baseline"}]},
            "contract": {
                "obs_dim": 45,
                "action_dim": len(order),
                "history_len": 5,
                "action_scale": float(contract.get("action", {}).get("action_scale", 0.25)),
                "autoplay": False,
                "default_joint_angles": {name: float(value) for name, value in zip(order, default_pose)},
            },
        }
        public_policies = [{
            "id": "go2-baseline-164k",
            "label": "Go2 baseline 164k",
            "url": go2_policy_url,
            "path": "models/go2_moe_cts_high_slope_164k.onnx",
            "obs_dim": 45,
            "action_dim": len(order),
            "history_len": 5,
            "contract": policy["contract"],
        }]
    simulation_control = simulation_config.get("control") if isinstance(simulation_config.get("control"), dict) else {}
    action_scale = float(
        simulation_config.get("action_scale", contract.get("action", {}).get("action_scale", 0.25))
    )
    decimation = int(
        simulation_config.get(
            "decimation",
            simulation_control.get("decimation", contract.get("control", {}).get("decimation", 4)),
        )
    )
    physics_hz = float(
        simulation_config.get(
            "physics_hz",
            simulation_control.get("physics_hz", contract.get("control", {}).get("physics_hz", 1000)),
        )
    )
    action_scale_by_role = simulation_config.get("action_scale_by_role")
    if not isinstance(action_scale_by_role, dict):
        action_scale_by_role = {"leg": action_scale, "wheel": 5.0}
    control_modes = simulation_config.get("control_modes")
    if not isinstance(control_modes, dict):
        control_modes = {"wheel": "velocity"}
    files = list(dict.fromkeys(files))
    # The revision busts the browser HTTP cache for every package file. It must
    # react to any served XML change (scenes included), not just the manifest.
    revision_sources = [root / "robot_package.json", root / "model" / "robot.xml"]
    revision_sources.extend(sorted((root / "simulation").glob("*.xml")))
    revision_ts = max((p.stat().st_mtime_ns for p in revision_sources if p.is_file()), default=0)
    return {
        "run_id": None,
        "robot": {
            "name": preset.get("family", robot_id),
            "joint_order": order,
            "default_joint_angles": {name: float(value) for name, value in zip(order, default_pose)},
            "control": {
                "action_scale": action_scale,
                "decimation": max(1, decimation),
                "sim_dt": 1.0 / max(1.0, physics_hz),
                "actuator_interface": str(simulation_config.get("actuator_interface") or "").lower(),
                "base_height_target": simulation_config.get("initial_base_height"),
                "initial_keyframe": str(simulation_config.get("initial_keyframe") or BROWSER_INITIAL_KEYFRAME),
                "stiffness": simulation_config.get("stiffness") or {"hip": 50.0, "thigh": 50.0, "calf": 50.0, "joint": 50.0},
                "damping": simulation_config.get("damping") or {"hip": 1.5, "thigh": 1.5, "calf": 1.5, "wheel": 1.0, "joint": 1.5},
                "torque_limits": simulation_config.get("torque_limits"),
                "action_scale_by_role": action_scale_by_role,
                "action_scale_by_joint": simulation_config.get("action_scale_by_joint") or {},
                "velocity_scale": float(simulation_config.get("velocity_scale", 5.0)),
                "control_modes": control_modes,
                # Deployment sim2sim extras: per-role action low-pass cutoffs
                # (Hz) and the PD settle hold (physics steps) applied on reset.
                "action_filter_cutoffs": (
                    simulation_config.get("action_filter_cutoffs")
                    if isinstance(simulation_config.get("action_filter_cutoffs"), dict)
                    else simulation_control.get("action_filter_cutoffs")
                ),
                "settle_steps": simulation_config.get("settle_steps", simulation_control.get("settle_steps", 0)),
            },
        },
        "policy": policy,
        "sim": {
            "robot": canonical_robot_id,
            "custom_robot_mjcf_supported": True,
            "asset_package": {
                "base_url": f"/api/simulation/browser-package/{canonical_robot_id}/",
                "files": files,
                "scenes": scenes,
                "models": public_models,
                "policies": public_policies,
                "terrains": terrain_options,
                "revision": str(revision_ts),
                # Only individual mesh files at or above the browser limit are
                # represented by generated primitive proxies.
                "lightweight_preview": lightweight_preview,
                "preview_mode": preview_mode,
                "asset_bytes": asset_bytes,
                "browser_asset_bytes": browser_asset_bytes,
                "mesh_limit_bytes": BROWSER_MESH_LIMIT_BYTES,
                "omitted_meshes": omitted_meshes,
            },
        },
    }


@router.get("/browser-package/{robot_id}/{asset_path:path}")
async def browser_simulation_asset(robot_id: str, asset_path: str):
    """Serve allowlisted package files to the browser MuJoCo virtual FS."""
    root, preset = _browser_package(robot_id)
    canonical_robot_id = str(preset.get("robot_id") or robot_id)
    normalized = asset_path.replace("\\", "/").lstrip("/")
    if canonical_robot_id == "unitree_go2" and normalized in GO2_BROWSER_SCENES:
        return PlainTextResponse(_go2_browser_scene(normalized), media_type="application/xml")
    if normalized == "scene.xml":
        scene = root / "simulation" / "scene.xml"
        if not scene.exists():
            scene_text = '<mujoco model="legged-studio-scene"><include file="model/robot.xml"/><worldbody><geom name="floor" type="plane" size="0 0 0.05"/></worldbody></mujoco>'
        else:
            source = scene.read_text(encoding="utf-8-sig")
            source = source.replace('file="../model/robot.xml"', 'file="model/robot.xml"')
            scene_text = source
        return PlainTextResponse(scene_text, media_type="application/xml")
    if normalized.startswith("model/") and normalized.lower().endswith((".xml", ".mjcf")):
        candidate = (root / normalized).resolve()
        model_root = (root / "model").resolve()
        if not candidate.is_file() or model_root not in candidate.parents:
            raise HTTPException(status_code=404, detail="browser simulation model not found")
        return PlainTextResponse(_browser_model_xml(root, candidate, preset), media_type="application/xml")
    if normalized.startswith("simulation/") and normalized.endswith(".xml"):
        candidate = (root / normalized).resolve()
        simulation_root = (root / "simulation").resolve()
        if not candidate.is_file() or simulation_root not in candidate.parents:
            raise HTTPException(status_code=404, detail="browser simulation scene not found")
        source = candidate.read_text(encoding="utf-8-sig")
        # Package scenes execute from /platform/simulation in the browser FS.
        # Normalize common source-project paths without introducing a
        # robot-specific adapter.
        source = source.replace('file="model/robot.xml"', 'file="../model/robot.xml"')
        source = source.replace("file='model/robot.xml'", "file='../model/robot.xml'")
        source = source.replace('meshdir="assets"', 'meshdir="../model/assets"')
        source = source.replace("meshdir='assets'", "meshdir='../model/assets'")
        return PlainTextResponse(source, media_type="application/xml")
    candidate = (root / normalized).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="invalid package asset path")
    allowed_prefixes = (root / "model", root / "simulation" / "policies", root / "simulation" / "visual")
    if not candidate.is_file() or not any(candidate == prefix or prefix in candidate.parents for prefix in allowed_prefixes):
        raise HTTPException(status_code=404, detail="browser package asset not found")
    # 策略 ONNX（及外部数据文件）会在原地被重写（例如外部数据内联）。
    # 绝不能让浏览器复用 HTTP 缓存里的旧字节，否则 onnxruntime 会按旧引用去
    # 请求不存在的 policy.onnx.data 并报 "Failed to load external data file"。
    if candidate.suffix.lower() in {".onnx", ".data"}:
        return FileResponse(candidate, headers={"Cache-Control": "no-store"})
    return FileResponse(candidate)


@router.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    _cleanup_sessions()
    with sessions_lock:
        items = [{"session_id": item.session_id, "robot_id": item.robot_id, "map_id": item.map_id, "mode": item.mode, "step": item.step_index, "created_at": item.created_at} for item in sessions.values()]
    return {"sessions": items, "count": len(items)}


@router.post("/sessions")
async def create_session(request: SimulationSessionRequest) -> dict[str, Any]:
    if request.map_id not in MAPS:
        raise HTTPException(status_code=404, detail=f"Unknown simulation map: {request.map_id}")
    preset = _get_robot_definition(request.robot_id)
    if request.contract is not None:
        preset = {"robot_id": request.robot_id, "family": request.contract.get("family", request.robot_id), "contract": request.contract, "asset_path": request.contract.get("urdf", {}).get("path", "")}
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot preset: {request.robot_id}")
    mode = request.mode
    if MAPS[request.map_id]["mode"] == "navigation":
        mode = "navigation"
    from contracts.robot_contract_v2 import RobotContractV2

    contract = RobotContractV2(**preset["contract"])
    scenario_payload = request.scenario or {"scenario_id": f"{request.map_id}_session", "map_id": request.map_id, "mode": mode, "seed": request.seed, "episode_length_s": request.episode_length_s}
    try:
        scenario = ScenarioContract(**scenario_payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid scenario: {exc}") from exc
    env = ContractMujocoEnv(contract, num_envs=1, episode_length_s=request.episode_length_s, scene_geoms=_scene_geoms(request.map_id))
    session_id = f"sim_{uuid.uuid4().hex[:12]}"
    session = SimulationSession(session_id, request.robot_id, request.map_id, mode, env)
    with sessions_lock:
        sessions[session_id] = session
    return {"success": True, "session_id": session_id, "scenario": scenario.to_payload(), "map": MAPS[request.map_id], "frame": session.reset()}


def _get_session(session_id: str) -> SimulationSession:
    _cleanup_sessions()
    with sessions_lock:
        session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Simulation session not found: {session_id}")
    return session


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session = _get_session(session_id)
    return {"success": True, "frame": session.last_frame, "map": MAPS[session.map_id]}


@router.get("/sessions/{session_id}/render")
async def render_session(session_id: str, width: int = 960, height: int = 640) -> dict[str, Any]:
    session = _get_session(session_id)
    try:
        image = session.render(width, height)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MuJoCo render failed: {exc}") from exc
    actual_width = max(160, min(width, 1920, int(getattr(session.env.model.vis.global_, "offwidth", width))))
    actual_height = max(120, min(height, 1440, int(getattr(session.env.model.vis.global_, "offheight", height))))
    return {"success": True, "format": "png", "width": actual_width, "height": actual_height, "image_base64": image, "frame": session.last_frame}


@router.post("/sessions/{session_id}/step")
async def step_session(session_id: str, request: SimulationStepRequest) -> dict[str, Any]:
    session = _get_session(session_id)
    try:
        return {"success": True, "frame": session.step(request)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/reset")
async def reset_session(session_id: str) -> dict[str, Any]:
    session = _get_session(session_id)
    return {"success": True, "frame": session.reset()}


@router.delete("/sessions/{session_id}")
async def close_session(session_id: str) -> dict[str, Any]:
    session = _get_session(session_id)
    session.env.close()
    with sessions_lock:
        sessions.pop(session_id, None)
    return {"success": True, "session_id": session_id}
