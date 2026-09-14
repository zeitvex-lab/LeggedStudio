#!/usr/bin/env python
"""部署策略可用性扫描：站立硬门 + 速度跟踪两档，并为**未通过者产出探究包**。

## 两条不可动摇的口径（用户 2026-09-14）

1. **站立是底线**：`stand` / `balance` / `velocity` 三族走站立硬门
   （存活、未摔、稳态高度比 ≥0.85、稳 tilt ≤20°）。
2. **速度跟踪 ≥0.6 合格、≥0.8 更好**（折算成 :func:`tracking_ratio`，见下方说明）。

## 这份扫描器**不产出"失败原因"**

未通过 ≠ 策略不可行。未通过只说明"它在我们这套仿真里没站住"，而原因通常在**我们这边**——
观测项次序、命令缩放、初始姿态、增益、关节序、encoder 链……要解决它，必须回到
**训练与部署源码**去对照。所以本工具对每条未通过者产出**探究包**（``diagnose``）：

* ``training_ref`` —— 声明里记的 ``profile`` 与 ``upstream``（训练工程出处）；
* ``training_source`` —— 包内训练源码目录是否存在；
* ``contract`` —— 这条策略实际被喂的观测/动作约定（obs_kind / obs_dim / history_len /
  action_joint_order / action_scale / scales / 命令缩放）；
* ``observed`` —— 实测指标（存活、稳态高度比、tilt、何时倒、跟踪达成率）。

拿这些去和上游的 obs 构建器 / deploy.yaml 逐项比对，才是"解决"的入口。

用法::

    python tools/sweep_policy_availability.py               # 全量
    python tools/sweep_policy_availability.py --limit 4     # 先试跑几条
    python tools/sweep_policy_availability.py --robots unitree_go2w,microduck
    python tools/sweep_policy_availability.py --json

**必须用 adapter venv 的 python 执行**（需要 mujoco + onnxruntime）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import policy_artifacts as pa  # noqa: E402
from tools import audit_policy_families as fam  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

#: 走站立硬门的三族（用户口径：站立是底线）。
STANDING_FAMILIES = ("stand", "balance", "velocity")

#: 本轮不纳入站立门 —— **不是"不可行"**，而是各自另有判据（特技/模仿/跑酷/操作），
#: 用户明确"特技任务再说"。它们仍会跑起来并记录指标，只是不进这条门。
DEFERRED_FAMILIES = ("imitation", "acrobatics", "parkour", "manipulation", "reorient")

#: 非标准站姿技能：族名归 balance，但**稳态高度天然偏离 `static_stand_height`**，
#: 故不套 `height_ratio` 硬门，改用"自身稳态稳定性"（后段高度稳定 + tilt 小 + 不摔）。
SELF_STABILITY_ONLY = {
    "go2w-himloco-stand-front": "前腿站立：稳态高度天然不等于四足标准站立高度",
    "go2w-himloco-leggedstand": "后腿站立：同上",
}

OUTPUT_DIR = ROOT / "workspace" / "validation" / "availability"


def _policy_inventory(robots: list[str] | None) -> list[dict]:
    rows: list[dict] = []
    for declaration in pa.scan_declarations():
        if robots and declaration["robot"] not in robots:
            continue
        contract = declaration.get("contract") or {}
        recommendation = fam.recommend_family(declaration)
        declared = contract.get("task_type") or declaration.get("task_type")
        artifact_id = pa.artifact_id_for(declaration["robot"], declaration["policy_id"])
        blob = declaration.get("onnx") or pa.policy_blob_path(declaration)
        rows.append({
            "robot": declaration["robot"],
            "policy_id": declaration["policy_id"],
            "label": declaration.get("label"),
            "family": str(declared or recommendation["family"]),
            "family_source": "declared" if declared else f"inferred({recommendation['confidence']})",
            "gated": str(declared or recommendation["family"]) in STANDING_FAMILIES,
            "self_stability_only": SELF_STABILITY_ONLY.get(artifact_id),
            "artifact_id": artifact_id,
            "blob": str(blob.relative_to(ROOT)) if blob and str(blob).startswith(str(ROOT)) else (str(blob) if blob else None),
            "observation_kind": contract.get("observation_kind"),
            "obs_dim": declaration.get("obs_dim"),
            "action_dim": declaration.get("action_dim"),
            "history_len": declaration.get("history_len"),
            "action_scale": contract.get("action_scale"),
            "action_joint_order": contract.get("action_joint_order"),
            "scales": contract.get("scales"),
            "command_dims": contract.get("command_dims"),
            "training_ref": contract.get("training_ref") or declaration.get("training_ref"),
        })
    return rows


def _run_one(row: dict, *, seconds: float, seed: int, timeout: float = 900.0) -> dict:
    """跑一条策略；返回实测指标。**未通过不写原因、不写"不可行"** —— 只留探究材料。

    用 subprocess 调 `tools/sim2sim_headless.py` 的 CLI（它的 `main()` 自己读 `sys.argv`，
    不适合作函数调用；走 CLI 也更贴合它已公开的接口契约）。子进程用的就是当前解释器 ——
    本脚本必须以 **adapter venv 的 python** 运行，mujoco/onnxruntime 才在。
    """
    output_dir = OUTPUT_DIR / row["artifact_id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, str(ROOT / "tools" / "sim2sim_headless.py"),
        "--robot", row["robot"], "--policy", row["policy_id"],
        "--task-type", row["family"], "--seconds", str(seconds), "--seed", str(seed),
        "--output-dir", str(output_dir), "--write-acceptance",
    ]
    exit_code = 0
    tail: list[str] = []
    try:
        completed = subprocess.run(          # noqa: S603
            command, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
        )
        exit_code = completed.returncode
        tail = (completed.stdout or "").strip().splitlines()[-8:]
        if completed.stderr:
            tail += [f"stderr: {line}" for line in completed.stderr.strip().splitlines()[-3:]]
    except subprocess.TimeoutExpired:
        exit_code = -2
        tail = [f"超时（>{timeout:.0f}s）"]
    except OSError as exc:                   # noqa: BLE001  跑不起来同样只是线索
        exit_code = -1
        tail = [f"[OSError] {exc}"]

    report = _newest_report(output_dir)
    return {
        **row,
        "exit_code": exit_code,
        "metrics": (report or {}).get("metrics") or (report or {}).get("modes"),
        "verdict": (report or {}).get("verdict"),
        "report_path": str(report) if report else None,
        "stdout_tail": tail,
    }


def _newest_report(output_dir: Path) -> dict | None:
    """取该策略最新写出的验收报告（不猜文件名，按 mtime 取最新的 json）。"""
    candidates = sorted(output_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and ("metrics" in payload or "modes" in payload or "verdict" in payload):
            return payload
    return None


def _diagnose(row: dict) -> dict:
    """**探究包**：拿它去对照训练/部署源码 —— 而不是用它下"不可行"的结论。"""
    training_dir = ROOT / "assets" / "robots" / row["robot"] / "training"
    training_ref = row.get("training_ref") or {}
    return {
        "training_ref": training_ref,
        "profile_candidates": [
            str(path.relative_to(ROOT))
            for path in sorted((training_dir / "profiles").glob("*.json"))
            if str(training_ref.get("profile") or "") in path.stem
        ],
        "training_source_dir": str(training_dir / "source") if (training_dir / "source").is_dir() else None,
        "contract_used": {
            "observation_kind": row["observation_kind"], "obs_dim": row["obs_dim"],
            "history_len": row["history_len"], "action_scale": row["action_scale"],
            "command_dims": row["command_dims"], "scales": row["scales"],
            "action_joint_order": row["action_joint_order"],
        },
        "blob": row["blob"],
        "observed": row.get("metrics"),
        "next_step": "对照 upstream 的 obs 构建器 / deploy.yaml 逐项核对（观测项次序、命令缩放、"
                     "初始姿态、增益、关节序、encoder 链），差异即线索",
    }


def sweep(*, robots: list[str] | None = None, limit: int | None = None,
          seconds: float = 6.0, seed: int = 0) -> dict:
    inventory = _policy_inventory(robots)
    if limit:
        inventory = inventory[:limit]

    results: list[dict] = []
    for index, row in enumerate(inventory, start=1):
        print(f"[{index}/{len(inventory)}] {row['artifact_id']} family={row['family']} "
              f"({row['family_source']})", flush=True)
        results.append(_run_one(row, seconds=seconds, seed=seed))

    summary = {
        "schema": "policy-availability-sweep-1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds_per_run": seconds, "seed": seed,
        "inventory": len(inventory),
        "gated": [r for r in results if r["gated"]],
        "deferred": [r for r in results if not r["gated"]],
        "self_stability_only": [r for r in results if r["self_stability_only"]],
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="部署策略可用性扫描（站立硬门 + 跟踪两档）")
    parser.add_argument("--robots", help="逗号分隔，只跑这些机型")
    parser.add_argument("--limit", type=int, help="只跑前 N 条（先验证管线）")
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    summary = sweep(
        robots=[r.strip() for r in args.robots.split(",")] if args.robots else None,
        limit=args.limit, seconds=args.seconds, seed=args.seed,
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print(f"\n扫描 {summary['inventory']} 条（站立门 {len(summary['gated'])} / "
          f"本轮不纳入 {len(summary['deferred'])}）")
    print(f"{'策略':<34}{'族':<12}{'结果':<16}跟踪达成率")
    print("-" * 78)
    needs_investigation: list[dict] = []
    for row in summary["gated"]:
        verdict = row.get("verdict") or {}
        ok = verdict.get("ok") if isinstance(verdict, dict) else None
        ratio = None
        modes = row.get("metrics")
        if isinstance(modes, list) and modes:
            ratio = (modes[0].get("quality") if isinstance(modes[0], dict) else None)
        label = "通过" if ok else ("待探究" if ok is False else "无报告")
        print(f"{row['artifact_id']:<34}{row['family']:<12}{label:<16}{ratio if ratio else ''}")
        if ok is False or ok is None:
            needs_investigation.append(row)
    if needs_investigation:
        (OUTPUT_DIR / "to_investigate.json").write_text(
            json.dumps([_diagnose(row) for row in needs_investigation], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n待探究 {len(needs_investigation)} 条 → {OUTPUT_DIR / 'to_investigate.json'}")
        print("（它们**不是**不可行：需回训练/部署源码对照观测次序、命令缩放、初始姿态、增益、关节序）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
