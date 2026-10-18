#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计可试玩策略的训练源（2026-10-17 用户口径）。

规则：`simulation/config.json` 的每条可试玩策略都必须声明
`training_ref.profile`，且该 profile 必须真实存在并带 `entrypoints.env`。
不能回溯到训练代码的“产物-only”策略不再允许出现在可试玩清单里。

用法：
    python tools/audit_playable_policy_training.py [--json report.json]

退出码：0 = 全部可回溯；1 = 有缺训练源的策略或索引不一致。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _module_candidates(package_root: Path, module: str) -> list[Path]:
    rel = module.replace(".", "/")
    return [
        package_root / "training" / "source" / f"{rel}.py",
        package_root / "training" / "source" / rel / "__init__.py",
        package_root / f"{rel}.py",
        ROOT / "adapters" / "mjlab" / f"{rel}.py",
        ROOT / "adapters" / "mjlab" / rel / "__init__.py",
        ROOT / f"{rel}.py",
    ]


def audit() -> dict:
    from backend.robot_packages import list_robot_packages

    records = []
    problems = []
    not_ready = []
    for record in list_robot_packages():
        robot = str(record.get("robot_id") or "")
        package = record.get("robot_package") or {}
        root = Path(str(package.get("package_root") or record.get("package_root") or ""))
        config_path = root / "simulation" / "config.json"
        if not robot or not config_path.is_file():
            continue
        config = _read(config_path) or {}
        for key in ("policies", "demo_policies"):
            for policy in config.get(key) or []:
                if not isinstance(policy, dict):
                    continue
                pid = str(policy.get("id") or "")
                if policy.get("sim_ready") is False:
                    not_ready.append(f"{robot}--{pid}")
                    continue
                training_ref = policy.get("training_ref") or {}
                profile_id = str(training_ref.get("profile") or "")
                entry = {
                    "robot": robot,
                    "policy": pid,
                    "list": key,
                    "profile": profile_id,
                    "package_root": str(root),
                    "entrypoints_env": "",
                    "source": "missing",
                    "ok": False,
                    "reason": "",
                }
                if not profile_id:
                    entry["reason"] = "training_ref.profile 为空（无可回溯训练源）"
                    problems.append(entry)
                    records.append(entry)
                    continue
                profile_path = root / "training" / "profiles" / f"{profile_id}.json"
                profile = _read(profile_path)
                if not profile:
                    entry["reason"] = f"训练 profile 不存在：{profile_path}"
                    problems.append(entry)
                    records.append(entry)
                    continue
                env = str((profile.get("entrypoints") or {}).get("env") or "")
                entry["entrypoints_env"] = env
                if not env or ":" not in env:
                    entry["reason"] = "profile.entrypoints.env 为空或格式不对"
                    problems.append(entry)
                    records.append(entry)
                    continue
                module = env.split(":", 1)[0].strip()
                candidates = _module_candidates(root, module)
                found = next((p for p in candidates if p.is_file()), None)
                if found is not None:
                    entry["source"] = str(found.relative_to(ROOT)).replace("\\", "/")
                elif module.startswith(("mjlab.", "rsl_rl.", "torch.")):
                    entry["source"] = f"external:{module}"
                else:
                    entry["reason"] = f"训练入口模块解析不到：{module}"
                    problems.append(entry)
                    records.append(entry)
                    continue
                entry["ok"] = True
                records.append(entry)

    # pretrained_models/index.json 是产品面的试玩清单；必须与包声明同步。
    index_path = ROOT / "pretrained_models" / "index.json"
    index = _read(index_path)
    declared = {f"{r['robot']}--{r['policy']}" for r in records}
    indexed = {str(x.get("id") or "") for x in (index or []) if isinstance(x, dict)}
    missing_in_index = sorted(declared - indexed)
    stale_in_index = sorted(indexed - declared)
    if missing_in_index or stale_in_index:
        problems.append({
            "robot": "*",
            "policy": "*",
            "list": "pretrained_models/index.json",
            "profile": "",
            "package_root": "",
            "entrypoints_env": "",
            "source": "index",
            "ok": False,
            "reason": (
                f"索引不同步：缺 {len(missing_in_index)} 条 "
                f"({', '.join(missing_in_index[:5])})；多 {len(stale_in_index)} 条 "
                f"({', '.join(stale_in_index[:5])})；先跑 tools/generate_pretrained_index.py"
            ),
        })

    return {
        "ok": not problems,
        "checked": len(records),
        "indexed": len(indexed),
        "not_ready": sorted(not_ready),
        "problems": problems,
        "policies": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="把报告写到文件")
    args = parser.parse_args()
    report = audit()
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(
        f"checked={report['checked']} indexed={report['indexed']} "
        f"not_ready={len(report['not_ready'])} problems={len(report['problems'])}"
    )
    for problem in report["problems"][:50]:
        print(f"  - {problem.get('robot')}/{problem.get('policy')}: {problem.get('reason')}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
