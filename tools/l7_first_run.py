"""L7 首跑/多机型驱动：产品内「训练→导出→入库」（HTTP 产品路径）。

用法：控制面 venv 运行，需要本地后端已起（默认 127.0.0.1:8766）：
    .venv/Scripts/python.exe tools/l7_first_run.py --robot unitree_go1 --profile go1-velocity
    .venv/Scripts/python.exe tools/l7_first_run.py --robot unitree_g1 --profile g1-velocity-flat
步骤：POST /api/training/create（smoke 档 16 envs × 5 iters）→ 轮询 status →
POST /api/training/{task_id}/promote → 打印入库产物与验证结论。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def call(base: str, method: str, path: str, payload: dict | None = None, *,
         headers: dict | None = None, timeout: int = 300):
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def main() -> int:
    parser = argparse.ArgumentParser(description="L7 产品内 训练→导出→入库 冒烟驱动（单机型一次）")
    parser.add_argument("--robot", default="unitree_go2", help="机型 robot_id（默认 unitree_go2）")
    parser.add_argument("--profile", default="go2-velocity-flat", help="训练 profile_id（默认 go2-velocity-flat）")
    parser.add_argument("--seed", type=int, default=7, help="训练种子（默认 7）")
    parser.add_argument("--port", type=int, default=8766, help="后端端口（默认 8766）")
    parser.add_argument("--key", default=None,
                        help="Idempotency-Key（缺省按 robot+时间生成，即每次运行都是新任务）")
    parser.add_argument("--timeout-min", type=int, default=25, help="轮询总超时分钟数（默认 25）")
    parser.add_argument("--num-envs", type=int, default=16, help="训练环境数（默认 16 = smoke 档）")
    parser.add_argument("--iters", type=int, default=5, help="训练迭代数（默认 5 = smoke 档）")
    parser.add_argument("--product", action="store_true", help="产品档（smoke=False，1024×750 等由 --num-envs/--iters 给）")
    args = parser.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    idem = args.key or (
        f"l7-{args.robot.replace('_', '-')}-"
        + _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    )

    from backend.robot_presets import get_robot_preset

    contract = (get_robot_preset(args.robot) or {}).get("contract")
    if not contract:
        print(f"::error:: 拿不到 {args.robot} 预设契约")
        return 1

    status, resp = call(base, "POST", "/api/training/create", {
        "contract": contract,
        "algorithm": "PPO",
        "num_envs": args.num_envs,
        "max_iterations": args.iters,
        "task_name": "forward_walk",
        "profile_id": args.profile,
        "device": "auto",
        "smoke": not args.product,
        "seed": args.seed,
        "save_interval": 250,  # 冒烟/长训逐键一致（smoke_gate 除规模外逐键比对）
    }, headers={"Idempotency-Key": idem})
    print(f"[create] HTTP {status}: {json.dumps(resp, ensure_ascii=False)[:300]}")
    if status != 200:
        return 1
    task_id = resp.get("task_id")

    deadline = time.time() + args.timeout_min * 60
    final = None
    while time.time() < deadline:
        _, st = call(base, "GET", f"/api/training/{task_id}/status", timeout=60)
        # /status 响应形状是 {"success": ..., "status": {任务状态}}——解包后才是状态词表
        if isinstance(st.get("status"), dict):
            st = st["status"]
        final = st
        line = f"status={st.get('status')} iter={st.get('current_iteration')}/{st.get('max_iterations')} reward={st.get('reward')}"
        print(f"[poll] {line}", flush=True)
        if st.get("status") in ("completed", "train_completed", "failed", "error", "stopped"):
            break
        time.sleep(10)

    if not final or final.get("status") not in ("completed", "train_completed"):
        print(f"::error:: 任务未完成：{json.dumps(final, ensure_ascii=False)[:500]}")
        return 1

    status, resp = call(base, "POST", f"/api/training/{task_id}/promote", payload={})
    print(f"[promote] HTTP {status}: {json.dumps(resp, ensure_ascii=False)[:500]}")
    if status != 200:
        return 1

    # 验证：Run 档案对账 + 产物可载入
    _, run = call(base, "GET", f"/api/training/{task_id}/run", timeout=120)
    verify = (run or {}).get("verify") or {}
    print(f"[verify_run] ok={verify.get('ok')} {json.dumps(verify, ensure_ascii=False)[:300]}")
    print(f"[DONE] robot={args.robot} task={task_id} artifact={resp['artifact']['artifact_id']} sha={resp['artifact']['onnx_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
