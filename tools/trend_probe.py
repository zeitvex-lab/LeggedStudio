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


def _export_checkpoint(run_dir: Path, checkpoint: str, out: Path) -> Path:
    cmd = [
        str(_adapter_python()), str(ROOT / "tools" / "export_checkpoint_onnx.py"),
        "--run", str(run_dir), "--checkpoint", checkpoint,
        "--out", str(out), "--no-verify",
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
    ap.add_argument("--cases", default="0.5,0,0;0,0.4,0;0,0,0.6")
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

    # 合成条目的 contract 块：抄包内同 kind 的**已取证条目**（布局/关节序同源），不新造
    ref_entry = next((e for e in sim_cfg["policies"]
                      if (e.get("contract") or {}).get("observation_kind") == "go2w_mjlab_legs_53"), None)

    exported_dir = run_dir / "exported"
    exported_dir.mkdir(exist_ok=True)
    checkpoints: list[dict] = []
    for ck in _pick_checkpoints(run_dir, args.checkpoints):
        if ck == "model_final.pt":
            onnx = exported_dir / "policy.onnx"
            if not onnx.is_file():
                onnx = _export_checkpoint(run_dir, ck, exported_dir / "policy.onnx")
            iter_label = "final"
        else:
            iter_num = int(re.fullmatch(r"model_(\d+)\.pt", ck).group(1))
            onnx = exported_dir / f"model_{iter_num}.onnx"
            if not onnx.is_file():
                onnx = _export_checkpoint(run_dir, ck, onnx)
            iter_label = iter_num

        width = onnx_obs_dim(onnx)
        kind = observation_kind_for(args.robot, width) if width else None
        contract_block = dict((ref_entry or {}).get("contract") or {})
        if kind:
            contract_block["observation_kind"] = kind
        if width:
            contract_block["obs_dim"] = width
        entry = {"id": f"trend-probe-{Path(onnx).stem}", "path": str(onnx),
                 "contract": contract_block}
        blob = policy_blob_path(entry, robot_dir=pkg, index=load_index())
        if blob is None or not Path(blob).is_file():
            blob = onnx
        entry = {**entry, "path": str(blob)}

        contract = pa.PackageContract(pkg, entry)
        sess = ort.InferenceSession(str(blob), providers=["CPUExecutionProvider"])
        cases_out = []
        for case in args.cases.split(";"):
            cmd = clamp_to_ranges([float(x) for x in case.split(",")], contract)
            r = run_case(sess, contract, model, tuple(cmd))
            main_axis = int(np.argmax(np.abs(cmd))) if np.abs(cmd).max() > 0 else -1
            cases_out.append({"command": cmd, "main_axis": main_axis,
                              "v_mean": r.get("v_mean"), "pass": r.get("pass"),
                              "err%": r.get("err%")})
        checkpoints.append({"iter": iter_label, "onnx": str(onnx), "cases": cases_out})
        walked = [c for c in cases_out if c["main_axis"] >= 0 and c["v_mean"]
                  and abs(c["v_mean"][c["main_axis"]]) > 1e-3]
        print(f"  ckpt {iter_label}: 主轴速度 " + ", ".join(
            f"{c['v_mean'][c['main_axis']] if c['v_mean'] else 0:.3f}(cmd{c['command'][c['main_axis']]})"
            for c in cases_out if c["main_axis"] >= 0)
            + f" ｜ 有位移命令数 {len(walked)}/{len(cases_out)}")

    curve = parse_reward_curve(run_dir / "training.log")
    plateau = detect_plateau(curve)
    last_iter = curve[-1][0] if curve else 0
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
