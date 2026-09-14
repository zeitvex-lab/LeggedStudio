#!/usr/bin/env python3
"""Command-line facade for the Legged Studio control-plane API.

The CLI intentionally calls the same HTTP contract used by the Web workbench.
It is therefore useful for smoke tests today and a stable automation surface
for native MJLab/Isaac adapters later.

离线子命令（I1 第一批）：``pack list`` / ``run list`` / ``artifact list``
不连控制面，直接读仓库数据，并且**复用 backend/ 的同一实现**（单一真值来源）：

* ``pack list``     → :func:`backend.pack_catalog.pack_catalog`（与 ``tools/validate_packs.py`` 同源）；
* ``run list``      → 扫描 ``workspace/`` 下含 ``run.json`` 的目录 + :func:`backend.training.runs.load_run`；
* ``artifact list`` → :func:`backend.policy_artifacts.load_index`。

因此这些命令**无需后端**（离线命令），只是参数解析与输出格式化在本文件完成。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# 仓库根 bootstrap：脚本方式运行时 sys.path[0] 是 scripts/，离线命令要 import backend.*
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _request(base_url: str, method: str, route: str, payload: object | None = None) -> object:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{route}",
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"无法连接控制平面 {base_url}: {exc.reason}") from exc


def _json_file(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------
# 离线命令（I1 第一批）：不连控制面，直接读仓库数据；逻辑一律复用 backend/，这里只做输出
# --------------------------------------------------------------------------------------
def _cmd_pack_list(as_json: bool) -> int:
    """``pack list``：列出 packs/ 下全部 Pack 及校验状态（离线命令，无需后端）。

    校验清单与 ``tools/validate_packs.py``、``GET /api/packs`` 同源——都走
    :func:`backend.pack_catalog.pack_catalog`，不抄第二份逻辑。
    """

    from backend.pack_catalog import pack_catalog

    catalog = pack_catalog()
    if as_json:
        payload = {
            "packs_dir": catalog["packs_dir"],
            "count": catalog["count"],
            "valid_count": catalog["valid_count"],
            "invalid_count": catalog["invalid_count"],
            "duplicates": catalog["duplicates"],
            "packs": [
                {
                    "pack_id": entry["pack_id"],
                    "valid": entry["valid"],
                    "file": entry["file"],
                    "errors": entry["errors"],
                    "warnings": entry["warnings"],
                }
                for entry in catalog["packs"]
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Pack 校验清单（离线命令，无需后端）：{catalog['packs_dir']}")
    print(f"{'pack_id':<26}{'校验':<6}{'错误':>4}{'警告':>4}  文件")
    for entry in catalog["packs"]:
        mark = "通过" if entry["valid"] else "失败"
        print(
            f"{entry['pack_id']:<26}{mark:<6}"
            f"{len(entry['errors']):>4}{len(entry['warnings']):>4}  {entry['file']}"
        )
        for error in entry["errors"]:
            print(f"    - {error}")
    print(f"汇总：{catalog['count']} 个 Pack，{catalog['valid_count']} 通过，{catalog['invalid_count']} 失败")
    return 0


def _workspace_root(workspace: str | None) -> Path:
    """workspace 根：``--workspace`` 参数 > 环境变量 > 仓库 ``workspace/``（与 backend 各模块同约定）。"""

    if workspace:
        return Path(workspace).expanduser()
    configured = os.environ.get("LEGGED_STUDIO_WORKSPACE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    from backend.training.runs import ROOT

    return ROOT / "workspace"


def _run_status(run_dir: Path, fallback: str) -> str:
    """读 ``status.json`` 的 ``status`` 字段；缺失/不可解析时回退 run.json 自带的 status（如实，不编造）。"""

    try:
        payload = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    value = payload.get("status") if isinstance(payload, dict) else None
    return str(value) if value else fallback


def _cmd_run_list(as_json: bool, workspace: str | None) -> int:
    """``run list``：列出 workspace/ 下含 run.json 的训练任务（离线命令，无需后端）。

    记录一律经 :func:`backend.training.runs.load_run` 读回（与后端同一实现）；
    不含 run.json 的旧目录**如实跳过**并在末尾汇总，不算作 Run。
    """

    from backend.training import runs

    root = _workspace_root(workspace)
    entries: list[dict] = []
    skipped: list[str] = []
    if root.is_dir():
        for child in sorted(path for path in root.iterdir() if path.is_dir()):
            if not (child / "run.json").is_file():
                skipped.append(child.name)
                continue
            try:
                record = runs.load_run(child)
            except (TypeError, ValueError, KeyError):
                record = None  # run.json 结构漂移：按“读不出来”如实处理，不崩
            if record is None:
                skipped.append(child.name)
                continue
            entries.append({
                "run_id": record.run_id,
                "robot_id": record.robot_id,
                "seed": record.seed,
                "status": _run_status(child, record.status),
                "created_at": record.created_at,
            })

    if as_json:
        payload = {"workspace": str(root), "count": len(entries), "runs": entries, "skipped": skipped}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"训练 Run 清单（离线命令，无需后端）：{root}")
    if not entries:
        print("（没有含 run.json 的任务目录）")
    print(f"{'run_id':<44}{'robot_id':<16}{'seed':>5}  {'状态':<16}创建时间")
    for entry in entries:
        print(
            f"{entry['run_id']:<44}{entry['robot_id']:<16}{entry['seed']:>5}"
            f"  {entry['status']:<16}{entry['created_at']}"
        )
    print(f"汇总：{len(entries)} 个 Run")
    if skipped:
        print(f"跳过 {len(skipped)} 个无 run.json 的目录：{', '.join(skipped)}")
    return 0


def _cmd_artifact_list(as_json: bool, out_dir: str | None) -> int:
    """``artifact list``：列出 policies/ 出库索引全部产物（离线命令，无需后端）。

    索引读回一律走 :func:`backend.policy_artifacts.load_index`（与后端同一实现）；
    ``produced`` 条目（产品自产策略）特别标注。
    """

    from backend.policy_artifacts import OUT_DIR, load_index

    root = Path(out_dir).expanduser() if out_dir else OUT_DIR
    index = load_index(root)
    artifacts = [
        {
            "artifact_id": artifact_id,
            "kind": entry.get("kind"),
            "produced": entry.get("kind") == "produced",
            "onnx_sha256_prefix": (entry.get("onnx_sha256") or "")[:12] or None,
            "onnx_bytes": entry.get("onnx_bytes"),
        }
        for artifact_id, entry in sorted(index.items())
    ]
    produced_count = sum(1 for item in artifacts if item["produced"])

    if as_json:
        payload = {
            "out_dir": str(root),
            "count": len(artifacts),
            "produced_count": produced_count,
            "artifacts": artifacts,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"策略产物清单（离线命令，无需后端）：{root}")
    if not artifacts:
        print("（出库索引为空：先跑 backend.policy_artifacts.build_all(write=True)）")
    print(f"{'artifact_id':<44}{'kind':<12}{'onnx_sha256':<14}{'bytes':>10}")
    for item in artifacts:
        kind = "produced *" if item["produced"] else str(item["kind"] or "-")
        prefix = item["onnx_sha256_prefix"] or "-"
        size = "-" if item["onnx_bytes"] is None else str(item["onnx_bytes"])
        print(f"{item['artifact_id']:<44}{kind:<12}{prefix:<14}{size:>10}")
    print(f"汇总：{len(artifacts)} 个产物（其中产品自产 produced {produced_count} 个，标 * 号）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Legged Studio CLI (shared Web/API contract)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765", help="running control-plane URL")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（对离线子命令 pack/run/artifact 的 list 生效）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("algorithms", help="list registered algorithms")
    sub.add_parser("hardware", help="show CUDA and native MJLab capabilities")
    model = sub.add_parser("validate-model", help="validate a URDF/MJCF model")
    model.add_argument("path")
    model.add_argument("--format", choices=["auto", "urdf", "mjcf"], default="auto")
    contract = sub.add_parser("validate-contract", help="validate a Robot Contract JSON")
    contract.add_argument("path")
    scenario = sub.add_parser("validate-scenario", help="validate a Scenario Contract JSON")
    scenario.add_argument("path")
    sub.add_parser("maps", help="list simulation and navigation maps")

    simulate = sub.add_parser("simulate", help="create and optionally step a simulation session")
    simulate.add_argument("--robot", default="unitree_go2")
    simulate.add_argument("--map", default="flat", dest="map_id")
    simulate.add_argument("--mode", choices=["basic", "navigation"], default="basic")
    simulate.add_argument("--steps", type=int, default=0)
    simulate.add_argument("--vx", type=float, default=0.0)
    simulate.add_argument("--vy", type=float, default=0.0)
    simulate.add_argument("--wz", type=float, default=0.0)

    train = sub.add_parser("train", help="create a training task")
    train.add_argument("contract", help="Robot Contract JSON")
    train.add_argument("--algorithm", default="PPO")
    train.add_argument("--iterations", type=int, default=1000)
    train.add_argument("--num-envs", type=int, default=4096)
    train.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    train.add_argument("--backend", choices=["native_mjlab"], default="native_mjlab")

    evaluate = sub.add_parser("evaluate", help="evaluate a completed task")
    evaluate.add_argument("task_id")
    evaluate.add_argument("--episodes", type=int, default=5)

    navigation = sub.add_parser("navigation", help="run a waypoint replay")
    navigation.add_argument("task_id")
    navigation.add_argument("--map", default="warehouse", dest="map_id")
    navigation.add_argument("--mode", choices=["auto", "manual"], default="auto", dest="control_mode")
    navigation.add_argument("--waypoints", default="0,0;2,0;4,0", help="x,y; x,y; ...")
    navigation.add_argument("--obstacles", default="", help="cx,cy,hw,hh; cx,cy,hw,hh; ... (optional map obstacles)")
    navigation.add_argument("--planner", default="astar", choices=["astar", "dijkstra"], dest="algorithm")
    navigation.add_argument("--use-planner", action="store_true", default=False, dest="use_planner")
    navigation.add_argument("--no-avoidance", action="store_true", default=False, dest="no_avoidance")

    # ---- 离线命令（I1 第一批）：不连控制面，直接读仓库数据，复用 backend/ 同一实现 ----
    # --json 在叶子子命令上再声明一次（default=SUPPRESS，不覆盖全局 --json 的值），
    # 因此 `--json pack list` 与 `pack list --json` 两种写法都可用。
    pack = sub.add_parser("pack", help="Capability Pack 目录（离线命令，无需后端）")
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)
    pack_list = pack_sub.add_parser(
        "list",
        help="列出 packs/ 下全部 Pack 及校验状态（离线命令，无需后端）",
        description="列出 packs/ 下全部 Pack 及校验状态（离线命令，无需后端）。",
    )
    pack_list.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    run = sub.add_parser("run", help="训练 Run 档案（离线命令，无需后端）")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    run_list = run_sub.add_parser(
        "list",
        help="列出 workspace/ 下含 run.json 的训练任务（离线命令，无需后端）",
        description="列出 workspace/ 下含 run.json 的训练任务（离线命令，无需后端）。",
    )
    run_list.add_argument("--workspace", default=None, help="workspace 根目录（默认：LEGGED_STUDIO_WORKSPACE 环境变量或仓库 workspace/）")
    run_list.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    artifact = sub.add_parser("artifact", help="策略产物出库索引（离线命令，无需后端）")
    artifact_sub = artifact.add_subparsers(dest="artifact_command", required=True)
    artifact_list = artifact_sub.add_parser(
        "list",
        help="列出 policies/ 出库索引全部产物（离线命令，无需后端）",
        description="列出 policies/ 出库索引全部产物（离线命令，无需后端）。",
    )
    artifact_list.add_argument("--out-dir", default=None, help="出库目录（默认：仓库 policies/）")
    artifact_list.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 离线命令：不走 HTTP，直接复用 backend/ 实现读仓库数据，处理完即返回
    if args.command == "pack":
        return _cmd_pack_list(args.json)
    if args.command == "run":
        return _cmd_run_list(args.json, args.workspace)
    if args.command == "artifact":
        return _cmd_artifact_list(args.json, args.out_dir)

    base = args.base_url
    if args.command == "algorithms":
        result = _request(base, "GET", "/api/training/options")
    elif args.command == "hardware":
        result = _request(base, "GET", "/api/training/hardware")
    elif args.command == "validate-model":
        result = _request(base, "POST", "/api/models/validate", {"path": args.path, "format": args.format})
    elif args.command == "validate-contract":
        result = _request(base, "POST", "/api/contracts/validate", _json_file(args.path))
    elif args.command == "validate-scenario":
        result = _request(base, "POST", "/api/scenarios/validate", _json_file(args.path))
    elif args.command == "maps":
        result = _request(base, "GET", "/api/simulation/maps")
    elif args.command == "simulate":
        result = _request(base, "POST", "/api/simulation/sessions", {"robot_id": args.robot, "map_id": args.map_id, "mode": args.mode})
        for _ in range(max(0, args.steps)):
            session_id = result["session_id"]
            result = _request(base, "POST", f"/api/simulation/sessions/{session_id}/step", {"command": {"vx": args.vx, "vy": args.vy, "wz": args.wz}})
    elif args.command == "train":
        result = _request(base, "POST", "/api/training/create", {"contract": _json_file(args.contract), "algorithm": args.algorithm, "max_iterations": args.iterations, "num_envs": args.num_envs, "device": args.device, "backend": args.backend})
    elif args.command == "evaluate":
        result = _request(base, "POST", "/api/evaluation/run", {"task_id": args.task_id, "episodes": args.episodes})
    else:
        waypoints = [[float(value) for value in point.split(",")] for point in args.waypoints.split(";")]
        obstacles = []
        for item in args.obstacles.split(";") if args.obstacles else []:
            if item.strip():
                obstacles.append([float(value) for value in item.split(",")])
        result = _request(base, "POST", "/api/navigation/run", {
            "task_id": args.task_id, "map_id": args.map_id, "control_mode": args.control_mode,
            "waypoints": waypoints, "obstacles": obstacles, "algorithm": args.algorithm,
            "use_planner": args.use_planner, "use_avoidance": not args.no_avoidance,
        })
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
