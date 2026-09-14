"""L7 首跑驱动：产品内「训练→导出→入库」第一次真实走通（HTTP 产品路径）。

用法：控制面 venv 运行，需要本地后端已在 127.0.0.1:8765。
步骤：POST /api/training/create（smoke 档 16 envs × 5 iters）→ 轮询 status →
POST /api/training/{task_id}/promote → 打印入库产物与验证结论。
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8765"


def call(method: str, path: str, payload: dict | None = None, *, headers: dict | None = None,
         timeout: int = 300):
    req = urllib.request.Request(
        BASE + path, method=method,
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
    from backend.robot_presets import get_robot_preset

    contract = (get_robot_preset("unitree_go2") or {}).get("contract")
    if not contract:
        print("::error:: 拿不到 unitree_go2 预设契约")
        return 1

    status, resp = call("POST", "/api/training/create", {
        "contract": contract,
        "algorithm": "PPO",
        "num_envs": 16,
        "max_iterations": 5,
        "task_name": "forward_walk",
        "profile_id": "go2-velocity-flat",
        "device": "auto",
        "smoke": True,
        "seed": 7,
        "save_interval": 5,
    }, headers={"Idempotency-Key": "l7-first-run-r3"})
    print(f"[create] HTTP {status}: {json.dumps(resp, ensure_ascii=False)[:300]}")
    if status != 200:
        return 1
    task_id = resp.get("task_id")

    deadline = time.time() + 25 * 60
    final = None
    while time.time() < deadline:
        _, st = call("GET", f"/api/training/{task_id}/status", timeout=60)
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

    status, resp = call("POST", f"/api/training/{task_id}/promote", payload={})
    print(f"[promote] HTTP {status}: {json.dumps(resp, ensure_ascii=False)[:500]}")
    if status != 200:
        return 1

    # 验证：Run 档案对账 + 产物可载入
    _, run = call("GET", f"/api/training/{task_id}/run", timeout=120)
    verify = (run or {}).get("verify") or {}
    print(f"[verify_run] {json.dumps(verify, ensure_ascii=False)[:300]}")
    print(f"[DONE] task={task_id} artifact={resp['artifact']['artifact_id']} sha={resp['artifact']['onnx_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
