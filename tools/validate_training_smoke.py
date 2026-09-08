"""Batch smoke-validate every robot training profile in Legged Studio.

Each profile is validated in an isolated subprocess (sys.path state from
different packages must not leak into each other).  For each profile:

1. import the env factory (source_root + package_root on sys.path),
2. build the env config and instantiate a mjlab ManagerBasedRlEnv,
3. roll out --rollout-steps control steps with zero actions,
4. check rewards stay finite,
5. with --mode train additionally run --iters PPO iterations for profiles
   whose runner is the standard RslRlOnPolicyRunnerCfg path (custom runners
   such as AMP / DreamWaQ are reported as skipped).

Writes a JSON report under workspace/validation/ and prints a table.

Usage:
  adapters/mjlab/.venv/Scripts/python.exe tools/validate_training_smoke.py
      [--num-envs 128] [--rollout-steps 50] [--mode rollout|train] [--iters 50]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT)
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

from backend.robot_packages import list_robot_packages  # noqa: E402

PY_EXE = str(ROOT / "adapters" / "mjlab" / ".venv" / "Scripts" / "python.exe")
SMOKE_ONE = ROOT / "tools" / "_smoke_one.py"


def validate_profile_subprocess(record, profile, num_envs, rollout_steps, mode, iters):
    package_root = str(Path(str(record["robot_package"]["package_root"])))
    source_rel = str(profile.get("source_root", "training/source")).replace("\\", "/")
    if Path(source_rel).is_absolute():
        source_root = source_rel
    else:
        source_root = str((Path(package_root) / source_rel).resolve())

    entry = profile.get("entrypoints") or {}
    cmd = [
        PY_EXE, str(SMOKE_ONE),
        package_root, source_root,
        entry.get("env", ""), entry.get("runner", "-"),
        str(num_envs), str(rollout_steps),
    ]
    if mode == "train":
        cmd += ["--train", "--iters", str(iters)]

    result = {"robot_id": record["robot_id"], "profile_id": profile["profile_id"]}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        json_line = None
        for line in reversed(proc.stdout.strip().splitlines()):
            if line.startswith("{"):
                json_line = line
                break
        if json_line:
            result.update(json.loads(json_line))
        if proc.returncode not in (0, 1) and result.get("status") in (None, "unknown"):
            result["status"] = "crashed"
            result["error"] = (proc.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["error"] = "timeout after 1800s"
    except Exception as exc:
        result["status"] = "crashed"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-envs", type=int, default=128)
    parser.add_argument("--rollout-steps", type=int, default=50)
    parser.add_argument("--mode", choices=["rollout", "train"], default="rollout")
    parser.add_argument("--iters", type=int, default=50)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    started = datetime.now()
    records = list_robot_packages()
    results = []
    for record in records:
        for profile in record.get("training_profiles", []):
            entry = {"robot_id": record["robot_id"], "profile_id": profile["profile_id"]}
            res = validate_profile_subprocess(record, profile, args.num_envs, args.rollout_steps, args.mode, args.iters)
            entry.update(res)
            flag = "OK " if res["status"] == "ok" else ("SK " if res["status"].startswith("skip") else "!! ")
            print(f"[{flag}] {entry['robot_id']}/{entry['profile_id']} -> {res['status']}")
            results.append(entry)

    report = {
        "started": started.isoformat(),
        "mode": args.mode,
        "num_envs": args.num_envs,
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "skipped": sum(1 for r in results if r["status"].startswith("skipped")),
        "failed": [r for r in results if r["status"] not in ("ok",) and not r["status"].startswith("skipped")],
        "results": results,
    }
    report_dir = ROOT / "workspace" / "validation"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report or (report_dir / f"report-{started.strftime('%Y%m%d-%H%M%S')}.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("")
    print(f"report: {report_path}")
    print(f"summary: {report['ok']} ok / {report['total']} total, {report['skipped']} skipped, {len(report['failed'])} failed")
    raise SystemExit(1 if report["failed"] else 0)


if __name__ == "__main__":
    main()
