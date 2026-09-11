"""Local RoboLab WebUI server.

This intentionally lives outside ``src/robolab``.  It is a small bridge for
the first UI milestone and can later be replaced by a richer API service
without changing the training backends.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
import xml.etree.ElementTree as ET
import base64
import shutil
import zipfile
import re
import struct
import sys
import socket
import time
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from robolab.tasks import get_task_spec, list_task_specs, resolve_training_recipe

WEB = ROOT / "webui"
PROJECTS = ROOT / "webui" / "projects"
UPLOADS = ROOT / "webui" / "uploads"
DERIVED = ROOT / "webui" / "derived"
PROJECTS.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
DERIVED.mkdir(parents=True, exist_ok=True)
RUNS: dict[str, dict] = {}
TOOLS: dict[str, dict] = {}


def resolve_run_dir(value: object) -> Path:
    run_dir = Path(str(value or "logs/webui")).expanduser()
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    return run_dir.resolve()


def latest_checkpoint(run_dir: Path) -> Path | None:
    def iteration(path: Path) -> int:
        match = re.search(r"model_(\d+)\.pt$", path.name)
        return int(match.group(1)) if match else -1
    candidates = sorted(run_dir.rglob("model_*.pt"), key=lambda p: (iteration(p), p.stat().st_mtime))
    return candidates[-1] if candidates else None


def training_progress(run_dir: Path, log_text: str, max_iterations: int | None = None) -> dict:
    checkpoint = latest_checkpoint(run_dir)
    current = -1
    if checkpoint:
        match = re.search(r"model_(\d+)\.pt$", checkpoint.name)
        current = int(match.group(1)) if match else -1
    for pattern in (r"Learning iteration\s+(\d+)\s*/\s*(\d+)", r"iteration[=: ]+(\d+)\s*/\s*(\d+)"):
        matches = list(re.finditer(pattern, log_text, re.I))
        if matches:
            current = max(current, int(matches[-1].group(1)))
            max_iterations = int(matches[-1].group(2))
    rewards = []
    for match in re.finditer(r"(?:mean[_ ]reward|reward)[^0-9-]*(-?\d+(?:\.\d+)?)", log_text, re.I):
        try:
            rewards.append(float(match.group(1)))
        except ValueError:
            pass
    total = int(max_iterations or 0)
    recent = rewards[-100:]
    return {
        "current_iteration": max(current, 0),
        "max_iterations": total,
        "progress": min(1.0, max(0.0, current / total)) if total else 0.0,
        "reward_history": recent,
        "reward_latest": recent[-1] if recent else None,
        "reward_best": max(recent) if recent else None,
        "reward_mean_recent": sum(recent[-10:]) / len(recent[-10:]) if recent else None,
    }


def runtime_python(framework: str) -> str:
    if framework == "mjlab":
        return os.environ.get("ROBO_MJLAB_PYTHON", "/home/lxy/miniconda3/envs/robolab-mjlab16/bin/python")
    return os.environ.get("ROBO_ISAACGYM_PYTHON", "/home/lxy/miniconda3/envs/robolab-isaacgym/bin/python")


def build_train_command(body: dict, run_dir: Path) -> list[str]:
    framework = str(body.get("framework", "isaacgym"))
    command = [runtime_python(framework), "-m", "robolab.cli", "workflow", "run", "train",
               "--framework", framework, "--task", str(body.get("task", "a1")),
               "--method", str(body.get("method", "ppo")), "--num-envs", str(body.get("num_envs", 1)),
               "--max-iterations", str(body.get("iterations", 1)), "--run-dir", str(run_dir),
               "--checkpoint-interval", str(body.get("checkpoint_interval", 300)),
               "--seed", str(body.get("seed", 0))]
    if body.get("recipe_path"):
        command.extend(["--recipe", str(Path(body["recipe_path"]).resolve())])
    checkpoint = Path(str(body.get("checkpoint", ""))).expanduser()
    if checkpoint and not checkpoint.is_absolute():
        checkpoint = ROOT / checkpoint
    if checkpoint.is_file():
        command.extend(["--resume-from", str(checkpoint.resolve())])
    return command


def robots():
    result = []
    for path in sorted((ROOT / "resources" / "robots").iterdir()):
        if path.is_dir():
            models = [str(p.relative_to(ROOT)) for p in path.rglob("*.urdf")] + [
                str(p.relative_to(ROOT)) for p in path.rglob("*.xml")
            ]
            result.append({"id": path.name, "name": path.name.replace("_", " "), "models": models})
    return result


def methods():
    # Keep this endpoint dependency-light; the browser only needs selection metadata.
    try:
        from robolab.methods.registry import list_methods, get_method
        return [get_method(name).to_dict() for name in list_methods()]
    except Exception:
        return [{"method_id": "ppo", "display_name": "Proximal Policy Optimization", "frameworks": ["isaacgym", "mjlab"]}]


def tasks():
    return [spec.to_dict() for spec in list_task_specs(ROOT)]


def inspect_model(relative_path: str) -> dict:
    """Inspect URDF/MJCF structure without treating optional geometry as invalid."""
    candidate = (ROOT / relative_path).resolve()
    if ROOT not in candidate.parents or not candidate.is_file():
        raise FileNotFoundError("model must be an existing file inside the RoboLab workspace")
    root = ET.parse(candidate).getroot()
    links, joints, warnings, notes = [], [], [], []
    child_joint_types = {}
    for candidate_joint in root.findall(".//joint"):
        child = candidate_joint.find("child")
        if child is not None and child.attrib.get("link"):
            child_joint_types[child.attrib["link"]] = candidate_joint.attrib.get("type", "fixed")
    for link in root.findall(".//link"):
        inertial = link.find("inertial")
        collision = link.findall("collision")
        visual = link.findall("visual")
        mass = inertial.find("mass") if inertial is not None else None
        inertia = inertial.find("inertia") if inertial is not None else None
        inertial_origin = inertial.find("origin") if inertial is not None else None
        geometry = []
        for tag, elements in (("visual", visual), ("collision", collision)):
            for item in elements:
                mesh = item.find("geometry/mesh")
                box = item.find("geometry/box")
                sphere = item.find("geometry/sphere")
                origin = item.find("origin")
                mesh_file = mesh.attrib.get("filename") if mesh is not None else None
                resolved_mesh = None
                if mesh_file:
                    requested = mesh_file.replace("package://", "")
                    resolved = (candidate.parent / requested).resolve()
                    if not resolved.is_file():
                        matches = list(candidate.parent.parent.rglob(Path(requested).name))
                        resolved = matches[0] if matches else resolved
                    if resolved.is_file() and ROOT in resolved.parents:
                        resolved_mesh = str(resolved.relative_to(ROOT))
                geometry.append({"kind": tag, "mesh": mesh.attrib.get("filename") if mesh is not None else None,
                                 "resolved_mesh": resolved_mesh,
                                 "scale": mesh.attrib.get("scale") if mesh is not None else None,
                                 "box_size": box.attrib.get("size") if box is not None else None,
                                 "radius": sphere.attrib.get("radius") if sphere is not None else None,
                                 "xyz": origin.attrib.get("xyz", "0 0 0") if origin is not None else "0 0 0",
                                 "rpy": origin.attrib.get("rpy", "0 0 0") if origin is not None else "0 0 0"})
        link_name = link.attrib.get("name", "")
        auxiliary = bool(re.search(
            r"(?:rotor|calflower|dummy|optical_frame|(?:^|_)imu(?:_|$)|(?:^|_)radar(?:_|$)|"
            r"camera|lidar|shell|remote|handle|battery|docking|face_|hatch|contact_)",
            link_name, re.I))
        # Fixed joints are also used for contact bodies (for example feet), so
        # they must not be blanket-classified as auxiliary. Exempt only known
        # rotor, decoration, and sensor links from rigid-body completeness checks.
        role = "auxiliary" if auxiliary else "structural"
        links.append({"name": link_name, "role": role, "collision_count": len(collision),
                      "visual_count": len(visual), "geometry": geometry,
                      "mass": float(mass.attrib.get("value", 0)) if mass is not None else None,
                      "inertia": dict(inertia.attrib) if inertia is not None else None,
                      "inertial_origin": {
                          "xyz": inertial_origin.attrib.get("xyz", "0 0 0"),
                          "rpy": inertial_origin.attrib.get("rpy", "0 0 0"),
                      } if inertial_origin is not None else {"xyz": "0 0 0", "rpy": "0 0 0"}})
        if inertial is None and role == "structural" and child_joint_types.get(link_name) not in {None, "fixed"}:
            warnings.append(f"link {link_name} 缺少 inertial（可动刚体可能无法正确加载动力学）")
        if not collision and role == "structural":
            # Collision geometry is optional in URDF and many official assets
            # intentionally use visual-only links or parent-body collisions.
            notes.append(f"link {link_name} 未定义 collision（按 visual-only/父 body 碰撞处理）")
    for joint in root.findall(".//joint"):
        limit = joint.find("limit")
        axis = joint.find("axis")
        parent = joint.find("parent")
        child = joint.find("child")
        joint_origin = joint.find("origin")
        entry = {"name": joint.attrib.get("name", ""), "type": joint.attrib.get("type", "fixed"),
                 "parent": parent.attrib.get("link", "") if parent is not None else "",
                 "child": child.attrib.get("link", "") if child is not None else "",
                 "axis": (axis.attrib.get("xyz", "0 0 1") if axis is not None else "0 0 1"),
                 "xyz": joint_origin.attrib.get("xyz", "0 0 0") if joint_origin is not None else "0 0 0",
                 "rpy": joint_origin.attrib.get("rpy", "0 0 0") if joint_origin is not None else "0 0 0",
                 "lower": float(limit.attrib["lower"]) if limit is not None and "lower" in limit.attrib else None,
                 "upper": float(limit.attrib["upper"]) if limit is not None and "upper" in limit.attrib else None,
                 "effort": float(limit.attrib["effort"]) if limit is not None and "effort" in limit.attrib else None,
                 "velocity": float(limit.attrib["velocity"]) if limit is not None and "velocity" in limit.attrib else None}
        joints.append(entry)
        if entry["type"] != "fixed" and limit is None:
            warnings.append(f"joint {entry['name']} 缺少 limit")
        if entry["lower"] is not None and entry["upper"] is not None and entry["lower"] > entry["upper"]:
            warnings.append(f"joint {entry['name']} 的 lower 大于 upper")
    if not links and root.tag == "mujoco":
        joints = []
        warnings, notes = [], []
        for body in root.findall(".//body"):
            links.append({"name": body.attrib.get("name", ""), "role": "structural", "collision_count": len(body.findall("geom")), "mass": None, "inertia": None})
        for joint in root.findall(".//joint"):
            value_range = joint.attrib.get("range", "").split()
            joints.append({"name": joint.attrib.get("name", ""), "type": joint.attrib.get("type", "hinge"),
                           "parent": "", "child": "", "axis": joint.attrib.get("axis", "0 0 1"),
                           "lower": float(value_range[0]) if len(value_range) == 2 else None,
                           "upper": float(value_range[1]) if len(value_range) == 2 else None,
                           "effort": None, "velocity": None})
    return {"path": relative_path, "format": candidate.suffix.lstrip("."), "name": root.attrib.get("name", candidate.stem),
            "links": links, "joints": joints, "warnings": warnings, "notes": notes,
            "summary": {"links": len(links), "joints": len(joints), "warnings": len(warnings), "notes": len(notes)}}


def mesh_preview(relative_path: str, limit: int = 1800) -> dict:
    """Return a small point sample from an STL mesh for the dependency-free viewer."""
    candidate = (ROOT / relative_path).resolve()
    if ROOT not in candidate.parents or not candidate.is_file():
        raise FileNotFoundError("mesh must be inside the RoboLab workspace")
    raw = candidate.read_bytes()
    vertices = []
    if len(raw) >= 84:
        count = int.from_bytes(raw[80:84], "little")
        if 84 + count * 50 <= len(raw):
            for offset in range(84, 84 + count * 50, 50):
                for pos in (offset + 12, offset + 24, offset + 36):
                    vertices.append(list(struct.unpack_from("<fff", raw, pos)))
    if not vertices:
        text = raw.decode("utf-8", errors="ignore")
        vertices = [[float(x), float(y), float(z)] for x, y, z in re.findall(r"vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", text)]
    if not vertices:
        raise ValueError("unsupported or empty STL mesh")
    stride = max(1, len(vertices) // limit)
    sample = vertices[::stride][:limit]
    mins = [min(point[i] for point in vertices) for i in range(3)]
    maxs = [max(point[i] for point in vertices) for i in range(3)]
    return {"path": relative_path, "vertices": sample, "bounds": {"min": mins, "max": maxs}, "total_vertices": len(vertices)}


def safe_name(value: object, fallback: str = "untitled") -> str:
    cleaned = "".join(c for c in str(value or fallback) if c.isalnum() or c in "-_ ").strip().replace(" ", "_")
    return cleaned or fallback


def compatibility(body: dict) -> dict:
    issues, warnings = [], []
    model = inspect_model(str(body.get("model", "")))
    method_id = str(body.get("method", "ppo"))
    method_spec = next((item for item in methods() if item.get("method_id") == method_id), None)
    framework = str(body.get("framework", "isaacgym"))
    task_spec = None
    try:
        task_spec = get_task_spec(str(body.get("task", "")), framework=framework, method=method_id, root=ROOT)
    except Exception as exc:
        issues.append(f"任务未注册: {exc}")
    if method_spec is None:
        issues.append(f"算法插件不存在: {method_id}")
    elif framework not in method_spec.get("frameworks", []):
        issues.append(f"{method_id} 不支持 backend {framework}")
    actuated = [joint for joint in model["joints"] if joint["type"] != "fixed"]
    mapping = body.get("mapping", {}) or {}
    missing = [joint["name"] for joint in actuated if not mapping.get(joint["name"], joint["name"])]
    if missing:
        issues.append(f"存在未映射关节: {', '.join(missing[:8])}")
    expected = body.get("expected_action_dim")
    if expected is not None and int(expected) != len(actuated):
        issues.append(f"动作维度不匹配: 模型 {len(actuated)}，算法 {expected}")
    if int(body.get("num_envs", 1)) < 1:
        issues.append("并行环境数必须大于 0")
    if int(body.get("iterations", 1)) < 1:
        issues.append("训练轮次必须大于 0")
    a1_only_methods = {"cts", "teacher_student", "dreamwaq", "ppo_ee"}
    if method_id in a1_only_methods and "resources/robots/unitree_a1/" not in str(body.get("model", "")):
        issues.append(f"{method_id} 当前只支持 Unitree A1 模型")
    # A registered TaskSpec is already the compatibility proof. Do not emit
    # the old blanket A1 warning for RoboLab-owned Go2/Anymal/etc. tasks.
    if task_spec is not None:
        expected_model = task_spec.models.get(framework)
        if expected_model and str(body.get("model", expected_model)) != expected_model:
            issues.append(f"模型与 TaskSpec 不一致：该任务训练资产为 {expected_model}")
        if task_spec.action_dim != len(actuated):
            issues.append(f"动作维度不匹配：TaskSpec {task_spec.action_dim}，模型 {len(actuated)}")
        try:
            resolve_training_recipe({**body, "run_dir": body.get("run_dir", "logs/webui")}, root=ROOT)
        except Exception as exc:
            issues.append(str(exc))
    return {"ok": not issues, "issues": issues, "warnings": warnings,
            "model_warnings": list(model["warnings"]), "model": model["summary"],
            "method": method_spec, "actuated_joints": len(actuated)}


def start_tool(tool: str, command: list[str], port: int) -> dict:
    current = TOOLS.get(tool)
    if current and current["process"].poll() is None:
        if current.get("command") == command:
            return {"status": "running", "port": port, "pid": current["process"].pid}
        try:
            os.killpg(current["process"].pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            current["process"].wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(current["process"].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            current["process"].wait(timeout=3)
        current.get("stream") and current["stream"].close()
        TOOLS.pop(tool, None)
    # The service may have been started by a previous WebUI process. Reuse an
    # already listening endpoint instead of launching a second copy that will
    # fail with "address already in use".
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return {"status": "running", "port": port, "url": f"http://127.0.0.1:{port}"}
    except OSError:
        pass
    try:
        tool_log = PROJECTS / f"tool_{safe_name(tool)}.log"
        stream = tool_log.open("w")
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            start_new_session=True,
        )
    except FileNotFoundError:
        return {"status": "unavailable", "error": f"未找到可执行文件: {command[0]}"}
    TOOLS[tool] = {"process": process, "port": port, "command": command, "log": str(tool_log.relative_to(ROOT)), "stream": stream}
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stream.flush()
            return {"status": "failed", "error": f"{tool} 启动失败（exit {process.returncode}）", "detail": tool_log.read_text(errors="replace")[-4000:]}
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return {"status": "started", "port": port, "pid": process.pid, "log": str(tool_log.relative_to(ROOT))}
        except OSError:
            time.sleep(0.2)
    return {"status": "starting", "port": port, "pid": process.pid, "log": str(tool_log.relative_to(ROOT))}


def stop_external_tool(port: int, marker: str) -> None:
    """Stop a stale RoboLab tool left by an earlier WebUI process."""
    try:
        output = subprocess.check_output(
            ["lsof", "-t", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return
    for raw_pid in output.split():
        try:
            pid = int(raw_pid)
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            if marker not in command:
                continue
            try:
                process_group = os.getpgid(pid)
                if process_group != os.getpgrp():
                    os.killpg(process_group, signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        except (OSError, ValueError):
            continue


def send_json(handler, value, status=200):
    payload = json.dumps(value, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/robots":
            return send_json(self, robots())
        if path == "/api/methods":
            return send_json(self, methods())
        if path == "/api/tasks":
            return send_json(self, tasks())
        if path == "/api/projects":
            return send_json(self, [p.stem for p in sorted(PROJECTS.glob("*.json"))])
        if path == "/api/project":
            name = parse_qs(urlparse(self.path).query).get("name", [""])[0]
            target = PROJECTS / (safe_name(name) + ".json")
            if target.is_file():
                return send_json(self, json.loads(target.read_text()))
            return send_json(self, {"error": "project not found"}, 404)
        if path == "/api/model":
            try:
                relative = parse_qs(urlparse(self.path).query).get("path", [""])[0]
                return send_json(self, inspect_model(relative))
            except Exception as exc:
                return send_json(self, {"error": str(exc)}, 400)
        if path == "/api/asset":
            try:
                query = parse_qs(urlparse(self.path).query)
                model = (ROOT / query.get("model", [""])[0]).resolve()
                mesh_name = query.get("path", [""])[0].replace("package://", "")
                asset = (model.parent / mesh_name).resolve()
                if not asset.is_file():
                    robot_root = next((parent for parent in model.parents if parent.parent == ROOT / "resources" / "robots"), model.parent)
                    matches = list(robot_root.rglob(Path(mesh_name).name))
                    asset = matches[0] if matches else asset
                if ROOT not in asset.parents or not asset.is_file():
                    raise FileNotFoundError("mesh asset not found")
                data = asset.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as exc:
                return send_json(self, {"error": str(exc)}, 404)
        if path == "/api/mesh":
            try:
                relative = parse_qs(urlparse(self.path).query).get("path", [""])[0]
                return send_json(self, mesh_preview(relative))
            except Exception as exc:
                return send_json(self, {"error": str(exc)}, 404)
        if path == "/api/tool/status":
            result = {}
            for name, value in TOOLS.items():
                result[name] = {"status": "running" if value["process"].poll() is None else "stopped",
                                "port": value["port"], "pid": value["process"].pid}
            return send_json(self, result)
        if path == "/api/run/latest":
            run_dir = resolve_run_dir(parse_qs(urlparse(self.path).query).get("run_dir", ["logs/webui"])[0])
            checkpoint = latest_checkpoint(run_dir)
            return send_json(self, {"run_dir": str(run_dir.relative_to(ROOT)) if ROOT in run_dir.parents else str(run_dir), "checkpoint": str(checkpoint.relative_to(ROOT)) if checkpoint and ROOT in checkpoint.parents else (str(checkpoint) if checkpoint else "")})
        if path.startswith("/workspace/"):
            try:
                asset = (ROOT / unquote(path.removeprefix("/workspace/"))).resolve()
                if ROOT not in asset.parents or not asset.is_file():
                    raise FileNotFoundError("workspace asset not found")
                content_types = {".urdf": "application/xml", ".xml": "application/xml", ".stl": "model/stl", ".dae": "model/vnd.collada+xml", ".obj": "model/obj", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
                data = asset.read_bytes()
                self.send_response(200); self.send_header("Content-Type", content_types.get(asset.suffix.lower(), "application/octet-stream")); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
            except Exception as exc:
                return send_json(self, {"error": str(exc)}, 404)
        static_files = {"/": ("index.html", "text/html; charset=utf-8"),
                        "/index.html": ("index.html", "text/html; charset=utf-8"),
                        "/viewer.js": ("viewer.js", "text/javascript; charset=utf-8"),
                        "/dist/three-viewer.js": ("dist/three-viewer.js", "text/javascript; charset=utf-8"),
                        "/app.js": ("app.js", "text/javascript; charset=utf-8")}
        if path in static_files:
            filename, content_type = static_files[path]
            data = (WEB / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size) or b"{}")
        except Exception as exc:
            return send_json(self, {"error": str(exc)}, 400)
        if path == "/api/compatibility":
            try:
                return send_json(self, compatibility({**body}))
            except Exception as exc:
                return send_json(self, {"ok": False, "issues": [str(exc)], "warnings": []}, 400)
        if path == "/api/project":
            name = str(body.get("name", "untitled")).strip() or "untitled"
            target = PROJECTS / (safe_name(name) + ".json")
            target.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
            return send_json(self, {"ok": True, "path": str(target.relative_to(ROOT))})
        if path == "/api/upload":
            filename = Path(str(body.get("filename", "robot.urdf"))).name
            suffix = Path(filename).suffix.lower()
            if suffix not in {".urdf", ".xml", ".zip"}:
                return send_json(self, {"error": "only .urdf, .xml and .zip files are accepted"}, 400)
            folder = UPLOADS / uuid.uuid4().hex[:10]
            folder.mkdir()
            try:
                raw = str(body.get("content", ""))
                if raw.startswith("data:"):
                    raw = raw.split(",", 1)[1]
                if suffix == ".zip":
                    archive = folder / filename
                    archive.write_bytes(base64.b64decode(raw))
                    with zipfile.ZipFile(archive) as zf:
                        members = [item for item in zf.infolist() if not Path(item.filename).is_absolute() and ".." not in Path(item.filename).parts]
                        if len(members) != len(zf.infolist()) or len(members) > 5000:
                            raise ValueError("ZIP 包含不安全路径或文件过多")
                        zf.extractall(folder / "package", members=members)
                    candidates = list((folder / "package").rglob("*.urdf")) + list((folder / "package").rglob("*.xml"))
                    if not candidates:
                        raise ValueError("ZIP 中未找到 URDF/XML")
                    target = candidates[0]
                else:
                    target = folder / filename
                    target.write_text(raw)
            except Exception as exc:
                shutil.rmtree(folder, ignore_errors=True)
                return send_json(self, {"error": f"上传失败: {exc}"}, 400)
            relative = str(target.relative_to(ROOT))
            try:
                result = inspect_model(relative)
            except Exception as exc:
                target.unlink(missing_ok=True)
                folder.rmdir()
                return send_json(self, {"error": f"model parse failed: {exc}"}, 400)
            return send_json(self, {"ok": True, "path": relative, "model": result})
        if path == "/api/derive":
            try:
                source = (ROOT / str(body["model"])).resolve()
                if ROOT not in source.parents or not source.is_file():
                    raise FileNotFoundError("source model does not exist")
                name = safe_name(body.get("name", source.stem))
                target_dir = DERIVED / name
                target_dir.mkdir(parents=True, exist_ok=True)
                model_target = target_dir / source.name
                model_target.write_bytes(source.read_bytes())
                profile = dict(body)
                profile["source_model"] = str(source.relative_to(ROOT))
                profile["derived_model"] = str(model_target.relative_to(ROOT))
                profile["profile_schema_version"] = 1
                (target_dir / "robot-profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
                return send_json(self, {"ok": True, "directory": str(target_dir.relative_to(ROOT)), "model": str(model_target.relative_to(ROOT))})
            except Exception as exc:
                return send_json(self, {"error": str(exc)}, 400)
        if path == "/api/train":
            check = compatibility(body)
            if not check["ok"]:
                return send_json(self, {"ok": False, "error": "训练前兼容性检查未通过", "compatibility": check}, 409)
            run_id = uuid.uuid4().hex[:10]
            base_dir = resolve_run_dir(body.get("run_dir", "logs/webui"))
            resume = body.get("resume_from")
            if resume:
                checkpoint = Path(str(resume)).expanduser()
                if not checkpoint.is_absolute():
                    checkpoint = ROOT / checkpoint
                run_dir = checkpoint.resolve().parent
            else:
                run_dir = base_dir / f"{safe_name(body.get('task', 'task'))}_{run_id}"
            run_dir.mkdir(parents=True, exist_ok=True)
            try:
                resolved = resolve_training_recipe({**body, "run_dir": str(run_dir)}, root=ROOT)
            except Exception as exc:
                return send_json(self, {"ok": False, "error": str(exc)}, 409)
            recipe_file = run_dir / "recipe.json"
            recipe_file.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n")
            (run_dir / "webui_recipe.json").write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
            profile_path = body.get("robot_profile")
            if profile_path:
                source_profile = (ROOT / str(profile_path)).resolve()
                if source_profile.is_file() and ROOT in source_profile.parents:
                    shutil.copy2(source_profile, run_dir / "robot_profile.json")
            command = build_train_command({
                **body,
                "framework": resolved["framework"],
                "task": resolved["backend_task"],
                "method": resolved["method"],
                "num_envs": resolved["num_envs"],
                "iterations": resolved["max_iterations"],
                "checkpoint_interval": resolved["checkpoint_interval"],
                "seed": resolved["seed"],
                "checkpoint": resolved.get("resume_from"),
                "recipe_path": recipe_file,
            }, run_dir)
            log = PROJECTS / f"run_{run_id}.log"
            RUNS[run_id] = {"status": "queued", "command": command, "log": str(log.relative_to(ROOT)), "run_dir": str(run_dir), "max_iterations": resolved["max_iterations"], "recipe": str(recipe_file.relative_to(ROOT))}
            def launch():
                environment = os.environ.copy()
                source_path = str(ROOT / "src")
                environment["PYTHONPATH"] = source_path + os.pathsep + environment.get("PYTHONPATH", "")
                with log.open("w") as stream:
                    if RUNS[run_id].get("stop_requested"):
                        RUNS[run_id]["status"] = "stopped"
                        return
                    RUNS[run_id]["status"] = "running"
                    process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                    RUNS[run_id]["process"] = process
                    result = process.wait()
                    if RUNS[run_id].get("stop_requested"):
                        RUNS[run_id]["status"] = "stopped"
                    else:
                        RUNS[run_id]["status"] = "completed" if result == 0 else "failed"
                    RUNS[run_id]["returncode"] = result
            threading.Thread(target=launch, daemon=True).start()
            return send_json(self, {"ok": True, "run_id": run_id, "log": str(log.relative_to(ROOT)), "run_dir": str(run_dir.relative_to(ROOT)) if ROOT in run_dir.parents else str(run_dir), "recipe": str(recipe_file.relative_to(ROOT))}, 202)
        if path == "/api/tool/start":
            tool = str(body.get("tool", ""))
            if tool == "tensorboard":
                run_dir = resolve_run_dir(body.get("run_dir", "logs/webui"))
                run_dir.mkdir(parents=True, exist_ok=True)
                framework = str(body.get("framework", "isaacgym"))
                python = runtime_python(framework)
                command = [python, str(ROOT / "webui" / "tensorboard_compat.py"),
                           "--logdir", str(run_dir), "--port", "6006", "--bind_all",
                           "--samples_per_plugin", "hparams=0"]
                result = start_tool(tool, command, 6006)
                return send_json(self, {**result, "url": "http://127.0.0.1:6006/?darkMode=true#timeseries", "logdir": str(run_dir)})
            if tool == "viser":
                checkpoint = Path(str(body.get("checkpoint", ""))).expanduser()
                if checkpoint and not checkpoint.is_absolute():
                    checkpoint = ROOT / checkpoint
                if not checkpoint.is_file():
                    checkpoint = latest_checkpoint(resolve_run_dir(body.get("run_dir", "logs/webui"))) or checkpoint
                if not checkpoint.is_file():
                    return send_json(self, {"status": "unavailable", "error": "请先填写有效 checkpoint 路径"}, 400)
                framework = str(body.get("framework", "isaacgym"))
                try:
                    task_value = get_task_spec(str(body.get("task", "")), framework=framework, method=str(body.get("method", "ppo")), root=ROOT).backend_task(framework, str(body.get("method", "ppo")))
                except Exception:
                    task_value = str(body.get("task", "a1"))
                command = [runtime_python(framework), "-m", "robolab.cli", framework, "play",
                           "--task", task_value, "--checkpoint", str(checkpoint.resolve()),
                           "--num-envs", "1", "--steps", "0", "--visualize"]
                if framework == "isaacgym":
                    command.extend(["--method", str(body.get("method", "ppo"))])
                # Replace a bridge left by an earlier WebUI session so its
                # checkpoint selector cannot keep showing historical models.
                stop_external_tool(8080, "viser_bridge")
                result = start_tool(tool, command, 8080)
                return send_json(self, {**result, "url": "http://localhost:8080", "checkpoint": str(checkpoint.resolve())})
            return send_json(self, {"error": "unknown tool"}, 400)
        if path == "/api/run/status":
            run_id = str(body.get("run_id", ""))
            log = PROJECTS / f"run_{run_id}.log"
            state = {key: value for key, value in RUNS.get(run_id, {"status": "unknown"}).items() if key != "process"}
            run_dir = resolve_run_dir(state.get("run_dir", body.get("run_dir", "logs/webui")))
            checkpoint = latest_checkpoint(run_dir)
            metrics = run_dir / "training_metrics.json"
            generated = []
            if checkpoint:
                generated.append(f"最新 checkpoint: {checkpoint.relative_to(ROOT) if ROOT in checkpoint.parents else checkpoint}")
            if metrics.is_file():
                try:
                    rows = json.loads(metrics.read_text())
                    if rows:
                        row = rows[-1]
                        generated.append(f"iteration: {row.get('iteration', '?')} · mean_reward: {row.get('mean_reward', '?')}")
                except Exception:
                    pass
            full_output = log.read_text(errors="replace")[-1000000:] if log.exists() else ""
            output = full_output[-12000:]
            progress = training_progress(run_dir, full_output, state.get("max_iterations"))
            return send_json(self, {"run_id": run_id, "exists": log.exists(), "log": output or "\n".join(generated) or "等待训练输出…", "checkpoint": str(checkpoint.relative_to(ROOT)) if checkpoint and ROOT in checkpoint.parents else (str(checkpoint) if checkpoint else ""), **progress, **state})
        if path == "/api/run/stop":
            run_id = str(body.get("run_id", ""))
            state = RUNS.get(run_id)
            if not state:
                return send_json(self, {"ok": False, "error": "run 不存在"}, 404)
            process = state.get("process")
            if process is None or process.poll() is not None:
                state["stop_requested"] = True
                state["status"] = "stopped" if state.get("status") in {"queued", "running"} else state.get("status", "unknown")
                return send_json(self, {"ok": True, "status": state["status"]})
            state["stop_requested"] = True
            state["status"] = "stopping"
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            def force_stop():
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                        state["force_killed"] = True
                    except ProcessLookupError:
                        pass
            threading.Thread(target=force_stop, daemon=True).start()
            return send_json(self, {"ok": True, "status": "stopping", "run_id": run_id})
        self.send_error(404)


if __name__ == "__main__":
    port = int(os.environ.get("ROBO_WEBUI_PORT", "8765"))
    print(f"RoboLab WebUI: http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
