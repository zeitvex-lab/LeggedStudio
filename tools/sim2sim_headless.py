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
  --write-baseline <path>     把本次全量结果写成基线（本地定期刷新用），并携带
                              provenance（生成时间/平台/Python/依赖版本/git/运行参数）——
                              基线在哪台环境刷的必须可查，否则环境差异会被误读成代码退化。

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

# 默认阈值：可按任务族用 --criteria-json 覆盖（策略自己也能声明——见 evaluate_policy
# 里 `contract.criteria` 的合并：**判据属于任务语义，应当由任务声明，而不是工具写死**）。
#
# `checks` = **量哪几项**（声明式检查表，2026-09-22 起）。此前是 `evaluate_mode` 里按家族写
# `if family in (...)`，于是"姿态类技能"（反关节/倒立：躯干立起来才是成功）与"站立类"共用
# 同一套检查，量出"倾角 88° 判不合格"这种**假阴性**——实测 `go2-lainlab-rear-stand` 稳定保持
# 躯干 −88°、baseZ 0.40 达 8 s（真的用后腿立住了），却被站立族判据判 fail。新增 `posture` 族
# 量"姿态角带"；将来任何新族只需在这里（或策略契约里）声明 checks，**不必改工具代码**。
DEFAULT_CRITERIA = {
    # 硬门 = 存活/未摔 + 稳态姿态；vel_err 单列为质量指标（默认不卡门，见 --gate-tracking）。
    "stand": {"survival_min": 0.999, "height_ratio_min": 0.85, "tilt_max_deg": 20.0, "vel_err_max": 0.20,
              "checks": ["survival", "not_fallen", "height_ratio", "tilt_max", "vel_track"]},
    "balance": {"survival_min": 0.999, "height_ratio_min": 0.85, "tilt_max_deg": 20.0, "vel_err_max": 0.20,
                "checks": ["survival", "not_fallen", "height_ratio", "tilt_max", "vel_track"]},
    # 站立硬门与 stand 族同档 —— 用户口径（2026-09-14）：站立是底线，
    # 而 0.70/30° 只保证"没摔倒"（允许趴在 70% 高度、歪 30°），那不等于"站得正常"。
    # 跟踪两档：track_pass_ratio=0.6 合格 / track_good_ratio=0.8 更好（按命令幅值折算，见 tracking_ratio）。
    "velocity": {"survival_min": 0.999, "height_ratio_min": 0.85, "tilt_max_deg": 20.0,
                 "vel_err_max": 0.20, "track_pass_ratio": 0.6, "track_good_ratio": 0.8,
                 "checks": ["survival", "not_fallen", "height_ratio", "tilt_max", "vel_track"]},
    "imitation": {"survival_min": 0.95, "checks": ["survival", "not_fallen"]},
    # LainLab playground 行走族（trot / jump / spring-jump，包内契约 `task_type="gait"`）：
    # 相位驱动的行走技能，判据与 velocity 同档（存活/高度/倾角 + 跟踪两档）。
    # **2026-09-22 补**：此前 **没有这一族** —— 三条策略在无头验收里直接 `KeyError: 'gait'`，
    # 这就是"四族行为级 B11 评测未做"里 gait 那几条的真身（不是观测布局的问题）。
    "gait": {"survival_min": 0.999, "height_ratio_min": 0.85, "tilt_max_deg": 20.0,
             "vel_err_max": 0.20, "track_pass_ratio": 0.6, "track_good_ratio": 0.8,
             "checks": ["survival", "not_fallen", "height_ratio", "tilt_max", "vel_track"]},
    # **姿态类技能**（后腿站立 / 倒立 / 反关节立姿）：成功 = 立住那个姿态，**不是**"站得平"
    # ——所以量稳态倾角**落在声明带内**（|roll| / |pitch| 的幅值），并保留存活/未摔。
    # 下界取 60°：躯干立不起来（实测 handstand 只到 33.5° 就定住）= 没做到，如实判失败；
    # 上界 110° 容许轻微过冲。带值可由策略契约 `criteria.tilt_band_deg` 覆盖（任务语义声明）。
    "posture": {"survival_min": 0.999, "tilt_band_deg": [60.0, 110.0],
                "checks": ["survival", "not_fallen", "tilt_band"]},
    "acrobatics": {"survival_min": 0.9, "checks": ["survival", "not_fallen"]},
    "parkour": {"survival_min": 0.95, "checks": ["survival", "not_fallen"]},
    # 操作类（抓取/搬运等）：站姿高度/倾角不是判据（任务本身就要求下蹲/伸出），只看存活。
    "manipulation": {"survival_min": 0.999, "checks": ["survival", "not_fallen"]},
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


def tracking_ratio(metrics: dict) -> float | None:
    """速度跟踪**达成率** = 1 − vel_track_err / ‖命令速度‖（夹到 [0, 1]）。

    为什么不能直接拿 ``vel_track_err`` 当判据：它是 ``‖v_meas−v_cmd‖ + 0.3·|ω−ω_cmd|``
    的**绝对误差**（见 `adapters/mjlab/policy_acceptance.py` 的 vel_errs 累加处）。
    同样 0.4 的误差，在 0.6 m/s 命令下意味着"几乎没动"，在 1.0 m/s 下只差四成 ——
    同一个数在不同命令下含义不同，无法跨命令比较。折算成达成率后才有统一口径：
    用户定的 **≥0.6 合格、≥0.8 更好**。
    """
    err = metrics.get("vel_track_err")
    command = metrics.get("command_effective") or metrics.get("command") or []
    if err is None or len(command) < 2:
        return None
    magnitude = (float(command[0]) ** 2 + float(command[1]) ** 2) ** 0.5
    if magnitude <= 1e-6:
        return None                      # 零命令（纯站立）没有"跟踪"可言
    return max(0.0, min(1.0, 1.0 - float(err) / magnitude))


def _legacy_checks(family: str) -> list[str]:
    """未声明 `checks` 的家族按**旧行为**回落（逐项等价，避免改动既有结论）。"""
    if family in ("stand", "balance", "velocity", "gait"):
        return ["survival", "not_fallen", "height_ratio", "tilt_max", "vel_track"]
    return ["survival", "not_fallen"]


def _steady_tilt(metrics: dict) -> float:
    """稳态倾角**幅值**（|roll| 与 |pitch| 取大者；无稳态窗口时回落全程最大值）。"""
    roll_s = metrics.get("roll_steady_max_deg")
    pitch_s = metrics.get("pitch_steady_max_deg")
    return max(roll_s if roll_s is not None else (metrics.get("roll_max_deg") or 0.0),
               pitch_s if pitch_s is not None else (metrics.get("pitch_max_deg") or 0.0))


def evaluate_mode(metrics: dict, family: str, contract, criteria: dict,
                  gate_tracking: bool = False, ref_height: float | None = None) -> dict:
    """硬门 = 存活/未摔 + 稳态姿态；跟踪精度为质量指标，按 gate_tracking 决定是否卡门。

    **量哪几项由 `criteria["checks"]` 声明**（2026-09-22 起）——"判据属于任务语义"的落点：
    此前按家族在代码里写 `if family in (...)`，于是姿态类技能（反关节/倒立）被站立族判据量成
    "倾角 88° 不合格"的**假阴性**（`go2-lainlab-rear-stand` 实测真立住了）；反过来新增一类任务
    又必须改工具代码。现在新族只需在 `DEFAULT_CRITERIA` 或策略契约 `criteria` 里声明 checks。

    高度基准优先用「默认姿静立参考高度」ref_height（多策略共享包级初高时更稳健）。
    """
    checks = list(criteria.get("checks") or _legacy_checks(family))
    hard: list[dict] = []
    quality: list[dict] = []

    for check in checks:
        if check == "survival":
            survival = float(metrics.get("survival_ratio") or 0.0)
            hard.append({"name": "survival", "ok": survival >= criteria["survival_min"],
                         "value": survival, "min": criteria["survival_min"]})
        elif check == "not_fallen":
            if metrics.get("fell"):
                hard.append({"name": "not_fallen", "ok": False, "value": metrics.get("fell_at_s")})
        elif check == "height_ratio":
            # **尺子优先级**：显式声明的参考高度 > 引擎现算的默认姿运动学高度 > 契约初高。
            # 结论里必须带 `ruler` —— "高度比 0.692" 若不说明"跟什么比"就没有意义：lite3 的
            # 0.692 是"跟默认姿运动学高度比"，而那不是策略的自然站姿（2026-09-14 实测，
            # 曾因此误判为"增益错"并一度去改物理常量，被测试挡下）。
            declared_ref = criteria.get("height_ref_m")
            if declared_ref and float(declared_ref) > 1e-6:
                base = float(declared_ref)
                ruler = str(criteria.get("height_ruler") or "declared")
            elif ref_height and ref_height > 1e-6:
                base = float(ref_height)
                ruler = "static_default_pose"
            else:
                base = float(contract.initial_height)
                ruler = "contract_initial_height"
            h_steady = metrics.get("height_steady")
            h_ratio = (float(h_steady) / max(base, 1e-6)) if h_steady is not None else metrics.get("height_steady_ratio")
            if h_ratio is None:
                h_ratio = (metrics.get("height_min") or 0.0) / max(base, 1e-6)
            hard.append({"name": "height_ratio_steady", "ok": h_ratio >= criteria["height_ratio_min"],
                         "value": round(float(h_ratio), 3), "min": criteria["height_ratio_min"],
                         "ruler": ruler, "ref_height": round(float(base), 3)})
        elif check == "tilt_max":
            tilt = _steady_tilt(metrics)
            hard.append({"name": "tilt_steady", "ok": tilt <= criteria["tilt_max_deg"],
                         "value": tilt, "max": criteria["tilt_max_deg"]})
        elif check == "tilt_band":
            band = criteria.get("tilt_band_deg") or [60.0, 110.0]
            lo, hi = float(band[0]), float(band[1])
            tilt = _steady_tilt(metrics)
            hard.append({"name": "tilt_band", "ok": lo <= tilt <= hi,
                         "value": tilt, "band": [lo, hi]})
        elif check == "vel_track":
            vel_err = metrics.get("vel_track_err")
            if vel_err is None:
                continue
            quality.append({"name": "vel_track_err", "ok": float(vel_err) <= criteria["vel_err_max"],
                            "value": vel_err, "max": criteria["vel_err_max"]})
            ratio = tracking_ratio(metrics)
            if ratio is not None:
                quality.append({
                    "name": "track_ratio",
                    "ok": ratio >= float(criteria.get("track_pass_ratio", 0.6)),
                    "value": round(ratio, 3),
                    "min": float(criteria.get("track_pass_ratio", 0.6)),
                    # `good` 不进 hard/quality 的 ok 判定，只作"更好"的标注（用户口径 0.8）
                    "good": ratio >= float(criteria.get("track_good_ratio", 0.8)),
                })
    hard_ok = all(c["ok"] for c in hard)
    tracking_ok = all(c["ok"] for c in quality) if quality else True
    return {
        "ok": hard_ok and (tracking_ok or not gate_tracking),
        "hard_ok": hard_ok,
        "tracking_ok": tracking_ok,
        "checks": hard + quality,
    }


def evaluate_policy(engine, package_dir: Path, policy_rel: str, family: str | None,
                    criteria_all: dict, seconds: float, seed: int, named_policy: str = "",
                    gate_tracking: bool = False) -> dict:
    import mujoco
    import onnxruntime as ort

    sim_cfg = json.loads((package_dir / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    policies = sim_cfg.get("policies") or []
    policy_path = package_dir / policy_rel
    # fail-closed（2026-10-01，R1 实证 bug）：终态条目（无 path、artifact 不在索引）会把
    # policy_rel 解析成空串 → policy_path 是包目录（is_file()=False）→ match 回落错条目，
    # 评的是别人的模型还报 pass（sha256 实证）。目录/不存在一律报错，不猜。
    if not policy_path.is_file():
        raise RuntimeError(
            f"策略路径不是文件: {policy_rel!r}（声明解析为空=终态条目缺索引 blob，或路径写错）"
        )
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    # 条目匹配与 policy_acceptance.py 共用同一实现（先按 id，再按解析出的 blob 文件名全等）。
    # 匹配不上就报错而不是空条目继续跑 —— 空条目意味着逐策略增益缺位（零力矩同族缺陷），
    # 对门禁而言"错着跑完还绿了"是最坏结果。外层循环的 except 会把它记为该策略的 error。
    entry = engine.match_policy_entry(policies, policy_path, package_dir)
    if entry is None:
        raise RuntimeError(f"策略文件对不上包内声明: {policy_rel}（包: {package_dir.name}）")
    # 点名一致性（2026-10-01，R1/R2 实证 bug）：--policy 传的是条目 id 时，解析到的
    # blob 若属于另一条声明（临时条目顶层 policy_id/provenance 残留他人），等于评了
    # 别人的模型还报 pass。id 形态下强一致；文件名形态维持全等匹配语义。
    if named_policy and entry.get("id") != named_policy             and Path(policy_rel).stem != named_policy and Path(policy_rel).name != named_policy:
        raise RuntimeError(
            f"点名 {named_policy!r} 但解析到条目 {entry.get('id')!r} 的 blob——"
            f"声明身份键（policy_id/provenance.artifact_id）疑似残留他人，拒绝错评"
        )
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

    # Go2 mjswan 四输入 RNN（robust/vanilla/facet）：actor(117) / is_init / adapt_hx(128) /
    # command_(16) 按**槽表位置**喂，隐藏状态逐步回灌 —— 通用单输入路径不适用，走专用回路。
    # 判据与 PIE 同口径（存活 + 姿态 + 前进），便于同一份报告里横比。
    if contract.observation_kind == "go2_mjswan_velocity":
        slots = tuple(
            (contract.contract.get("onnx_slots") or {}).get("inputs")
            or ("actor", "is_init", "adapt_hx", "command_")
        )
        model = engine.load_package_model(package_dir, sim_cfg, None,
                                          scene_rel=contract.contract.get("scene_path"))
        model.opt.timestep = 1.0 / float(contract.physics_hz)
        data = mujoco.MjData(model)
        sess = ort.InferenceSession(str(policy_path), providers=["CPUExecutionProvider"])
        criteria = {"survival_min": 0.9, "tilt_max_deg": 75.0, "forward_min_m": 0.3}
        criteria.update(criteria_all.get("velocity") or {})
        modes = [[0.6, 0.0, 0.0], [1.0, 0.0, 0.0]]
        mode_reports = []
        for idx, cmd in enumerate(modes):
            metrics = engine.run_mjswan_policy(
                sess, contract, model, data, engine.ObsBuilder(contract, model, data),
                cmd, max(float(seconds), 10.0), seed + idx, slots=slots,
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
            "task_family": "velocity",
            "observation_kind": contract.observation_kind,
            "criteria": criteria,
            "slots": list(slots),
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

    # 判据优先级：**策略自己声明的**（`contract.criteria`，任务语义）> 运行参数 `--criteria-json`
    # > 家族默认。策略级声明是"新族不必改工具"的正门（如姿态类技能声明自己的 `tilt_band_deg`）。
    criteria = {**DEFAULT_CRITERIA[family], **(criteria_all.get(family) or {}),
                **((contract.contract.get("criteria") or {}))}
    # 复合命令（command_dims != 3）一律单指令评估，即使 task_type 标为 velocity。
    single_mode = (contract.command_dims != 3) or family in ("stand", "balance", "imitation", "acrobatics", "parkour", "posture")
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
        criteria_all = json.loads(args.criteria_json.read_text(encoding="utf-8-sig"))

    packages = sorted((ROOT / "assets" / "robots").iterdir())
    results = []
    for pkg in packages:
        if not pkg.is_dir() or not (pkg / "simulation" / "config.json").is_file():
            continue
        if args.robot and pkg.name != args.robot:
            continue
        sim_cfg = json.loads((pkg / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
        entries = list(sim_cfg.get("policies") or [])
        # B10 之后声明只留 `id`（源路径与 hash 都在 policies/index.json），故必须走解析器。
        # 早期版本在此读 entry["path"]：迁移删掉裸路径后，**每条策略都会被跳过**（total 恒为 0）。
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from backend.policy_artifacts import policy_relative_path

        for entry in entries:
            rel = policy_relative_path(entry, robot_dir=pkg) or ""
            if not rel:
                continue
            if args.policy and args.policy not in (entry.get("id"), Path(rel).name):
                continue
            try:
                report = evaluate_policy(engine, pkg, rel, args.task_type, criteria_all,
                                         args.seconds, args.seed, named_policy=str(args.policy or ""),
                                         gate_tracking=args.gate_tracking)
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
        baseline_doc = {
            "schema": "sim2sim-headless-baseline-1.0",
            "provenance": _sim2sim_provenance(args),
            "results": _baseline_rows(results),
        }
        args.write_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.write_baseline.write_text(json.dumps(baseline_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"baseline written: {args.write_baseline}")
        return 0

    if args.baseline is not None:
        if not args.baseline.is_file():
            print(f"::error::baseline not found: {args.baseline}")
            return 1
        comparison = _compare_baseline(results, args.baseline)
        diff = _provenance_diff(args.baseline, _sim2sim_provenance(args))
        if diff:
            comparison["provenance_diff"] = diff
            print("  WARNING 基线与本机环境签名不一致 —— 先怀疑环境再怀疑代码"
                  "（差异见 baseline_compare.provenance_diff；旧基线请用 --write-baseline 重刷）")
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


def _sim2sim_provenance(args) -> dict:
    """基线 provenance：这份基线是在**什么环境、哪份代码、什么参数**下刷出来的。

    起因（待决 D，2026-09-14）：现行基线由云原生开发环境（Ubuntu 容器）生成，
    本机 Windows 复跑出现 5 条"退化"，事后查明与代码无关 —— 基线不带环境信息时，
    这类差异会被误读成代码退化。git 状态复用 B9 的 ``_git_state``（同一逻辑不写两份）。
    """
    import platform
    from importlib import metadata

    from backend.training.runs import _git_state

    def _ver(name: str) -> str | None:
        try:
            return metadata.version(name)
        except Exception:  # noqa: BLE001 —— 缺包不是错误，如实记 None
            return None

    version_file = ROOT / "VERSION"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "product_version": version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else None,
        "git": _git_state(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        # sim2sim 实际用到的三个包（版本变了，物理步进/推理数值就可能变）
        "packages": {name: _ver(name) for name in ("mujoco", "onnxruntime", "numpy")},
        "run_params": {"seconds": args.seconds, "seed": args.seed, "gate_tracking": bool(args.gate_tracking)},
    }


def _provenance_diff(baseline_path: Path, current: dict) -> dict | None:
    """基线与本次运行的环境签名差异（**只报不拦**，门禁语义不变）。

    无 provenance 的旧基线如实标注（而不是装作可比）；有差异时逐项列出
    baseline/current 两边的值，让"先怀疑环境还是先怀疑代码"有据可依。
    """
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 —— 基线读不了由 _compare_baseline 报，这里不重复
        return None
    recorded = baseline.get("provenance") or {}
    if not recorded:
        return {"note": "baseline has no provenance (written before 2026-09-14); refresh with --write-baseline"}
    diffs: dict = {}
    for key in ("platform", "python", "product_version"):
        if recorded.get(key) not in (None, current.get(key)):
            diffs[key] = {"baseline": recorded.get(key), "current": current.get(key)}
    for key in ("packages", "run_params"):
        base, cur = recorded.get(key) or {}, current.get(key) or {}
        differing = {
            name: {"baseline": base.get(name), "current": cur.get(name)}
            for name in sorted(set(base) | set(cur))
            if base.get(name) != cur.get(name)
        }
        if differing:
            diffs[key] = differing
    return diffs or None


def _compare_baseline(results: list[dict], baseline_path: Path) -> dict:
    """将本次结果与历史基线逐 policy 对比，只把'新增失败/由 pass 变 fail'算作退化。

    设计意图：仓库里存在少量既存失败（go2 特技类量化判据未过），它们已记录在
    基线里；CI 应在这批失败之外守住"不许新增失败"，而不是一开始就全绿。
    """
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
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
