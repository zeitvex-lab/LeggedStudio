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

import mimetypes

import numpy as np
import mujoco
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from adapters.mjlab.mujoco_env import ContractMujocoEnv
from backend.robot_presets import get_robot_preset
from backend.scenario_maps import MAPS
from contracts.role_resolver import RoleResolver
from contracts.scenario_contract import ScenarioContract


from backend.simulation_browser import (  # noqa: E402
    BROWSER_INITIAL_KEYFRAME, BROWSER_MESH_LIMIT_BYTES,
    _browser_package, _browser_package_root, _browser_asset_bytes,
    _read_simulation_config, _acceptance_report_path, _load_acceptance_report,
    _acceptance_health_check, _browser_asset_files, _initial_key_qpos,
    _mesh_aabb, _proxy_geom, _browser_model_xml, _find_package_root_quiet,
    _read_contract_v3, _browser_scene_file,
    _terrain_entries, common_map_entries, map_scene_xml, MAPS_ROOT,
    common_map_asset_files, read_common_map_asset,
)
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
# and several packages carry body meshes (b2/b2w base_link 17 MB) that are
# required for a non-blank render. Raise the cap so real robots stay intact;
# only pathological single files still fall back to primitive proxies.


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
    from contracts.path_bootstrap import adapter_python

    # 适配器 venv 落点由 path_bootstrap 统一解析；缺失时退回当前解释器
    # （验收脚本只用 mujoco/onnxruntime，不依赖训练栈）。
    adapter_interpreter = adapter_python(default=Path(__file__).resolve().parents[1] / "adapters" / "mjlab" / ".venv")
    python_exe = str(adapter_interpreter) if adapter_interpreter.exists() else sys.executable
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






















@router.get("/browser-config/{robot_id}")
async def browser_simulation_config(robot_id: str) -> dict[str, Any]:
    """Return the browser-native MuJoCo/Three.js package manifest."""
    root, preset = _browser_package(robot_id)
    # 能力门控（robot_lab register/detect 模式）：未声明 mujoco_sim 的包不进浏览器仿真
    package_capabilities = ((preset.get("robot_package") or {}).get("capabilities")) or []
    if "mujoco_sim" not in package_capabilities:
        raise HTTPException(status_code=422, detail=f"robot package {robot_id} does not declare the mujoco_sim capability")
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
    terrain_entries = _terrain_entries(simulation_config)
    terrain_options = []
    for entry in terrain_entries:
        label_source = entry.get("label") or entry.get("id") or Path(entry["path"]).stem
        terrain_options.append({
            "id": entry["id"],
            "label": str(label_source) if entry.get("label") else str(label_source).replace("_", " ").title(),
            "path": entry["path"],
        })
    if not terrain_options:
        scene_files = sorted((root / "simulation").glob("scene*.xml"))
        terrain_options = [
            {
                "id": path.stem,
                "label": "Default scene" if path.name == "scene.xml" else path.stem.removeprefix("scene_").replace("_", " ").title(),
                # Always package-root-relative: the browser writes files
                # under /working/platform/<rel> and loads them from there.
                "path": str(path.relative_to(root)).replace("\\", "/"),
            }
            for path in scene_files
        ]
    if not terrain_options:
        terrain_options = [{"id": "default", "label": "Default scene", "path": "simulation/scene.xml"}]
    # 公共地图库（assets/maps/）：所有机型共用，id 冲突时包声明（任务场景）优先。
    package_ids = {item["id"] for item in terrain_options}
    for common in common_map_entries():
        if common["id"] not in package_ids:
            terrain_options.append({"id": common["id"], "label": common["label"], "path": common["path"]})
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
    files.extend(
        str(item.relative_to(root)).replace("\\", "/")
        for item in sorted((root / "simulation").glob("*.xml"))
        if item.is_file() and item.name != "scene.xml"
    )
    files.extend(browser_assets)
    # 公共地图库的**非 XML 资产**（贴图）也要下发：地图 XML 引用 ``./imgs/label_*.png``，
    # 只给 xml 会让浏览器虚拟文件系统里编译失败（后端上一次就是这么踩的）。
    files.extend(f"maps/{name}" for name in common_map_asset_files())
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
            encoder_path = str(item.get("encoder") or "").replace("\\", "/")
            public_policies.append({
                "id": str(item.get("id") or Path(policy_path).stem),
                "label": str(item.get("label") or item.get("id") or Path(policy_path).stem),
                "url": f"/api/simulation/browser-package/{canonical_robot_id}/{policy_path}",
                "encoder_url": (f"/api/simulation/browser-package/{canonical_robot_id}/{encoder_path}" if encoder_path else None),
                "path": policy_path,
                # 仿真分层：advanced = 需要外部传感器或目标驱动的自动任务；basic = 盲狗/手动遥控。
                "sim_surface": str(item.get("sim_surface") or "basic"),
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
            sel_encoder = str(selected_policy.get("encoder") or "").replace("\\", "/")
            policy = {
                "id": str(selected_policy.get("id") or Path(policy_path).stem),
                "disabled": False,
                "onnx_url": f"/api/simulation/browser-package/{canonical_robot_id}/{policy_path}",
                "encoder_url": (f"/api/simulation/browser-package/{canonical_robot_id}/{sel_encoder}" if sel_encoder else None),
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
    # 演示策略（demo 卡素材）由包配置 demo_policies 声明——URL/维度/迭代数全部是数据
    for demo in simulation_config.get("demo_policies") or []:
        if not isinstance(demo, dict) or not demo.get("url"):
            continue
        demo_contract = {
            "obs_dim": int(demo.get("obs_dim") or 0),
            "action_dim": int(demo.get("action_dim") or len(order)),
            "history_len": int(demo.get("history_len") or 1),
            "action_scale": float(contract.get("action", {}).get("action_scale", 0.25)),
            "autoplay": False,
            "default_joint_angles": {name: float(value) for name, value in zip(order, default_pose)},
        }
        policy = {
            "id": str(demo.get("id") or Path(str(demo["url"])).stem),
            "disabled": False,
            "onnx_url": str(demo["url"]),
            "checkpoint_iteration": demo.get("checkpoint_iteration"),
            "health": {"status": "pass", "checks": [{"id": "bundled", "ok": True, "message": "Bundled demo policy"}]},
            "contract": demo_contract,
        }
        # demo 策略作为默认选择追加进列表——不得整体替换 public_policies
        # （曾把 go2 的 backflip/jump 从下拉里抹掉，URL 指定策略被静默回落）。
        public_policies.append({
            "id": policy["id"],
            "label": str(demo.get("label") or policy["id"]),
            "url": str(demo["url"]),
            "path": str(demo.get("path") or demo["url"]),
            "obs_dim": demo_contract["obs_dim"],
            "action_dim": demo_contract["action_dim"],
            "history_len": demo_contract["history_len"],
            "contract": demo_contract,
        })
        break
    simulation_control = simulation_config.get("control") if isinstance(simulation_config.get("control"), dict) else {}
    # B3/2：物理事实改由契约 v3 单一真值供给（contracts/physics_binding.py）。
    # simulation/config.json 仅作未迁移包的兼容回落，不再参与物理取值。
    from contracts.physics_binding import (
        action_scale_facts,
        payload_action_scale_view,
        payload_physics_view,
        payload_t_n_curve_view,
        physics_facts,
        t_n_curve_facts,
    )

    physics = physics_facts(root)
    payload_physics = payload_physics_view(physics)
    # D9/P1：速度限幅与 T-N 曲线一并交给浏览器——浏览器早就实现了 applyVelocityLimits /
    # applyMotorEnvelopes，但 `robot.control` 是**显式白名单**，这两个键此前不在其中 →
    # 契约里有值也到不了仿真。默认（无包声明）两者为空，浏览器各自早退，行为与现在一致。
    payload_t_n_curve = payload_t_n_curve_view(t_n_curve_facts(root))
    # B5/2：action_scale（标量 / 按角色 / 按关节）改由契约 v3 单一真值供给。
    # 不再读 simulation/config.json——轮足机型的轮档位在训练侧本就随任务变化
    # （go2w 实测：UniLab 类默认 10.0 / rough 任务 5.0 / 官方部署 yaml 35.0），
    # config 只是其中一个快照，继续读它必然与契约漂移。
    contract_v3_file = root / "contract_v3.json"
    if contract_v3_file.exists():
        action_payload = payload_action_scale_view(
            action_scale_facts(json.loads(contract_v3_file.read_text(encoding="utf-8-sig")))
        )
    else:
        legacy_scale = float(
            simulation_config.get("action_scale", contract.get("action", {}).get("action_scale", 0.25))
        )
        legacy_by_role = simulation_config.get("action_scale_by_role")
        action_payload = {
            "action_scale": legacy_scale,
            "action_scale_by_role": (
                legacy_by_role if isinstance(legacy_by_role, dict) else {"joint": legacy_scale}
            ),
            "action_scale_by_joint": simulation_config.get("action_scale_by_joint") or {},
        }
    action_scale = float(action_payload["action_scale"])
    decimation = int(
        physics["decimation"]
        or simulation_control.get("decimation")
        or contract.get("control", {}).get("decimation")
        or 4
    )
    physics_hz = float(
        physics["physics_hz"]
        or simulation_control.get("physics_hz")
        or contract.get("control", {}).get("physics_hz")
        or 1000
    )
    action_scale_by_role = action_payload["action_scale_by_role"]
    control_modes = simulation_config.get("control_modes")
    if not isinstance(control_modes, dict):
        control_modes = {"wheel": "velocity"}
    files = list(dict.fromkeys(files))
    # The revision busts the browser HTTP cache for every package file. It must
    # react to any served XML change (scenes included), not just the manifest.
    revision_sources = [root / "robot_package.json", root / "model" / "robot.xml"]
    revision_sources.extend(sorted((root / "simulation").glob("*.xml")))
    # 用 rglob：地图库的**贴图**变了也要换 revision（否则浏览器拿旧缓存里的贴图，
    # 改了图却看不到变化——这种"改了没生效"最难查）。
    revision_sources.extend(sorted(MAPS_ROOT.rglob("*")))
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
                "stiffness": payload_physics["stiffness"] or {"hip": 50.0, "thigh": 50.0, "calf": 50.0, "joint": 50.0},
                "damping": payload_physics["damping"] or {"hip": 1.5, "thigh": 1.5, "calf": 1.5, "wheel": 1.0, "joint": 1.5},
                "torque_limits": payload_physics["torque_limits"] or None,
                "action_scale_by_role": action_scale_by_role,
                "action_scale_by_joint": action_payload["action_scale_by_joint"],
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
                # 物理常量契约（armature/frictionloss 增量真值，覆盖 XML default）：
                # 训练 worker / 验收器 / 浏览器三方消费同一份数字，封死物理漂移。
                "armature": payload_physics["armature"] or {},
                "frictionloss": payload_physics["frictionloss"] or {},
                # 速度限幅（D9）：浏览器 applyVelocityLimits 读的就是这个键
                "velocity_limits": payload_physics.get("velocity_limits") or None,
                # T-N 曲线（P1）：浏览器 applyMotorEnvelopes 读的就是这个键；
                # 未声明任何曲线时为空 → 浏览器早退，行为不变。
                "motor_envelopes": payload_t_n_curve or None,
            },
        },
        "policy": policy,
        "sim": {
            "robot": canonical_robot_id,
            "custom_robot_mjcf_supported": True,
            # 取景参数由包配置声明（viewer_camera_scale / viewer_camera_max_distance），
            # 缺省为通用默认——消灭前端按机器人 ID 的三元式
            "viewer": {
                "camera_scale": float(simulation_config.get("viewer_camera_scale", 1.0)),
                "camera_max_distance": float(simulation_config.get("viewer_camera_max_distance", 22.0)),
            },
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
    normalized = asset_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("maps/"):
        rel = normalized[len("maps/"):]
        if rel.endswith(".xml"):
            return PlainTextResponse(map_scene_xml(rel[: -len(".xml")]), media_type="application/xml")
        # 地图贴图等静态资产：原样回传（不是 XML，不能走 map_scene_xml 的注入逻辑）
        payload = read_common_map_asset(rel)
        if payload is None:
            raise HTTPException(status_code=404, detail="common map asset not found")
        media_type = mimetypes.guess_type(rel)[0] or "application/octet-stream"
        return Response(content=payload, media_type=media_type)
    simulation_config = _read_simulation_config(root)
    for entry in _terrain_entries(simulation_config):
        if not entry.get("browser_scene"):
            continue
        if normalized == str(entry["path"]).lstrip("/"):
            return PlainTextResponse(
                _browser_scene_file(root, entry), media_type="application/xml"
            )
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
    # H3：planner 命令来源 ⇒ 装配导航计划（规划与到达判据只有一处实现，
    # 与浏览器侧的 /api/navigation/plan 共用，避免两端各算一套）。
    navigation = None
    if scenario.command_source == "planner":
        from backend.navigation_plan import build_navigation_payload

        navigation = await build_navigation_payload(request.map_id, scenario.waypoints)
    env = ContractMujocoEnv(contract, num_envs=1, episode_length_s=request.episode_length_s, scene_geoms=_scene_geoms(request.map_id))
    session_id = f"sim_{uuid.uuid4().hex[:12]}"
    session = SimulationSession(session_id, request.robot_id, request.map_id, mode, env)
    with sessions_lock:
        sessions[session_id] = session
    return {
        "success": True,
        "session_id": session_id,
        "scenario": scenario.to_payload(),
        "map": MAPS[request.map_id],
        "frame": session.reset(),
        # 仅 command_source=planner 时非空（其余场景保持原有形状，向后兼容）
        "navigation": navigation,
    }


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
