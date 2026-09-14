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

训练在线命令（I1 第二批）：``train create`` / ``train status`` / ``train stop`` /
``train list`` —— **需要后端在跑**，走与 Web 工作台完全相同的 HTTP 契约
（``/api/training/*``）。``--base`` 指定后端地址（默认 http://127.0.0.1:8765）；
后端不可达时给出中文可操作提示并以非 0 码退出，**绝不静默编造结果**。
原顶层 ``train <contract.json>``（10 命令时期的叶子命令）并入
``train create --contract <path>``，请求字段保持不变。
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


def _http_detail_hint(detail: str) -> str | None:
    """从错误体里提取人类可读原因（FastAPI 的 detail 可能是字符串或 dict）。"""

    try:
        parsed = json.loads(detail)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    inner = parsed.get("detail")
    if isinstance(inner, str):
        return inner
    if isinstance(inner, dict):
        for key in ("message", "reason"):
            value = inner.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _request(
    base_url: str,
    method: str,
    route: str,
    payload: object | None = None,
    *,
    headers: dict[str, str] | None = None,
    unreachable_hint: str | None = None,
    friendly_http: bool = False,
) -> object:
    """对控制面发一次 HTTP 请求并解析 JSON 响应。

    关键字参数只被训练在线命令（I1 第二批）使用，默认关闭时行为与既有
    10 个 HTTP 门面命令完全一致：

    * ``headers``          —— 追加请求头（如 Idempotency-Key）；
    * ``unreachable_hint`` —— 连接失败时的中文可操作提示模板（{base}/{reason} 占位）；
    * ``friendly_http``    —— HTTP 错误体里提取 message/reason 给可读行（原始体仍保留）。
    """

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    all_headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    request = Request(f"{base_url.rstrip('/')}{route}", data=body, method=method, headers=all_headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if friendly_http:
            hint = _http_detail_hint(detail)
            if hint:
                raise SystemExit(f"HTTP {exc.code} 请求被拒：{hint}\n{detail}") from exc
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except (URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        if unreachable_hint:
            raise SystemExit(unreachable_hint.format(base=base_url, reason=reason)) from exc
        raise SystemExit(f"无法连接控制平面 {base_url}: {reason}") from exc


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


# --------------------------------------------------------------------------------------
# 训练在线命令（I1 第二批）：需后端在跑，走 HTTP —— 与 Web 工作台同一 API 契约
# --------------------------------------------------------------------------------------
_DEFAULT_TRAIN_BASE = "http://127.0.0.1:8765"

#: 连接失败时的中文可操作提示（占位符 base/reason 由 _request 填充）
_TRAIN_UNREACHABLE_HINT = (
    "无法连接后端 {base}：{reason}\n"
    "后端未启动？可先启动后端再重试：npm start 或 uvicorn backend.api_complete:app"
    f"（默认 {_DEFAULT_TRAIN_BASE}）"
)


def _train_base(args: argparse.Namespace) -> str:
    """后端地址：子命令 ``--base`` > 全局 ``--base-url`` > 默认 http://127.0.0.1:8765。"""

    return str(getattr(args, "base", None) or args.base_url or _DEFAULT_TRAIN_BASE)


def _train_request(
    args: argparse.Namespace, method: str, route: str, payload: object | None = None, *, headers: dict[str, str] | None = None
) -> object:
    """训练命令专用请求：断连给中文可操作提示、HTTP 错误提取可读原因，**绝不静默编造结果**。"""

    return _request(
        _train_base(args), method, route, payload,
        headers=headers, unreachable_hint=_TRAIN_UNREACHABLE_HINT, friendly_http=True,
    )


def _iteration_text(record: dict) -> str:
    """把 current_iteration/max_iterations 拼成「5 / 5」；缺失侧如实留 -。"""

    current = record.get("current_iteration")
    total = record.get("max_iterations")
    if current is None:
        return "-"
    if total is None:
        return str(current)
    return f"{current} / {total}"


def _cmd_train_create(args: argparse.Namespace) -> int:
    """``train create``：按机器人预设创建训练任务（在线命令，需后端在跑）。

    契约取自 :func:`backend.robot_presets.get_robot_preset` 的 ``contract`` 字段
    （与 Web 训练页同一真值来源）；``--contract <path>`` 保留旧顶层
    ``train <file>`` 的显式契约用法，请求字段不变。
    """

    if args.contract:
        contract = _json_file(args.contract)
        num_envs = args.envs if args.envs is not None else 4096    # 旧 train 的默认规模
        max_iterations = args.iters if args.iters is not None else 1000
    else:
        from backend.robot_presets import get_robot_preset, list_robot_presets

        preset = get_robot_preset(args.robot)
        if preset is None:
            available = ", ".join(sorted(str(item.get("robot_id")) for item in list_robot_presets()))
            raise SystemExit(f"未知机器人预设 {args.robot}（可用：{available or '无'}）")
        contract = preset["contract"]
        num_envs = args.envs if args.envs is not None else 16      # 快速起步规模，见 --help 用法
        max_iterations = args.iters if args.iters is not None else 5

    body = {
        "contract": contract,
        "algorithm": args.algorithm,
        "num_envs": num_envs,
        "max_iterations": max_iterations,
        "task_name": args.task_name,
        "profile_id": args.profile,
        "device": args.device,
        "seed": args.seed,
        "smoke": args.smoke,
    }
    if args.contract:
        body["backend"] = args.backend                             # 旧用法的字段原样保留
    headers = {"Idempotency-Key": args.key} if args.key else None

    result = _train_request(args, "POST", "/api/training/create", body, headers=headers)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"训练任务已创建（在线命令）：{result.get('task_id')}")
    if result.get("idempotent_replay"):
        print("幂等重放：同 Idempotency-Key 返回既有任务，未重复启动")
    gate = result.get("smoke_gate")
    if isinstance(gate, dict):
        required = bool(gate.get("required"))
        ok = bool(gate.get("ok"))
        print(f"冒烟前置门：{'通过' if ok else '未通过'}（required={required}）")
    return 0


def _cmd_train_status(args: argparse.Namespace) -> int:
    """``train status``：输出状态/迭代/奖励（解包**内层** status 词表，在线命令，需后端）。"""

    result = _train_request(args, "GET", f"/api/training/{args.task_id}/status")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    status = result.get("status") if isinstance(result, dict) else None
    if not isinstance(status, dict):
        # 内层词表缺失/结构漂移：如实回显原始响应，不猜测字段
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"训练任务 {status.get('task_id', args.task_id)}（在线命令）")
    state = str(status.get("status", "-"))
    if state == "train_completed":
        state += "（已完成）"
    print(f"状态：{state}")
    print(f"迭代：{_iteration_text(status)}")
    reward = status.get("reward")
    print(f"奖励：{'-' if reward is None else reward}")
    error = status.get("error")
    if error:
        print(f"错误：{error}")
    return 0


def _cmd_train_stop(args: argparse.Namespace) -> int:
    """``train stop``：请求停止训练任务（在线命令，需后端）。"""

    result = _train_request(args, "POST", f"/api/training/{args.task_id}/stop")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"已请求停止训练任务：{args.task_id}")
    message = result.get("message") if isinstance(result, dict) else None
    if message:
        print(message)
    return 0


def _cmd_train_list(args: argparse.Namespace) -> int:
    """``train list``：列出后端全部训练任务（在线命令，需后端）。"""

    result = _train_request(args, "GET", "/api/training/list")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    tasks = result.get("tasks") if isinstance(result, dict) else None
    if not isinstance(tasks, list):
        # 响应结构漂移：如实回显，不编造表格
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"训练任务清单（在线命令，需后端）：{_train_base(args)}")
    if not tasks:
        print("（后端当前没有任何训练任务）")
    print(f"{'task_id':<40}{'状态':<18}{'迭代':<12}{'奖励':>10}")
    for task in tasks:
        if not isinstance(task, dict):
            continue
        reward = task.get("reward")
        print(
            f"{str(task.get('task_id', '-')):<40}{str(task.get('status', '-')):<18}"
            f"{_iteration_text(task):<12}{'-' if reward is None else str(reward):>10}"
        )
    print(f"汇总：{len(tasks)} 个任务")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Legged Studio CLI (shared Web/API contract)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765", help="running control-plane URL")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（离线 pack/run/artifact 的 list 与在线 train 各子命令均生效）")
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

    # ---- 训练在线命令（I1 第二批）：需后端在跑，与 Web 工作台同一 HTTP 契约 ----
    # 原顶层 `train <contract.json>`（10 命令时期的叶子命令）并入 `train create
    # --contract <path>`，请求字段不变；新预设用法 --robot/--profile 的契约来自
    # backend.robot_presets（与 Web 训练页同一真值来源）。
    train = sub.add_parser(
        "train",
        help="训练任务 create/status/stop/list（在线命令，需后端在跑）",
        description=f"训练任务 create/status/stop/list（在线命令，需后端在跑，默认 {_DEFAULT_TRAIN_BASE}）。",
    )
    train_sub = train.add_subparsers(dest="train_command", required=True)

    train_create = train_sub.add_parser(
        "create",
        help="创建训练任务（在线命令，需后端）",
        description=(
            "创建训练任务（在线命令，需后端在跑）。契约取自 backend.robot_presets 预设；"
            "--contract 保留旧 train <file> 的显式契约用法。示例：train create --robot "
            "unitree_go2 --profile go2-velocity-flat --envs 16 --iters 5 --seed 7 --smoke"
        ),
    )
    train_create.add_argument("--robot", default="unitree_go2", help="机器人预设 id（默认 unitree_go2；与 --contract 二选一）")
    train_create.add_argument("--profile", default=None, help="训练档案 profile_id（如 go2-velocity-flat）")
    train_create.add_argument("--contract", default=None, help="显式 Robot Contract JSON 路径（旧 train <file> 用法；给出时忽略 --robot）")
    train_create.add_argument("--algorithm", default="PPO")
    train_create.add_argument("--envs", type=int, default=None, help="并行环境数（预设用法默认 16；--contract 用法默认 4096）")
    train_create.add_argument("--iters", type=int, default=None, help="最大迭代数（预设用法默认 5；--contract 用法默认 1000）")
    train_create.add_argument("--seed", type=int, default=7, help="随机种子（默认 7）")
    train_create.add_argument("--smoke", action="store_true", default=False, help="冒烟档：未过冒烟门的长训会被后端 409 拒")
    train_create.add_argument("--task-name", default="forward_walk", help="任务名（默认 forward_walk）")
    train_create.add_argument("--device", default="auto", help="auto / cpu / cuda（默认 auto）")
    train_create.add_argument("--backend", choices=["native_mjlab"], default="native_mjlab", help="训练后端（仅 --contract 用法发送）")
    train_create.add_argument("--key", default=None, help="Idempotency-Key 幂等键（可选，重复提交返回既有任务）")
    train_create.add_argument("--base", default=None, help=f"后端地址（默认 {_DEFAULT_TRAIN_BASE}）")
    train_create.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出完整响应（含 smoke_gate 字段）")

    train_status = train_sub.add_parser(
        "status",
        help="查询任务状态/迭代/奖励（在线命令，需后端）",
        description="查询训练任务状态/迭代/奖励（在线命令，需后端在跑）。--json 输出完整响应（内层 status 才是词表）。",
    )
    train_status.add_argument("task_id", help="训练任务 id")
    train_status.add_argument("--base", default=None, help=f"后端地址（默认 {_DEFAULT_TRAIN_BASE}）")
    train_status.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出完整响应")

    train_stop = train_sub.add_parser(
        "stop",
        help="请求停止训练任务（在线命令，需后端）",
        description="请求停止训练任务（在线命令，需后端在跑）。",
    )
    train_stop.add_argument("task_id", help="训练任务 id")
    train_stop.add_argument("--base", default=None, help=f"后端地址（默认 {_DEFAULT_TRAIN_BASE}）")
    train_stop.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出完整响应")

    train_list = train_sub.add_parser(
        "list",
        help="列出后端全部训练任务（在线命令，需后端）",
        description="列出后端全部训练任务（在线命令，需后端在跑）。",
    )
    train_list.add_argument("--base", default=None, help=f"后端地址（默认 {_DEFAULT_TRAIN_BASE}）")
    train_list.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出完整响应")

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

    # 训练在线命令（I1 第二批）：需后端在跑，走 HTTP（与 Web 工作台同一契约）
    if args.command == "train":
        if args.train_command == "create":
            return _cmd_train_create(args)
        if args.train_command == "status":
            return _cmd_train_status(args)
        if args.train_command == "stop":
            return _cmd_train_stop(args)
        return _cmd_train_list(args)

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
