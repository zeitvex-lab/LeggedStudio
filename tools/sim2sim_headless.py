"""无头 CPU sim2sim 验收器（B0）。

用 onnxruntime 加载**部署版 onnx 策略** + MuJoCo CPU 步进，按任务族施加量化判据，
判定策略能否「站立」并完成对应任务（速度跟踪/站立/模仿/特技/跑酷）。观测构造复用
`adapters/mjlab/policy_acceptance.py` 的契约驱动实现（与 web/sim2sim 同规格）。

用法：
  python tools/sim2sim_headless.py --robot unitree_go2w [--policy <id|file>]
      [--task-type velocity|stand|balance|imitation|acrobatics|parkour]
      [--seconds 6] [--seed 0] [--criteria-json thresholds.json]
      [--output-dir workspace/validation] [--write-acceptance]

退出码：0 全过 / 1 有 fail / 2 环境缺失（缺 mujoco/onnxruntime）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "adapters" / "mjlab"))

# 默认阈值：可按任务族用 --criteria-json 覆盖。
DEFAULT_CRITERIA = {
    # 硬门 = 存活/未摔 + 稳态姿态；vel_err 单列为质量指标（默认不卡门，见 --gate-tracking）。
    "stand": {"survival_min": 0.999, "height_ratio_min": 0.85, "tilt_max_deg": 20.0, "vel_err_max": 0.20},
    "balance": {"survival_min": 0.999, "height_ratio_min": 0.85, "tilt_max_deg": 20.0, "vel_err_max": 0.20},
    "velocity": {"survival_min": 0.999, "height_ratio_min": 0.70, "tilt_max_deg": 30.0, "vel_err_max": 0.20},
    "imitation": {"survival_min": 0.95},
    "acrobatics": {"survival_min": 0.9},
    "parkour": {"survival_min": 0.95},
}


def load_engine():
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "policy_acceptance", ROOT / "adapters" / "mjlab" / "policy_acceptance.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except ImportError as exc:  # mujoco/onnxruntime 缺失
        print(f"[sim2sim] 环境缺失：{exc}", file=sys.stderr)
        raise SystemExit(2)


def task_family(entry: dict, contract) -> str:
    explicit = contract.task_type or (entry.get("contract") or {}).get("task_type")
    if explicit:
        return str(explicit)
    # 只有纯 3 维速度命令才算 velocity；复合命令（如 microduck 13 维）按站立/任务
    # 固定指令评估，避免用速度扫描去测技能/站姿策略。
    return "velocity" if (contract.command_dims or 0) == 3 else "stand"


def evaluate_mode(metrics: dict, family: str, contract, criteria: dict,
                  gate_tracking: bool = False, ref_height: float | None = None) -> dict:
    """硬门 = 存活/未摔 + 稳态姿态；跟踪精度为质量指标，按 gate_tracking 决定是否卡门。

    高度基准优先用「默认姿静立参考高度」ref_height（多策略共享包级初高时更稳健）。
    """
    hard: list[dict] = []
    survival = float(metrics.get("survival_ratio") or 0.0)
    hard.append({"name": "survival", "ok": survival >= criteria["survival_min"],
                 "value": survival, "min": criteria["survival_min"]})
    if metrics.get("fell"):
        hard.append({"name": "not_fallen", "ok": False, "value": metrics.get("fell_at_s")})
    if family in ("stand", "balance", "velocity"):
        base = ref_height if (ref_height and ref_height > 1e-6) else contract.initial_height
        h_steady = metrics.get("height_steady")
        h_ratio = (float(h_steady) / max(base, 1e-6)) if h_steady is not None else metrics.get("height_steady_ratio")
        if h_ratio is None:
            h_ratio = (metrics.get("height_min") or 0.0) / max(base, 1e-6)
        hard.append({"name": "height_ratio_steady", "ok": h_ratio >= criteria["height_ratio_min"],
                     "value": round(float(h_ratio), 3), "min": criteria["height_ratio_min"],
                     "ref_height": round(float(base), 3)})
        roll_s = metrics.get("roll_steady_max_deg")
        pitch_s = metrics.get("pitch_steady_max_deg")
        tilt = max(roll_s if roll_s is not None else (metrics.get("roll_max_deg") or 0.0),
                   pitch_s if pitch_s is not None else (metrics.get("pitch_max_deg") or 0.0))
        hard.append({"name": "tilt_steady", "ok": tilt <= criteria["tilt_max_deg"],
                     "value": tilt, "max": criteria["tilt_max_deg"]})

    quality: list[dict] = []
    vel_err = metrics.get("vel_track_err")
    if vel_err is not None and family in ("stand", "balance", "velocity"):
        quality.append({"name": "vel_track_err", "ok": float(vel_err) <= criteria["vel_err_max"],
                        "value": vel_err, "max": criteria["vel_err_max"]})
    hard_ok = all(c["ok"] for c in hard)
    tracking_ok = all(c["ok"] for c in quality) if quality else True
    return {
        "ok": hard_ok and (tracking_ok or not gate_tracking),
        "hard_ok": hard_ok,
        "tracking_ok": tracking_ok,
        "checks": hard + quality,
    }


def evaluate_policy(engine, package_dir: Path, policy_rel: str, family: str | None,
                    criteria_all: dict, seconds: float, seed: int,
                    gate_tracking: bool = False) -> dict:
    import mujoco
    import onnxruntime as ort

    sim_cfg = json.loads((package_dir / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    policies = sim_cfg.get("policies") or []
    policy_path = package_dir / policy_rel
    entry = next((p for p in policies if str(p.get("path", "")).endswith(policy_path.name)), {})
    contract = engine.PackageContract(package_dir, entry)
    family = family or task_family(entry, contract)

    model = engine.load_package_model(package_dir, sim_cfg)
    model.opt.timestep = 1.0 / contract.physics_hz
    data = mujoco.MjData(model)
    try:
        ref_height = engine.static_stand_height(contract, model, data, engine.ObsBuilder(contract, model, data))
    except Exception:  # noqa: BLE001
        ref_height = None
    sess = ort.InferenceSession(str(policy_path), providers=["CPUExecutionProvider"])
    sess_enc = None
    if contract.encoder_rel:
        enc_path = Path(contract.encoder_rel)
        if not enc_path.is_absolute():
            enc_path = package_dir / enc_path
        sess_enc = ort.InferenceSession(str(enc_path), providers=["CPUExecutionProvider"])
    else:
        in_dim = sess.get_inputs()[0].shape[-1]
        if contract.total_obs_dim and in_dim != contract.total_obs_dim:
            return {"status": "dim_mismatch", "error": f"ONNX 输入 {in_dim} vs 契约 {contract.total_obs_dim}"}

    if family in ("imitation", "acrobatics", "parkour") or contract.observation_kind in engine._DEFERRED_KINDS:
        return {"status": "skipped", "reason": f"{family}/{contract.observation_kind} 需 MotionLoader/复合命令，走 Node 桥（obs_bridge.mjs）"}

    criteria = {**DEFAULT_CRITERIA[family], **(criteria_all.get(family) or {})}
    modes = [[0.0, 0.0, 0.0]] if family in ("stand", "balance") else engine.default_modes(contract.cmd_ranges)
    mode_reports = []
    for idx, cmd in enumerate(modes):
        obs = engine.ObsBuilder(contract, model, data)
        if sess_enc is not None:
            metrics = engine.run_encoder_mode(sess_enc, sess, contract, model, data, obs, cmd, seconds, seed + idx)
        else:
            metrics = engine.run_mode(sess, contract, model, data, obs, cmd, seconds, seed + idx)
        verdict = evaluate_mode(metrics, family, contract, criteria, gate_tracking, ref_height)
        mode_reports.append({"command": cmd, "metrics": metrics, "verdict": verdict})
    passed = sum(1 for m in mode_reports if m["verdict"]["ok"])
    return {
        "status": "ok",
        "task_family": family,
        "observation_kind": contract.observation_kind,
        "criteria": criteria,
        "modes": mode_reports,
        "passed": passed,
        "total": len(mode_reports),
        "verdict": "pass" if passed == len(mode_reports) else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="无头 CPU sim2sim 验收器")
    parser.add_argument("--robot", default=None, help="机型 id（缺省遍历全部内置包）")
    parser.add_argument("--policy", default=None, help="策略 id 或 onnx 文件名（缺省包内全部）")
    parser.add_argument("--task-type", default=None, choices=sorted(k for k in DEFAULT_CRITERIA))
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--criteria-json", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "workspace" / "validation")
    parser.add_argument("--write-acceptance", action="store_true",
                        help="同时写 <stem>.acceptance.json 到策略目录（供 browser-config 健康检查）")
    parser.add_argument("--gate-tracking", action="store_true",
                        help="把速度跟踪误差纳入硬门（默认只作质量指标，不卡站立/存活门）")
    args = parser.parse_args()

    engine = load_engine()
    criteria_all = {}
    if args.criteria_json and args.criteria_json.is_file():
        criteria_all = json.loads(args.criteria_json.read_text(encoding="utf-8"))

    packages = sorted((ROOT / "assets" / "robots").iterdir())
    results = []
    for pkg in packages:
        if not pkg.is_dir() or not (pkg / "simulation" / "config.json").is_file():
            continue
        if args.robot and pkg.name != args.robot:
            continue
        sim_cfg = json.loads((pkg / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
        entries = list(sim_cfg.get("policies") or [])
        for entry in entries:
            rel = str(entry.get("path") or "")
            if not rel:
                continue
            if args.policy and args.policy not in (entry.get("id"), Path(rel).name):
                continue
            try:
                report = evaluate_policy(engine, pkg, rel, args.task_type, criteria_all,
                                         args.seconds, args.seed, args.gate_tracking)
            except Exception as exc:  # noqa: BLE001
                report = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            record = {"robot": pkg.name, "policy": entry.get("id") or Path(rel).name, "onnx": rel, **report}
            results.append(record)
            flag = {"pass": "OK ", "fail": "!! ", "skipped": "SK ", "ok": "?? "}.get(report.get("verdict") or report.get("status"), "..")
            print(f"[{flag}] {pkg.name}/{record['policy']} -> {report.get('verdict') or report.get('status')}")

    report = {
        "schema": "sim2sim-headless-1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "seconds_per_mode": args.seconds,
        "seed": args.seed,
        "total": len(results),
        "passed": sum(1 for r in results if r.get("verdict") == "pass"),
        "failed": [r for r in results if r.get("verdict") == "fail" or r.get("status") == "error"],
        "skipped": [r for r in results if r.get("status") == "skipped"],
        "results": results,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "sim2sim-headless.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport: {out}")
    print(f"summary: {report['passed']} pass / {report['total']} total, "
          f"{len(report['skipped'])} skipped, {len(report['failed'])} failed")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
