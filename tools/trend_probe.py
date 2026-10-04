#!/usr/bin/env python3
"""trend_probe.py — 训练期趋势探针（用户判据的流水线化，2026-10-02）。

## 用户口径（2026-10-02 实战确立，本工具是其标准测量）

* 好框架/奖励/课程/命令下 **~200 轮出趋势**（观测格点 250，见 TREND_ITER_DEFAULT）：主轴速度达到命令的
  `--trend-ratio`（默认 20%）；
* reward **连续 50 轮相对变化 < 2% ≈ 已收敛**——收敛点错（如站立）= 配方判负；
* **判负的响应协议**：移植保真门（recipe_parity）→ 机制覆盖（参考内化）→
  **最后才是参数**；禁止加预算、禁止参数狩猎（判负≠调参信号，是架构缺口信号）。

## 为什么做成工具（架构，不是一次性脚本）

趋势判决此前是手搓的（手动导 checkpoint → 手动装条目 → 手动评测 → 结论写文档）——
不可复现、不可比较、依赖执行人。本工具把它收进流水线：

* 判据数值只有一处（本文件常量 + `--trend-iter/--trend-ratio`），与
  `tools/check_user_criteria.py` 共用同一个 `run_case`（同一把尺子）；
* 评测**不污染机器人包**：合成条目只存在内存里，checkpoint ONNX 导出到
  run 目录 `exported/`，结论落 `<run>/trend_probe.json`——证据随 Run 档案走；
* 同一 run 重跑探针 = 同一 JSON 形状（除时间戳），不同 run 之间可横向对比。

## 用法（adapter venv）

    adapters/mjlab/.venv/Scripts/python.exe tools/trend_probe.py \
        --run workspace/<run> --robot unitree_go2w
    # --checkpoints auto（默认：≥200 的最小 checkpoint + 终版）
    # --checkpoints 250,1000,2500 / --trend-iter 200 / --trend-ratio 0.2

退出码：0 = 探针完成（verdict 在 JSON 里，trend_ok / trend_late / no_trend）；
2 = 环境/输入缺失。探针**不判红训练**——它是测量，判决人来下。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 趋势判据常量（用户口径「~200 轮出趋势」的单一真值；--trend-iter/--trend-ratio 可覆盖）。
#: 250 = checkpoint 保存节奏的下限（save_interval = max(250, iters//10)）——判据在
#: **观测格点**上执行：250 轮内有趋势 = 「~200 左右」达标，再晚才是 trend_late。
TREND_ITER_DEFAULT = 250
TREND_RATIO_DEFAULT = 0.2
PLATEAU_WINDOW = 50          # 连续多少轮
PLATEAU_REL_CHANGE = 0.02    # 窗口内相对变化 < 2% ⇒ 平台（≈收敛）

_REWARD_LINE = re.compile(r"Learning iteration\s+(\d+)/\d+.*?Mean reward:\s*([-\d.eE+]+)", re.S)


def parse_reward_curve(log_path: Path) -> list[tuple[int, float]]:
    """training.log → [(iter, mean_reward)]（按出现序；缺文件 = 空表）。"""
    if not log_path.is_file():
        return []
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    pairs: list[tuple[int, float]] = []
    last_iter = 0
    for line in text.splitlines():
        m_iter = re.search(r"Learning iteration\s+(\d+)/", line)
        if m_iter:
            last_iter = int(m_iter.group(1))
            continue
        m_rew = re.search(r"Mean reward:\s*([-\d.eE+]+)", line)
        if m_rew and last_iter:
            pairs.append((last_iter, float(m_rew.group(1))))
    return pairs


def detect_plateau(curve: list[tuple[int, float]], *, window: int = PLATEAU_WINDOW,
                   rel: float = PLATEAU_REL_CHANGE) -> int | None:
    """第一个「连续 window 轮相对变化 < rel」的**起点 iter**；无平台 = None。

    相对变化以窗口首点为基准（|end-start| / max(|start|, 1e-9)）；曲线短于
    window+1 个点时不判（数据不足，不编造）。
    """
    if len(curve) < window + 1:
        return None
    for i in range(len(curve) - window):
        start_i, start_v = curve[i]
        end_v = curve[i + window][1]
        if abs(end_v - start_v) / max(abs(start_v), 1e-9) < rel:
            return start_i
    return None


def curriculum_cases(effective: dict, iteration, final_iter: int | None = None) -> list[str] | None:
    """从 run 的 effective-config 推**当期命令分布**的探针用例（课程感知）。

    命令课程是配方数据：stage-0 训练分布里 vx∈[-0.1,0.25] 时，拿 0.5 测趋势
    = 分布外测量（2026-10-02 实证：终版 vx 0.243 ≈ stage-0 上限 0.25 的 97%——
    策略在精确跟踪课程，此前判「趋势晚」是测错了地方）。规则：
      * checkpoint 迭代 × num_steps_per_env → 当期 stage（≤ 则取最后一个）；
      * 每条非零程轴取当期上限的 80%（in-distribution 的"走到没有"）；
      * 零程轴（如 vy≡0）跳过——命令域没有的维度判不出趋势；
      * 无课程/无 stages → None（调用方回落显式 --cases）。
    """
    try:
        env = effective.get("environment") or {}
        twist = ((env.get("commands") or {}).get("twist")) or {}
        stages = (((env.get("curriculum") or {}).get("command_vel") or {}).get("params") or {}).get("velocity_stages") or []
        steps = ((effective.get("algorithm_config") or {}).get("num_steps_per_env")
                 or effective.get("environment", {}).get("num_steps_per_env") or 24)
        if not stages:
            return None
        it = (final_iter if final_iter else 10 ** 9) if iteration == "final" else int(iteration)
        env_steps = it * int(steps)
        stage = stages[0]
        for s in stages:
            if int(s.get("step") or 0) <= env_steps:
                stage = s
        cases: list[str] = []
        for axis in ("lin_vel_x", "ang_vel_z"):
            span = stage.get(axis) or [0.0, 0.0]
            hi = float(span[1]) if len(span) > 1 else 0.0
            if abs(hi) > 1e-9:
                cases.append(f"{hi * 0.8:.3f},0,0" if axis == "lin_vel_x" else f"0,0,{hi * 0.8:.3f}")
        return cases or None
    except Exception:
        return None


def trend_verdict(checkpoints: list[dict], *, trend_iter: int, trend_ratio: float,
                  final_iter: int = 0) -> dict:
    """checkpoint 评测结果 → 趋势判决（纯函数，可测）。

    trend_at = 最早的「任一单命令主轴速度 ≥ 命令×trend_ratio」的 checkpoint iter；
    verdict：trend_ok（≤ trend_iter）/ trend_late（> trend_iter）/ no_trend（全程无）。
    """
    trend_at: int | None = None

    def _ck_order(c: dict):
        return (1, 0) if c["iter"] == "final" else (0, int(c["iter"]))

    for ck in sorted(checkpoints, key=_ck_order):
        for case in ck.get("cases", []):
            main = int(case.get("main_axis", -1))
            cmd = case.get("command") or []
            v_mean = case.get("v_mean") or []
            if main < 0 or main >= len(cmd) or main >= len(v_mean):
                continue
            mag = abs(cmd[main])
            if mag <= 0:
                continue
            if abs(v_mean[main]) / mag >= trend_ratio:
                trend_at = final_iter if ck["iter"] == "final" else int(ck["iter"])
                break
        if trend_at is not None:
            break
    if trend_at is None:
        verdict = "no_trend"
    elif trend_at <= trend_iter:
        verdict = "trend_ok"
    else:
        verdict = "trend_late"
    return {"trend_at_iter": trend_at, "trend_iter_budget": trend_iter,
            "trend_ratio": trend_ratio, "verdict": verdict}


def _adapter_python() -> Path:
    from contracts.path_bootstrap import adapter_python
    return adapter_python(default=ROOT / "adapters" / "mjlab" / ".venv")


def _export_checkpoint(run_dir: Path, checkpoint: str, out: Path, robot_id: str) -> Path:
    cmd = [
        str(_adapter_python()), str(ROOT / "tools" / "export_checkpoint_onnx.py"),
        "--run", str(run_dir), "--checkpoint", checkpoint,
        "--out", str(out), "--no-verify",
        # 包根随 run 的机器人走（缺省是 unitree_go2w——跨机型 run 会因此在
        # 别的包里找 profile，找不到回落 legs-only ⇒ 装出 12 动作模型去载
        # 16 动作 checkpoint 必炸 shape mismatch）。profile_id 从 training_config
        # 读，包根由调用方按 --robot 传入。
        "--package-root", str(ROOT / "assets" / "robots" / robot_id),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError(f"checkpoint 导出失败（{checkpoint}）：{proc.stdout[-300:]} {proc.stderr[-300:]}")
    return out


def _available_checkpoints(run_dir: Path) -> list[int]:
    iters = sorted(
        int(m.group(1))
        for p in run_dir.glob("model_*.pt")
        if (m := re.fullmatch(r"model_(\d+)\.pt", p.name))
    )
    return iters


def _pick_checkpoints(run_dir: Path, spec: str) -> list[str]:
    """auto = ≥200 的最小 checkpoint + 终版；也接受 `250,1000` 显式清单。"""
    if spec != "auto":
        return [f"model_{int(x)}.pt" for x in spec.split(",") if str(x).strip()]
    iters = [i for i in _available_checkpoints(run_dir) if i >= TREND_ITER_DEFAULT]
    picks: list[str] = []
    if iters:
        picks.append(f"model_{min(iters)}.pt")
    if (run_dir / "exported" / "policy.onnx").is_file():
        picks.append("model_final.pt")
    elif iters:
        picks.append(f"model_{max(iters)}.pt")
    return picks


def main() -> int:
    ap = argparse.ArgumentParser(description="训练期趋势探针（~200 轮趋势 / 50 轮平台判敛）")
    ap.add_argument("--run", required=True)
    ap.add_argument("--robot", required=True)
    ap.add_argument("--checkpoints", default="auto")
    ap.add_argument("--trend-iter", type=int, default=TREND_ITER_DEFAULT)
    ap.add_argument("--trend-ratio", type=float, default=TREND_RATIO_DEFAULT)
    ap.add_argument("--cases", default="auto", help="auto = 按 run 命令课程的当期 stage 构造分布内用例（推荐）；否则分号分隔 vx,vy,wz")
    args = ap.parse_args()

    run_dir = Path(args.run)
    if not run_dir.is_dir():
        print(f"[env-missing] run 目录不存在：{run_dir}", file=sys.stderr)
        return 2
    pkg = ROOT / "assets" / "robots" / args.robot
    if not pkg.is_dir():
        print(f"[env-missing] 机型包不存在：{pkg}", file=sys.stderr)
        return 2

    # 同一把尺子：run_case / clamp / PackageContract 全部来自判据工具与验收器
    import numpy as np
    import onnxruntime as ort
    import mujoco
    from adapters.mjlab import policy_acceptance as pa
    from backend.policy_artifacts import (
        load_index,
        observation_kind_for,
        onnx_obs_dim,
        policy_blob_path,
    )
    from tools.check_user_criteria import clamp_to_ranges, run_case

    sim_cfg = json.loads((pkg / "simulation/config.json").read_text(encoding="utf-8-sig"))
    model = pa.load_package_model(pkg, sim_cfg)
    model.opt.timestep = 1.0 / 50  # 由契约在 PackageContract 内覆写（与判据工具同口径）

    # 合成条目的 contract 块：抄包内**同布局的已取证条目**（布局/关节序同源），不新造。
    # 参照按「先 kind 后宽度」选——混合 57 与纯腿 53 的 action_joint_order 宽度不同，
    # 抄错参照 = 动作序错位（2026-10-02 混合档实测：12 名序参照 → 16 checkpoint 越界）。
    ref_entry = None

    exported_dir = run_dir / "exported"
    exported_dir.mkdir(exist_ok=True)
    effective = json.loads((run_dir / "effective-config.json").read_text(encoding="utf-8-sig"))         if (run_dir / "effective-config.json").is_file() else {}
    curve = parse_reward_curve(run_dir / "training.log")
    last_iter = curve[-1][0] if curve else 0
    checkpoints: list[dict] = []
    for ck in _pick_checkpoints(run_dir, args.checkpoints):
        cases_for_this_ckpt = args.cases.split(";")
        if args.cases.strip().lower() == "auto":
            auto = curriculum_cases(
                effective,
                ck.replace("model_", "").replace(".pt", "") if ck != "model_final.pt" else "final",
                final_iter=last_iter or None)
            if auto:
                cases_for_this_ckpt = auto
        if ck == "model_final.pt":
            onnx = exported_dir / "policy.onnx"
            if not onnx.is_file():
                onnx = _export_checkpoint(run_dir, ck, exported_dir / "policy.onnx", args.robot)
            iter_label = "final"
        else:
            iter_num = int(re.fullmatch(r"model_(\d+)\.pt", ck).group(1))
            onnx = exported_dir / f"model_{iter_num}.onnx"
            if not onnx.is_file():
                onnx = _export_checkpoint(run_dir, ck, onnx, args.robot)
            iter_label = iter_num

        width = onnx_obs_dim(onnx)
        kind = observation_kind_for(args.robot, width) if width else None
        if ref_entry is None or (ref_entry.get("contract") or {}).get("observation_kind") != kind:
            candidates = sim_cfg["policies"]
            ref_entry = next((e for e in candidates
                              if (e.get("contract") or {}).get("observation_kind") == kind), None)
            if ref_entry is None and width:
                ref_entry = next((e for e in candidates
                                  if (e.get("contract") or {}).get("obs_dim") == width), None)
        contract_block = dict((ref_entry or {}).get("contract") or {})
        if kind:
            contract_block["observation_kind"] = kind
        if width:
            contract_block["obs_dim"] = width
        # run 真值补齐（否则 clamp/出生姿回落包级 ≠ 训练口径——2026-10-02 实测
        # 缺 command_ranges 时 clamp 失效，0.64 分布外输入喂出 0.047 假读数）：
        twist = ((effective.get("environment") or {}).get("commands") or {}).get("twist") or {}
        ranges = twist.get("ranges") or {}
        if ranges:
            contract_block["command_ranges"] = {
                k: [float(v[0]), float(v[1])] for k, v in ranges.items()
                if isinstance(v, (list, tuple)) and len(v) == 2}
        # run 契约快照若声明了 observation_layout（声明式布局），随 contract_block
        # 携带——验收侧 frame_from_spec 按此构建（无参照策略的布局从这条走）。
        run_contract = {}
        _rc_path = run_dir / "contract.json"
        if _rc_path.is_file():
            try:
                run_contract = json.loads(_rc_path.read_text(encoding="utf-8-sig"))
            except Exception:  # noqa: BLE001
                run_contract = {}
        if run_contract.get("observation_layout"):
            contract_block["observation_layout"] = run_contract["observation_layout"]
        snapshot = json.loads((run_dir / "contract_snapshot.json").read_text(encoding="utf-8-sig"))             if (run_dir / "contract_snapshot.json").is_file() else {}
        pose = ((snapshot.get("action") or {}).get("default_pose") or [])
        order = (snapshot.get("action") or {}).get("joint_order") or []
        if pose and order and len(pose) == len(order):
            contract_block["default_joint_angles"] = dict(zip(order, [float(x) for x in pose]))
        entry = {"id": f"trend-probe-{Path(onnx).stem}", "path": str(onnx),
                 "contract": contract_block}
        blob = policy_blob_path(entry, robot_dir=pkg, index=load_index())
        if blob is None or not Path(blob).is_file():
            blob = onnx
        entry = {**entry, "path": str(blob)}

        contract = pa.PackageContract(pkg, entry)
        sess = ort.InferenceSession(str(blob), providers=["CPUExecutionProvider"])
        cases_out = []
        for case in cases_for_this_ckpt:
            cmd = clamp_to_ranges([float(x) for x in case.split(",")], contract)
            if float(np.abs(cmd).max()) <= 1e-9:
                continue  # 全零命令判不出趋势（零程轴被契约钳平）
            r = run_case(sess, contract, model, tuple(cmd))
            main_axis = int(np.argmax(np.abs(cmd))) if np.abs(cmd).max() > 0 else -1
            cases_out.append({"command": cmd, "main_axis": main_axis,
                              "v_mean": r.get("v_mean"), "pass": r.get("pass"),
                              "reason": r.get("reason"), "err%": r.get("err%")})
        checkpoints.append({"iter": iter_label, "onnx": str(onnx), "cases": cases_out})
        def _v(c):
            return c["v_mean"][c["main_axis"]] if c["v_mean"] else None

        walked = [c for c in cases_out if c["main_axis"] >= 0 and c["v_mean"]
                  and abs(c["v_mean"][c["main_axis"]]) > 1e-3]
        print(f"  ckpt {iter_label}: 主轴速度 " + ", ".join(
            (f"{_v(c):.3f}" if _v(c) is not None else "None(倒地/不足5s)")
            + f"(cmd{c['command'][c['main_axis']]})"
            for c in cases_out if c["main_axis"] >= 0)
            + f" ｜ 有位移命令数 {len(walked)}/{len(cases_out)}")

    plateau = detect_plateau(curve)
    verdict = trend_verdict(checkpoints, trend_iter=args.trend_iter, trend_ratio=args.trend_ratio,
                            final_iter=last_iter)
    report = {
        "schema": "trend-probe-1.0",
        "run": str(run_dir),
        "robot": args.robot,
        "criteria": {"trend_iter": args.trend_iter, "trend_ratio": args.trend_ratio,
                     "plateau_window": PLATEAU_WINDOW, "plateau_rel_change": PLATEAU_REL_CHANGE},
        "reward_plateau_iter": plateau,
        "checkpoints": checkpoints,
        **verdict,
    }
    out = run_dir / "trend_probe.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[trend] verdict={verdict['verdict']} trend_at={verdict['trend_at_iter']} "
          f"plateau_at={plateau} → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
