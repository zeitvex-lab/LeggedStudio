"""无头 CPU sim2sim 验收器（B0）。

用 onnxruntime 加载**部署版 onnx 策略** + MuJoCo CPU 步进，按任务族施加量化判据，
判定策略能否「站立」并完成对应任务（速度跟踪/站立/模仿/特技/跑酷）。观测构造复用
`adapters/mjlab/policy_acceptance.py` 的契约驱动实现（与 web/sim2sim 同规格）。

用法：
  python tools/sim2sim_headless.py --robot unitree_go2w [--policy <id|file>]
      [--task-type velocity|stand|balance|imitation|acrobatics|parkour]
      [--seconds 6] [--seed 0] [--criteria-json thresholds.json]
      [--output-dir workspace/validation] [--write-acceptance]

回归门禁（CI 用）：
  --baseline <baseline.json>  读取历史基线，仅当出现"新增失败/退化"时退出码非 0；
                              已记录的既存失败（如 go2 特技类）不阻塞 CI。
  --write-baseline <path>     把本次全量结果写成基线（本地定期刷新用）。

  退出码：无 --baseline 时 0 全过 / 1 有 fail；
          有 --baseline 时 0 无新增退化 / 1 有新增退化或基线不可读。
环境缺失（缺 mujoco/onnxruntime）退出码 2。
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
    # 操作类（抓取/搬运等）：站姿高度/倾角不是判据（任务本身就要求下蹲/伸出），只看存活。
    "manipulation": {"survival_min": 0.999},
    # Wuji Hand in-hand 重定向：成功 = 朝向误差 < 阈值保持 hold_steps 步（试次间聚合成功率）
    "reorient": {"success_rate_min": 0.8, "trials": 10, "trial_timeout_s": 14.0, "success_threshold_rad": 0.2, "success_hold_steps": 5},
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
    contract.motion_loader = engine.load_motion_loader(contract, package_dir)

    # Wuji Hand in-hand 立方体重定向：固定基座灵巧手，站立/速度判据不适用，
    # 走专用场景 + 成功判据（朝向误差 < 阈值保持 hold_steps 步）。
    if contract.observation_kind == "wuji_reorient_69":
        scene_rel = str(contract.contract.get("scene_path") or "simulation/scene_reorient.xml")
        model = engine.load_package_model(package_dir, sim_cfg, None, scene_rel=scene_rel)
        model.opt.timestep = 1.0 / contract.physics_hz
        data = mujoco.MjData(model)
        sess = ort.InferenceSession(str(policy_path), providers=["CPUExecutionProvider"])
        criteria = {"success_rate_min": 0.8, "trials": 10, "trial_timeout_s": 14.0,
                    "success_threshold_rad": 0.2, "success_hold_steps": 5}
        criteria.update(criteria_all.get("reorient") or {})
        trials = int(criteria["trials"])
        trial_seconds = max(float(seconds), float(criteria["trial_timeout_s"]))
        mode_reports = []
        for idx in range(trials):
            metrics = engine.run_wuji_reorient(
                sess, contract, model, data, engine.ObsBuilder(contract, model, data),
                trial_seconds, seed + idx,
                success_threshold=criteria["success_threshold_rad"],
                hold_steps=criteria["success_hold_steps"],
            )
            mode_reports.append({
                "command": [0.0, 0.0, 0.0],
                "metrics": metrics,
                "verdict": {"ok": metrics["success"] and not metrics["dropped"]},
            })
        passed = sum(1 for m in mode_reports if m["verdict"]["ok"])
        rate = passed / max(trials, 1)
        return {
            "status": "ok",
            "task_family": "reorient",
            "observation_kind": contract.observation_kind,
            "criteria": criteria,
            "modes": mode_reports,
            "passed": passed,
            "total": trials,
            "success_rate": round(rate, 3),
            "verdict": "pass" if rate >= criteria["success_rate_min"] else "fail",
        }

    # Go2 PIE 深度跑酷：多输入（proprio/proprio_history/depth_history/memory）+ GRU
    # memory + 深度相机，走专用回路（深度用 raycast 合成）。判据 = 存活 + 前进 + 姿态。
    if contract.observation_kind == "go2_pie_depth":
        scene_rel = contract.contract.get("scene_path")
        model = engine.load_package_model(package_dir, sim_cfg, None, scene_rel=scene_rel)
        model.opt.timestep = engine._PIE_CONTROL_DT / engine._PIE_PHYSICS_STEPS
        data = mujoco.MjData(model)
        sess = ort.InferenceSession(str(policy_path), providers=["CPUExecutionProvider"])
        criteria = {"survival_min": 0.9, "tilt_max_deg": 75.0, "forward_min_m": 0.3}
        criteria.update(criteria_all.get("parkour") or {})
        modes = [[0.6, 0.0, 0.0], [1.0, 0.0, 0.0]]
        mode_reports = []
        for idx, cmd in enumerate(modes):
            metrics = engine.run_pie_policy(
                sess, contract, model, data, engine.ObsBuilder(contract, model, data),
                cmd, max(float(seconds), 10.0), seed + idx,
            )
            ok = (
                (not metrics["fell"])
                and metrics["survival_ratio"] >= criteria["survival_min"]
                and metrics["tilt_max_deg"] <= criteria["tilt_max_deg"]
                and metrics["forward_max_m"] >= criteria["forward_min_m"]
            )
            mode_reports.append({"command": cmd, "metrics": metrics, "verdict": {"ok": ok}})
        passed = sum(1 for m in mode_reports if m["verdict"]["ok"])
        return {
            "status": "ok",
            "task_family": "parkour",
            "observation_kind": contract.observation_kind,
            "criteria": criteria,
            "modes": mode_reports,
            "passed": passed,
            "total": len(mode_reports),
            "verdict": "pass" if passed == len(mode_reports) else "fail",
        }

    motion = contract.observation_kind in ("go2_motion_69", "g1_motion_154")
    family = "imitation" if motion else (family or task_family(entry, contract))

    effort_override = {str(k).lower(): float(v) for k, v in (contract.contract.get("torque_limits") or {}).items()}
    model = engine.load_package_model(package_dir, sim_cfg, effort_override or None)
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

    if contract.observation_kind in engine._DEFERRED_KINDS:
        return {"status": "skipped", "reason": f"{contract.observation_kind} 布局待实现（Node 桥）"}
    if motion and contract.motion_loader is None:
        return {"status": "skipped", "reason": "缺少 motion_csv 参考动作"}
    if family in ("acrobatics", "parkour") and not motion:
        return {"status": "skipped", "reason": f"{family} 技能需参考动作/任务专属判据，静态站立判据不适用"}

    criteria = {**DEFAULT_CRITERIA[family], **(criteria_all.get(family) or {})}
    # 复合命令（command_dims != 3）一律单指令评估，即使 task_type 标为 velocity。
    single_mode = (contract.command_dims != 3) or family in ("stand", "balance", "imitation", "acrobatics", "parkour")
    modes = [[0.0, 0.0, 0.0]] if single_mode else engine.default_modes(contract.cmd_ranges)
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
    parser.add_argument("--baseline", type=Path, default=None,
                        help="历史基线 JSON；存在时只对'新增失败/退化'判非 0，已记录的既存失败放行")
    parser.add_argument("--write-baseline", type=Path, default=None,
                        help="把本次结果写成基线文件后退出（与 --baseline 互斥）")
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
            if args.write_acceptance and report.get("status") == "ok":
                policy_file = pkg / rel
                if policy_file.is_file():
                    sidecar = {
                        "schema": "policy-acceptance-1.0",
                        "generated_at": datetime.now().isoformat(timespec="seconds"),
                        "seconds_per_mode": (report.get("criteria") or {}).get("trial_timeout_s", args.seconds),
                        "seed": args.seed,
                        **report,
                    }
                    policy_file.with_name(policy_file.stem + ".acceptance.json").write_text(
                        json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
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

    if args.write_baseline:
        baseline_doc = {"schema": "sim2sim-headless-baseline-1.0", "results": _baseline_rows(results)}
        args.write_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.write_baseline.write_text(json.dumps(baseline_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"baseline written: {args.write_baseline}")
        return 0

    if args.baseline is not None:
        if not args.baseline.is_file():
            print(f"::error::baseline not found: {args.baseline}")
            return 1
        comparison = _compare_baseline(results, args.baseline)
        report["baseline_compare"] = comparison
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        regressions = comparison["regressions"]
        print(f"baseline: {comparison['compared']} compared, "
              f"{len(comparison['new_policies'])} new, {len(regressions)} regressed")
        for item in regressions:
            print(f"  REGRESSED {item['robot']}/{item['policy']}: {item['reason']}")
        return 1 if regressions else 0

    return 1 if report["failed"] else 0


def _baseline_rows(results: list[dict]) -> list[dict]:
    """基线只保留稳定判定所需的字段，避免机器相关指标（耗时/绝对阈值）污染对比。"""
    rows = []
    for item in results:
        rows.append({
            "robot": item.get("robot"),
            "policy": item.get("policy"),
            "verdict": item.get("verdict") or item.get("status"),
            "family": item.get("family"),
        })
    return rows


def _compare_baseline(results: list[dict], baseline_path: Path) -> dict:
    """将本次结果与历史基线逐 policy 对比，只把'新增失败/由 pass 变 fail'算作退化。

    设计意图：仓库里存在少量既存失败（go2 特技类量化判据未过），它们已记录在
    基线里；CI 应在这批失败之外守住"不许新增失败"，而不是一开始就全绿。
    """
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"cannot parse baseline {baseline_path}: {exc}",
                "compared": 0, "new_policies": [], "regressions": []}
    base_map = {}
    for row in baseline.get("results") or []:
        key = (row.get("robot"), row.get("policy"))
        verdict = row.get("verdict")
        base_map[key] = "fail" if verdict in ("fail", "error") else ("pass" if verdict == "pass" else verdict)

    regressions = []
    new_policies = []
    for item in results:
        key = (item.get("robot"), item.get("policy"))
        current = item.get("verdict") or item.get("status")
        current = "fail" if current in ("fail", "error") else ("pass" if current == "pass" else current)
        base = base_map.get(key)
        if base is None:
            # 新增 policy：只要不是明确 fail 就只报不卡（首次收录允许观察）
            new_policies.append({"robot": key[0], "policy": key[1], "verdict": current})
            if current == "fail":
                regressions.append({"robot": key[0], "policy": key[1],
                                    "reason": f"new policy failing (baseline has no entry): {current}"})
            continue
        if base == "pass" and current == "fail":
            regressions.append({"robot": key[0], "policy": key[1],
                                "reason": f"{base} -> {current}"})
    return {"baseline_file": str(baseline_path), "compared": len(base_map),
            "new_policies": new_policies, "regressions": regressions}


if __name__ == "__main__":
    raise SystemExit(main())
