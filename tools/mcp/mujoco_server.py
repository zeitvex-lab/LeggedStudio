"""MCP: MuJoCo 模型查询与无头稳定测试。

落点：``tools/sim2sim_headless.py``（CPU 验收器）、``adapters/mjlab/scene_builder.py``
（MJCF 可加载性探针）、``assets/robots/*/model/``。

为什么值得做成 MCP：agent 回答"这机型 MJCF 能不能编译/关节叫什么/物理跑 N 秒
稳不稳"目前必须写一次性脚本。这里把三件最常用的事固化成工具，且**不复制**
``sim2sim_headless.py`` 的验收语义（那是门禁，这个只是探针）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.mcp._rpc import run_server  # noqa: E402

ROBOTS_DIR = ROOT / "assets" / "robots"


def _resolve_model(robot_or_path: str) -> Path:
    """接受机型名或相对路径；返回可编译的 MJCF 入口。"""
    candidate = Path(robot_or_path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    if candidate.is_file():
        return candidate

    pkg = ROBOTS_DIR / robot_or_path
    if not pkg.is_dir():
        raise FileNotFoundError(f"机型或路径不存在: {robot_or_path}")
    # 包内入口优先 robot.xml，其次深度优先找第一个 xml（跳过 scene/terrain 类）。
    preferred = pkg / "model" / "robot.xml"
    if preferred.is_file():
        return preferred
    xmls = sorted(p for p in pkg.rglob("*.xml") if "assets" not in p.parts)
    scene_like = [p for p in xmls if "scene" in p.name or "terrain" in p.name or "map" in p.name]
    (scene_like or xmls or [None])[0]
    pick = next((p for p in xmls if p not in scene_like), None) or (xmls[0] if xmls else None)
    if pick is None:
        raise FileNotFoundError(f"{robot_or_path} 里没有 .xml")
    return pick


def load_model(robot_or_path: str) -> object:
    """编译 MJCF，返回维度摘要。失败即返回错误原因（不抛）。"""
    import mujoco

    path = _resolve_model(robot_or_path)
    try:
        model = mujoco.MjModel.from_xml_path(str(path))
    except Exception as exc:  # noqa: BLE001 - 编译失败本身就是要看的诊断信息
        return {"ok": False, "model": str(path.relative_to(ROOT)), "error": str(exc)}
    return {
        "ok": True,
        "model": str(path.relative_to(ROOT)),
        "nq": model.nq,
        "nv": model.nv,
        "nu": model.nu,
        "nbody": model.nbody,
        "ngeom": model.ngeom,
        "timestep": float(model.opt.timestep),
    }


def list_joints(robot_or_path: str) -> object:
    """列模型里的关节（含类型与自由度）—— 与契约 ``action.joint_order`` 对照用。"""
    import mujoco

    path = _resolve_model(robot_or_path)
    model = mujoco.MjModel.from_xml_path(str(path))
    names, kinds = [], []
    for jid in range(model.njnt):
        names.append(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, jid))
        kinds.append(int(model.jnt_type[jid]))
    return {"model": str(path.relative_to(ROOT)), "count": model.njnt, "joints": names, "types": kinds}


def stability_probe(robot_or_path: str, seconds: float = 3.0, settle: float = 0.5) -> object:
    """零控制输入跑 N 秒：报告基座高度变化与是否翻倒。

    **这不是门禁**（门禁是 ``tools/sim2sim_headless.py``），只是"模型/坐标系是否
    明显不对"的快速探针：真策略稳定性必须带 onnx 跑。
    """
    import mujoco
    import numpy as np

    path = _resolve_model(robot_or_path)
    model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)

    n_settle = int(settle / model.opt.timestep)
    for _ in range(n_settle):
        mujoco.mj_step(model, data)

    # 找 root body 的高度与重力方向投影（自由关节机型才有意义）。
    heights, quats = [], []
    n_steps = int(seconds / model.opt.timestep)
    for _ in range(n_steps):
        mujoco.mj_step(model, data)
        heights.append(float(data.qpos[2]) if model.nq > 2 else 0.0)
        quats.append([float(x) for x in data.qpos[3:7]] if model.nq >= 7 else [1, 0, 0, 0])

    q = np.array(quats)
    # 四元数 [w,x,y,z] 的 z 轴在世界系中的 z 分量：|cos(tilt)|，1 = 完全竖直。
    up_z = 1 - 2 * (q[:, 1] ** 2 + q[:, 2] ** 2)
    return {
        "model": str(path.relative_to(ROOT)),
        "seconds": seconds,
        "steps": n_steps,
        "z_start": round(heights[0], 4),
        "z_end": round(heights[-1], 4),
        "z_min": round(min(heights), 4),
        "upright_min": round(float(up_z.min()), 4),
        "fell": bool(up_z.min() < 0.5),
        "note": "零控制探针：无 PD hold、无策略，翻倒不一定是模型错误（悬空/倒立摆结构属正常）",
    }


TOOLS = [
    {
        "name": "load_model",
        "description": "编译机型 MJCF 并返回维度摘要（nq/nv/nu/timestep），编译失败返回原因",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot_or_path": {"type": "string", "description": "机型目录名或 .xml 相对路径"},
            },
            "required": ["robot_or_path"],
        },
    },
    {
        "name": "list_joints",
        "description": "列模型内关节名与类型（与契约 action.joint_order 对照）",
        "inputSchema": {
            "type": "object",
            "properties": {"robot_or_path": {"type": "string"}},
            "required": ["robot_or_path"],
        },
    },
    {
        "name": "stability_probe",
        "description": "零控制跑 N 秒，报告基座高度与翻倒判定（快速探针，非验收门禁）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot_or_path": {"type": "string"},
                "seconds": {"type": "number", "description": "默认 3.0"},
                "settle": {"type": "number", "description": "先空跑多久再采样，默认 0.5"},
            },
            "required": ["robot_or_path"],
        },
    },
]

_DISPATCH = {
    "load_model": lambda a: load_model(a["robot_or_path"]),
    "list_joints": lambda a: list_joints(a["robot_or_path"]),
    "stability_probe": lambda a: stability_probe(
        a["robot_or_path"], float(a.get("seconds", 3.0)), float(a.get("settle", 0.5))
    ),
}


def call(name: str, args: dict) -> object:
    return _DISPATCH[name](args)


if __name__ == "__main__":
    run_server(
        "legged-studio-mujoco",
        "0.1.0",
        TOOLS,
        call,
        instructions="MuJoCo 模型查询：编译探针、关节清单、零控制稳定探针。验收门禁请用 tools/sim2sim_headless.py。",
    )
