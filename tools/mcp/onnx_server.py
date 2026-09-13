"""MCP: 策略 onnx 检查与单帧推理。

落点：``tools/evaluator.py``（``PolicyEvaluator``）、``assets/robots/*/simulation/policies/*.onnx``
（45 条仿真策略）、``adapters/mjlab/onnx_exporter.py``。

为什么值得做成 MCP：本仓刚做过一次"浏览器 ↔ Python 推理链 100% 对拍"
（见 00_know/50_方案与清单/进度流水.md 续六），这类对拍每次都要重写脚本；
把"查输入输出维 / 读 metadata_props / 单帧推理"固化下来，对拍只需一次调用。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.mcp._rpc import run_server  # noqa: E402


def _resolve_policy(policy: str) -> Path:
    """接受 .onnx 路径、模型名或机型名（机型名 → 候选清单，报错时列出）。"""
    candidate = Path(policy)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    if candidate.is_file():
        return candidate

    hits = sorted(ROOT.glob(f"**/{policy}")) if policy.endswith(".onnx") else []
    hits = [p for p in hits if p.is_file()]
    if hits:
        return hits[0]

    pkg = ROOT / "assets" / "robots" / policy
    if pkg.is_dir():
        found = sorted(pkg.rglob("*.onnx"))
        if len(found) == 1:
            return found[0]
        if found:
            raise FileNotFoundError(
                f"{policy} 有 {len(found)} 个策略，请指定具体文件：\n  "
                + "\n  ".join(str(p.relative_to(ROOT)) for p in found[:20])
            )
    raise FileNotFoundError(f"找不到策略: {policy}")


def inspect_model(policy: str) -> object:
    """输入/输出张量名、形状（None 表示动态轴）、metadata_props、算子集版本。"""
    import onnxruntime as ort

    path = _resolve_policy(policy)
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    meta = sess.get_modelmeta()
    return {
        "path": str(path.relative_to(ROOT)),
        "size_bytes": path.stat().st_size,
        "inputs": [{"name": i.name, "shape": i.shape, "type": i.type} for i in sess.get_inputs()],
        "outputs": [{"name": o.name, "shape": o.shape, "type": o.type} for o in sess.get_outputs()],
        "metadata_props": dict(meta.custom_metadata_map or {}),
    }


def infer_once(policy: str, feed: dict | None = None) -> object:
    """跑一帧推理，返回输出的形状与统计量（不返回全部数值，避免刷屏）。

    ``feed`` 省略时按输入声明自动造零输入 —— 目的是**验证链路可跑通**，
    不是验证策略行为（"推理链对拍"要用真实帧数据）。
    """
    import numpy as np
    import onnxruntime as ort

    path = _resolve_policy(policy)
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])

    feeds: dict[str, np.ndarray] = {}
    for inp in sess.get_inputs():
        if feed and inp.name in feed:
            arr = np.asarray(feed[inp.name], dtype=np.float32).reshape(inp.shape)
            feeds[inp.name] = arr
            continue
        shape = [d if isinstance(d, int) and d > 0 else 1 for d in inp.shape]
        feeds[inp.name] = np.zeros(shape, dtype=np.float32)

    outs = sess.run(None, feeds)
    summary = []
    for out, arr in zip(sess.get_outputs(), outs):
        a = np.asarray(arr, dtype=np.float32)
        summary.append({
            "name": out.name,
            "shape": list(a.shape),
            "min": round(float(a.min()), 6),
            "max": round(float(a.max()), 6),
            "mean": round(float(a.mean()), 6),
            "has_nan": bool(np.isnan(a).any()),
        })
    return {"path": str(path.relative_to(ROOT)), "fed": {k: list(v.shape) for k, v in feeds.items()}, "outputs": summary}


TOOLS = [
    {
        "name": "inspect_model",
        "description": "查 onnx 输入输出张量名/形状与 metadata_props",
        "inputSchema": {
            "type": "object",
            "properties": {"policy": {"type": "string", "description": ".onnx 路径、模型文件名或机型名"}},
            "required": ["policy"],
        },
    },
    {
        "name": "infer_once",
        "description": "跑一帧推理，返回输出形状与统计量（默认零输入，只验链路）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "policy": {"type": "string"},
                "feed": {"type": "object", "description": "可选，{输入名: 嵌套数组}"},
            },
            "required": ["policy"],
        },
    },
]

_DISPATCH = {
    "inspect_model": lambda a: inspect_model(a["policy"]),
    "infer_once": lambda a: infer_once(a["policy"], a.get("feed")),
}


def call(name: str, args: dict) -> object:
    return _DISPATCH[name](args)


if __name__ == "__main__":
    run_server(
        "legged-studio-onnx",
        "0.1.0",
        TOOLS,
        call,
        instructions="策略 onnx 检查：IO 契约与单帧推理链路验证。",
    )
