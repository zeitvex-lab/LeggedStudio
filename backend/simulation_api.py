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
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from adapters.mjlab_new.mujoco_env import ContractMujocoEnv
from backend.robot_presets import get_robot_preset


router = APIRouter(prefix="/api/simulation", tags=["simulation"])


MAPS: dict[str, dict[str, Any]] = {
    "flat": {
        "id": "flat",
        "label": "Flat / 基础遥控",
        "kind": "flat",
        "mode": "basic",
        "description": "平面环境，用于关节和速度指令的快速检查。",
        "bounds": [-5.0, 5.0, -5.0, 5.0],
    },
    "warehouse": {
        "id": "warehouse",
        "label": "Warehouse / 导航",
        "kind": "grid",
        "mode": "navigation",
        "description": "带固定障碍物的二维路线场景，适合 waypoint 任务。",
        "bounds": [-2.0, 8.0, -4.0, 4.0],
        "obstacles": [[2.0, -1.2, 0.6, 2.4], [4.5, 0.8, 0.8, 2.0]],
        "default_waypoints": [[0.0, 0.0], [1.5, 2.2], [3.2, 2.2], [6.0, 0.0]],
    },
    "rough": {
        "id": "rough",
        "label": "Rough / 复杂地形",
        "kind": "terrain",
        "mode": "navigation",
        "description": "粗糙地形任务元数据；native mjlab terrain adapter 可接入。",
        "bounds": [-2.0, 8.0, -4.0, 4.0],
        "default_waypoints": [[0.0, 0.0], [2.0, 0.5], [4.0, -0.8], [6.0, 0.0]],
    },
    "stairs": {
        "id": "stairs",
        "label": "Stairs / 特定任务",
        "kind": "terrain",
        "mode": "navigation",
        "description": "楼梯路线任务元数据；通过 Scenario Contract 绑定实际地形。",
        "bounds": [-2.0, 8.0, -4.0, 4.0],
        "default_waypoints": [[0.0, 0.0], [2.0, 0.0], [4.0, 0.8], [6.0, 1.6]],
    },
}


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
    map_id: str = "flat"
    mode: str = Field(default="basic", pattern="^(basic|navigation)$")
    episode_length_s: float = Field(default=60.0, gt=0.0, le=600.0)


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
        leg_count = max(1, self.env.action_dim // 3)
        for leg in range(leg_count):
            offset = 0.0 if leg % 2 == 0 else math.pi
            base = leg * 3
            if base + 2 >= len(action):
                break
            action[base] = np.clip(0.08 * vy + 0.06 * wz, -1.0, 1.0)
            action[base + 1] = np.clip(0.20 * vx * math.sin(phase + offset), -1.0, 1.0)
            action[base + 2] = np.clip(-0.25 * abs(vx) * max(0.0, math.sin(phase + offset)), -1.0, 1.0)
        return action

    def step(self, request: SimulationStepRequest) -> dict[str, Any]:
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
        }


sessions: dict[str, SimulationSession] = {}


@router.get("/maps")
async def list_maps() -> dict[str, Any]:
    return {"maps": list(MAPS.values()), "count": len(MAPS)}


@router.post("/sessions")
async def create_session(request: SimulationSessionRequest) -> dict[str, Any]:
    if request.map_id not in MAPS:
        raise HTTPException(status_code=404, detail=f"Unknown simulation map: {request.map_id}")
    preset = get_robot_preset(request.robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot preset: {request.robot_id}")
    mode = request.mode
    if MAPS[request.map_id]["mode"] == "navigation":
        mode = "navigation"
    from contracts.robot_contract_v2 import RobotContractV2

    contract = RobotContractV2(**preset["contract"])
    env = ContractMujocoEnv(contract, num_envs=1, episode_length_s=request.episode_length_s, scene_geoms=_scene_geoms(request.map_id))
    session_id = f"sim_{uuid.uuid4().hex[:12]}"
    session = SimulationSession(session_id, request.robot_id, request.map_id, mode, env)
    sessions[session_id] = session
    return {"success": True, "session_id": session_id, "map": MAPS[request.map_id], "frame": session.reset()}


def _get_session(session_id: str) -> SimulationSession:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Simulation session not found: {session_id}")
    return session


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session = _get_session(session_id)
    return {"success": True, "frame": session.last_frame, "map": MAPS[session.map_id]}


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
    sessions.pop(session_id, None)
    return {"success": True, "session_id": session_id}
