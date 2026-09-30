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

--mode longtrain 触发长训回归档（默认 iters=2000），配合 --profile/--robot 聚焦
单个 profile 做长训验收；--baseline 提供历史基线 JSON 时逐 profile 输出退化判定，
形成可对比的发布回归基线。

Writes a JSON report under workspace/validation/ and prints a table.

Usage:
  adapters/mjlab/.venv/Scripts/python.exe tools/validate_training_smoke.py
      [--num-envs 128] [--rollout-steps 50] [--mode rollout|train|longtrain]
      [--iters 50] [--profile go2_velocity] [--robot unitree_go2] [--baseline baseline.json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 统一自举：见 contracts/path_bootstrap.py。
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contracts.path_bootstrap import bootstrap_root  # noqa: E402

ROOT = bootstrap_root()

from backend.robot_packages import list_robot_packages  # noqa: E402


def _adapter_python() -> Path:
    """定位适配器 venv 的 python（落点由 path_bootstrap 统一解析）。

    未安装时不回退到别的解释器：错误信息直接暴露"训练栈未供应"，比静默跑错栈好。
    """
    from contracts.path_bootstrap import adapter_python

    return adapter_python(default=ROOT / "adapters" / "mjlab" / ".venv")


PY_EXE = str(_adapter_python())
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
        # profile 声明的 runner 类透传给 worker（产品路径也是按它导入的）：
        # 不透传就只剩标准 PPO runner，自定义算法全部落进 skipped。
        "--runner-class", str(entry.get("runner_class") or ""),
    ]
    if mode == "train":
        cmd += ["--train", "--iters", str(iters)]

    result = {"robot_id": record["robot_id"], "profile_id": profile["profile_id"]}
    try:
        # 编码必须显式给 UTF-8：``text=True`` 默认按 **locale**（Windows=GBK）解码子进程
        # 输出，而 worker 侧写的是 UTF-8（``launcher._prepare_env`` 设 PYTHONIOENCODING=utf-8）
        # —— 含中文的输出会让 reader 线程抛 UnicodeDecodeError，``proc.stdout`` 随之变 None，
        # 于是本函数紧接着在 ``proc.stdout.strip()`` 上抛 AttributeError：**把真跑通的
        # profile 记成 crashed**（2026-09-19 实测：go2 全 profile 基线 18 档里 7 档是这样
        # 的假失败）。``errors="replace"`` 是第二道保险：即便子进程吐坏字节也只损失那几个字符。
        import os as _os
        _train_timeout = int(_os.environ.get("SMOKE_TRAIN_TIMEOUT_S", "1800"))
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=_train_timeout
        )
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


def _source_drift(record) -> list[str]:
    """包内 ``training/{profiles,source}`` 与内置源树的**文件集合**差异。

    只在"选中的是 workspace 副本"时才有意义（内置源树与自身当然一致）。有差异说明
    单向同步还没把源树的增删搬到副本 —— 此时跑冒烟**验的是旧副本**，必须判失败而不是
    静默通过（2026-09-20 go2 去包化实况：删掉 23 个文件后首次回归等于没验）。
    """
    package_root = Path(str((record.get("robot_package") or {}).get("package_root") or "")).resolve()
    shipped = (ROOT / "assets" / "robots" / str(record.get("robot_id") or "")).resolve()
    if not shipped.is_dir() or package_root == shipped:
        return []

    def _tree(root: Path) -> dict[str, int]:
        """相对路径 → 字节数。比"只比文件名"多一层：**内容被改却没同步**也看得出来
        （只看集合会漏掉"同名不同内容"的陈旧副本，而那正是最隐蔽的一种）。"""
        found: dict[str, int] = {}
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                found[path.relative_to(root).as_posix()] = path.stat().st_size
            except OSError:
                continue
        return found

    drift: list[str] = []
    for relative in ("training/profiles", "training/source"):
        source_files = _tree(shipped / relative) if (shipped / relative).is_dir() else {}
        copy_files = _tree(package_root / relative) if (package_root / relative).is_dir() else {}
        drift += [f"{relative}/{name}：源树已删、副本仍在" for name in sorted(set(copy_files) - set(source_files))]
        drift += [f"{relative}/{name}：源树有、副本缺" for name in sorted(set(source_files) - set(copy_files))]
        drift += [
            f"{relative}/{name}：内容与源树不一致（副本陈旧）"
            for name in sorted(set(source_files) & set(copy_files))
            if source_files[name] != copy_files[name]
        ]
    return drift


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-envs", type=int, default=128)
    parser.add_argument("--rollout-steps", type=int, default=50)
    parser.add_argument("--mode", choices=["rollout", "train", "longtrain"], default="rollout")
    parser.add_argument("--iters", type=int, default=50)
    parser.add_argument("--profile", default=None, help="仅验证指定 profile_id（可用于长训聚焦）")
    parser.add_argument("--robot", default=None, help="仅验证指定 robot_id")
    parser.add_argument("--baseline", type=Path, default=None,
                        help="历史基线 JSON；存在时逐 profile 对比 ok/skip/fail 与指标是否退化")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    # 长训档：--mode longtrain 时提高默认 iters 作为发布回归基线门槛。
    if args.mode == "longtrain" and args.iters == 50:
        args.iters = 2000

    started = datetime.now()
    # 源树 → workspace 副本的单向同步只在"索引重扫"时发生。改完包内训练源码就直接跑冒烟，
    # 验的可能是**旧副本**（2026-09-20 go2 去包化实况：删掉 23 个文件后首次回归等于没验，
    # 副本仍是 182 个 .py）。故这里先强制重建一次索引（会连带触发内容同步），
    # 再在下面逐 profile 断言"副本源码集合 == 源树"，不一致就判失败而非静默通过。
    from backend.robot_packages import rebuild_package_index  # noqa: PLC0415

    rebuild_package_index()
    records = list_robot_packages()
    results = []
    for record in records:
        if args.robot and record["robot_id"] != args.robot:
            continue
        for profile in record.get("training_profiles", []):
            if args.profile and profile["profile_id"] != args.profile:
                continue
            entry = {"robot_id": record["robot_id"], "profile_id": profile["profile_id"]}
            drift = _source_drift(record)
            if drift:
                res = {
                    "status": "failed",
                    "error": "包内训练源码与内置源树不一致（此时验的是旧副本，结论不可信）："
                             + "; ".join(drift[:4]),
                }
            else:
                res = validate_profile_subprocess(record, profile, args.num_envs, args.rollout_steps, args.mode, args.iters)
            entry.update(res)
            flag = "OK " if res["status"] == "ok" else ("SK " if res["status"].startswith("skip") else "!! ")
            print(f"[{flag}] {entry['robot_id']}/{entry['profile_id']} -> {res['status']}")
            results.append(entry)

    baseline_compare = None
    if args.baseline and args.baseline.exists():
        baseline_compare = _compare_baseline(results, args.baseline)

    report = {
        "started": started.isoformat(),
        "mode": args.mode,
        "num_envs": args.num_envs,
        "iters": args.iters,
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "skipped": sum(1 for r in results if r["status"].startswith("skip")),
        "failed": [r for r in results if r["status"] not in ("ok",) and not r["status"].startswith("skip")],
        "results": results,
        "baseline_compare": baseline_compare,
    }
    report_dir = ROOT / "workspace" / "validation"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report or (report_dir / f"report-{args.mode}-{started.strftime('%Y%m%d-%H%M%S')}.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("")
    print(f"report: {report_path}")
    print(f"summary: {report['ok']} ok / {report['total']} total, {report['skipped']} skipped, {len(report['failed'])} failed")
    if baseline_compare:
        regressed = [c for c in baseline_compare["per_profile"] if c.get("regressed")]
        print(f"baseline: {len(baseline_compare['per_profile'])} compared, {len(regressed)} regressed")
        if regressed:
            for c in regressed:
                print(f"  REGRESSED {c['robot_id']}/{c['profile_id']}: {c.get('regression_reason')}")
    raise SystemExit(1 if report["failed"] else 0)


def _compare_baseline(results: list[dict], baseline_path: Path) -> dict:
    """把本次结果与历史基线 JSON 对比，返回逐 profile 的退化判定。

    基线里相同 robot_id/profile_id 的记录若本次从 ok 退化到失败/非有限，
    或以相同 mode 跑出更差的 rewards（长训回归），则标记 regressed。
    """
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"error": f"cannot parse baseline {baseline_path}"}
    base_by_key = {}
    for item in baseline.get("results", []):
        base_by_key[(item.get("robot_id"), item.get("profile_id"))] = item

    per_profile = []
    for item in results:
        key = (item.get("robot_id"), item.get("profile_id"))
        base = base_by_key.get(key)
        record = {
            "robot_id": item.get("robot_id"),
            "profile_id": item.get("profile_id"),
            "status": item.get("status"),
            "rewards": item.get("rewards"),
            "regressed": False,
            "regression_reason": None,
        }
        if base is None:
            record["regression_reason"] = "no_baseline_entry"
            per_profile.append(record)
            continue
        base_status = base.get("status")
        # 基线为 ok，本次退化到失败/非有限 → 退化
        if base_status == "ok" and item.get("status") not in ("ok",):
            record["regressed"] = True
            record["regression_reason"] = f"status {base_status} -> {item.get('status')}"
        # 长训回归：同 profile 曾有 rewards，本次 rewards 显著更差
        elif item.get("rewards") is not None and base.get("rewards") is not None:
            base_r = float(base["rewards"])
            cur_r = float(item["rewards"])
            if base_r > 0 and cur_r < base_r * 0.8:
                record["regressed"] = True
                record["regression_reason"] = f"rewards {cur_r:.4f} < 0.8*base {base_r:.4f}"
        per_profile.append(record)
    return {"baseline_file": str(baseline_path), "per_profile": per_profile}


if __name__ == "__main__":
    # 作为 CLI 运行（`python tools/validate_training_smoke.py ...`）时必须有这个
    # 入口：缺失会让整条命令静默退出 0，CI 门禁看起来"绿"但什么都没跑。
    main()
