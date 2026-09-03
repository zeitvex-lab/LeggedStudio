"""Interactive MuJoCo sessions for basic teleoperation and map replay.

The session is intentionally backend-neutral: Web and CLI send a high-level
command or a normalized action vector, and receive a serializable frame. A
future native mjlab viewer can consume the same frame contract without
changing the control API.
"""

from __future__ import annotations

import json
import math
import time
import uuid
import threading
import base64
import io
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

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
    imports_root = Path(__file__).resolve().parents[1] / "workspace" / "imports"
    for contract_path in imports_root.rglob("contract.json"):
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


def _browser_package_root(robot_id: str) -> Path:
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
    if not (root / "model" / "robot.xml").exists():
        raise HTTPException(status_code=404, detail=f"Robot package has no browser MJCF model: {robot_id}")
    return root


@router.get("/browser-config/{robot_id}")
async def browser_simulation_config(robot_id: str) -> dict[str, Any]:
    """Return the browser-native MuJoCo/Three.js package manifest."""
    root = _browser_package_root(robot_id)
    preset = get_robot_preset(robot_id) or {}
    contract = preset.get("contract") or {}
    order = list(contract.get("action", {}).get("joint_order") or contract.get("joints", {}).get("actuated_joints") or [])
    default_pose = list(contract.get("joints", {}).get("default_pose") or [0.0] * len(order))
    files = ["scene.xml", "model/robot.xml"]
    files.extend(str(item.relative_to(root)).replace("\\", "/") for item in sorted((root / "model" / "assets").rglob("*")) if item.is_file())
    asset_bytes = sum(item.stat().st_size for item in (root / "model" / "assets").rglob("*") if item.is_file())
    return {
        "run_id": None,
        "robot": {
            "name": preset.get("family", robot_id),
            "joint_order": order,
            "default_joint_angles": {name: float(value) for name, value in zip(order, default_pose)},
            "control": {
                "action_scale": float(contract.get("action", {}).get("action_scale", 0.25)),
                "decimation": int(contract.get("control", {}).get("decimation", 4)),
                "sim_dt": 1.0 / float(contract.get("control", {}).get("physics_hz", 1000)),
                "stiffness": {"hip": 50.0, "thigh": 50.0, "calf": 50.0, "joint": 50.0},
                "damping": {"hip": 1.5, "thigh": 1.5, "calf": 1.5, "wheel": 1.0, "joint": 1.5},
                "action_scale_by_role": {"leg": 0.25, "wheel": 5.0},
                "velocity_scale": 5.0,
                "control_modes": {"wheel": "velocity"},
            },
        },
        "policy": {"disabled": True, "contract": {"obs_dim": 0, "action_dim": len(order), "history_len": 1}},
        "sim": {
            "robot": robot_id,
            "asset_package": {
                "base_url": f"/api/simulation/browser-package/{robot_id}/",
                "files": files,
                "scenes": ["scene.xml"],
                "revision": str((root / "robot_package.json").stat().st_mtime_ns),
                # Large mesh packages are previewed with collision geometry in
                # the browser to keep synchronous WASM compilation responsive.
                "lightweight_preview": asset_bytes >= 20 * 1024 * 1024,
                "asset_bytes": asset_bytes,
            },
        },
    }


@router.get("/browser-package/{robot_id}/{asset_path:path}")
async def browser_simulation_asset(robot_id: str, asset_path: str):
    """Serve allowlisted package files to the browser MuJoCo virtual FS."""
    root = _browser_package_root(robot_id)
    normalized = asset_path.replace("\\", "/").lstrip("/")
    if normalized == "scene.xml":
        scene = root / "simulation" / "scene.xml"
        if not scene.exists():
            scene_text = '<mujoco model="legged-studio-scene"><include file="model/robot.xml"/><worldbody><geom name="floor" type="plane" size="0 0 0.05"/></worldbody></mujoco>'
        else:
            source = scene.read_text(encoding="utf-8-sig")
            source = source.replace('file="../model/robot.xml"', 'file="model/robot.xml"')
            scene_text = source
        return PlainTextResponse(scene_text, media_type="application/xml")
    candidate = (root / normalized).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="invalid package asset path")
    if not candidate.is_file() or (candidate != root / "model" / "robot.xml" and root / "model" not in candidate.parents):
        raise HTTPException(status_code=404, detail="browser package asset not found")
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
