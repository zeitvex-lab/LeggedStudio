"""CLI 在线命令：train 族（自 scripts/legged_studio_cli.py 拆分，2026-10-12；函数体零改动）。

train create/status/stop/list——需后端在跑，走与 Web 工作台相同的 /api/training/* 契约。
"""

from __future__ import annotations

import json

from scripts.cli.http import _json_file, _request

_DEFAULT_TRAIN_BASE = "http://127.0.0.1:8765"
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
