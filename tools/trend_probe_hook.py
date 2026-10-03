"""trend_probe 的**训练内钩子消费者**——Phase 3 首个 hooks.on_checkpoint 客户。

架构位置（00_know/08 §2 hooks seam）：native_worker 每次 save checkpoint 后调用
本模块 `run`，趋势探针在训练进行中自动出 verdict——**判负早停的地基**
（用户口径：~250 轮出趋势 / reward 50 轮 <2% 平台 = 收敛点错即配方判负）。

fail-soft 纪律（与 training_hooks 同级）：探针失败只写 status，不弄死训练。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 趋势验收默认档（与 tools/trend_probe.py 的常量同值——那份是单一真值，这里只引用）
DEFAULT_CASES = "0.5,0,0"


def run(ctx: dict, *, cases: str = DEFAULT_CASES, trend_ratio: float | None = None) -> None:
    """on_checkpoint 消费者：当前 checkpoint → trend_probe 测评 → 写 <run>/trend_hook.json。"""
    import importlib

    probe = importlib.import_module("tools.trend_probe")
    run_dir = Path(str(ctx.get("run_dir") or ""))
    checkpoint = Path(str(ctx.get("checkpoint_path") or ""))
    if not run_dir.is_dir() or not checkpoint.is_file():
        print(f"[trend_hook] 跳过（run/checkpoint 不存在）: {run_dir} / {checkpoint.name}")
        return

    robot = str(ctx.get("robot_id") or _robot_from_run(run_dir) or "")
    if not robot:
        print("[trend_hook] 跳过（robot_id 未知）")
        return

    export_dir = run_dir / "exported"
    export_dir.mkdir(exist_ok=True)
    out_onnx = export_dir / f"trend_{checkpoint.stem}.onnx"
    try:
        cmd = [
            str(_adapter_python()), str(ROOT / "tools" / "export_checkpoint_onnx.py"),
            "--run", str(run_dir), "--checkpoint", checkpoint.name,
            "--out", str(out_onnx), "--no-verify",
        ]
        import subprocess

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0 or not out_onnx.is_file():
            print(f"[trend_hook] checkpoint 导出失败: {proc.stderr[-200:]}")
            return
    except Exception as exc:  # noqa: BLE001
        print(f"[trend_hook] checkpoint 导出异常: {type(exc).__name__}: {str(exc)[:150]}")
        return

    # 探针模块化消费：直接调它的解析/判决纯函数（不经 subprocess），导出走上面
    status = {"schema": "trend-hook-1.0", "checkpoint": checkpoint.name, "verdict": "not-evaluated"}
    try:
        import numpy as np
        import onnxruntime as ort
        import mujoco
        from adapters.mjlab import policy_acceptance as pa
        from backend.policy_artifacts import load_index, observation_kind_for, onnx_obs_dim
        from tools.check_user_criteria import clamp_to_ranges, run_case

        sim_cfg = json.loads((ROOT / "assets" / "robots" / robot / "simulation/config.json").read_text(encoding="utf-8-sig"))
        model = pa.load_package_model(pkg_path := ROOT / "assets" / "robots" / robot, sim_cfg)
        model.opt.timestep = 1.0 / 50
        ref_entry = next((e for e in sim_cfg["policies"]
                          if (e.get("contract") or {}).get("observation_kind") not in (None, "", "unknown")), None)
        width = onnx_obs_dim(out_onnx)
        kind = observation_kind_for(robot, width) if width else None
        contract_block = dict((ref_entry or {}).get("contract") or {})
        if kind:
            contract_block["observation_kind"] = kind
        if width:
            contract_block["obs_dim"] = width
        entry = {"id": f"trend-hook-{checkpoint.stem}", "path": str(out_onnx), "contract": contract_block}
        from backend.policy_artifacts import policy_blob_path

        blob = policy_blob_path(entry, robot_dir=pkg_path, index=load_index()) or out_onnx
        contract = pa.PackageContract(pkg_path, {**entry, "path": str(blob)})
        sess = ort.InferenceSession(str(blob), providers=["CPUExecutionProvider"])
        cases_out = []
        for case in cases.split(";"):
            c = clamp_to_ranges([float(x) for x in case.split(",")], contract)
            r = run_case(sess, contract, model, tuple(c))
            main = int(np.argmax(np.abs(c))) if np.abs(c).max() > 0 else -1
            cases_out.append({"command": c, "main_axis": main,
                              "v_mean": r.get("v_mean"), "pass": r.get("pass"), "reason": r.get("reason")})
        ratio = trend_ratio if trend_ratio is not None else probe.TREND_RATIO_DEFAULT
        trend = None
        for c in cases_out:
            m = c["main_axis"]
            if m >= 0 and c["v_mean"] and abs(float(c["command"][m])) > 0:
                if abs(c["v_mean"][m]) / abs(float(c["command"][m])) >= ratio:
                    trend = checkpoint.stem
                    break
        status.update({"cases": cases_out, "trend_at_checkpoint": trend,
                       "verdict": "trend" if trend else "no_trend_yet"})
    except Exception as exc:  # noqa: BLE001
        status.update({"verdict": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"})

    out = run_dir / "trend_hook.json"
    history = []
    if out.is_file():
        try:
            prev = json.loads(out.read_text(encoding="utf-8-sig"))
            history = prev.get("history") or []
        except Exception:
            history = []
    history.append(status)
    out.write_text(json.dumps({"schema": "trend-hook-1.0", "history": history},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[trend_hook] {checkpoint.name}: {status.get('verdict')} "
          + json.dumps([c.get("v_mean") for c in status.get("cases", [])])[:120])


def _robot_from_run(run_dir: Path) -> str | None:
    try:
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8-sig"))
        return record.get("robot_id") or None
    except Exception:
        return None


def _adapter_python() -> Path:
    from contracts.path_bootstrap import adapter_python

    return adapter_python(default=ROOT / "adapters" / "mjlab" / ".venv")


def _load_trend_probe():
    import importlib.util

    spec = importlib.util.spec_from_file_location("trend_probe", ROOT / "tools" / "trend_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
