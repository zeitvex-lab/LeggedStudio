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


ROOT = Path(__file__).resolve().parents[1]


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
        # checkpoint 磁盘纪律（2026-09-30，C 盘满员事故后立规）：落盘频率按预算
        # 自适应——一轮训练至多 ~10 个中间 checkpoint（4 万轮 → 每 4000 轮一个，
        # ≈45MB/run；旧固定 250 是 712MB/run，直接把 C 盘写满）。smoke_gate 已把
        # save_interval 列入豁免（它不影响训练行为，只影响落盘节奏）。
        "save_interval": max(250, args.iters // 10),
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
        it, rew = st.get("current_iteration"), st.get("reward")
        # /status 的进度字段是任务级快照（worker 完成时才刷新，长训全程恒 0——
        # 2026-09-30 实测 20000 轮全程 0/20000）。真进度在 run 目录的 training.log
        #（与 task_id 同名），tail 末条 `Learning iteration N/M` + `Mean reward` 兜底。
        run_log = ROOT / "workspace" / str(task_id) / "training.log"
        if run_log.is_file():
            try:
                tail = run_log.read_text(encoding="utf-8", errors="ignore").splitlines()[-40:]
                iters = [ln for ln in tail if "Learning iteration" in ln]
                rewards = [ln for ln in tail if "Mean reward" in ln]
                ansi = __import__("re").compile(r"\x1b\[[0-9;]*m")
                if iters:
                    it = ansi.sub("", iters[-1].split("Learning iteration")[-1]).strip()
                if rewards:
                    rew = ansi.sub("", rewards[-1].split("Mean reward:")[-1]).strip()
            except OSError:
                pass  # 日志被轮转/删了就回退 API 快照，如实显示
        line = f"status={st.get('status')} iter={it}/{st.get('max_iterations')} reward={rew}"
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
