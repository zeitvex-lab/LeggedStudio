"""质量攻关第二轮（新档 1024×250 口径）：命令重采样实验。

baseline = gpu-1024x250（resampling (3.0, 8.0) 默认）。
A 组假设：3–8s 才换一次指令 ⇒ 250 iters 内命令切换样本太少，策略过拟合"当前命令"，
跟踪误差（lin_vel_err / ang_vel_err）降不下来。缩短到 (1.0, 1.0) 增加切换密度。

与产品路径同口径（同 env factory / runner / asdict 展开），训练完**当进程内**
直接做 B11 同款评测（load 最优 checkpoint 不可行——评测用独立 ONNX 导出链，
这里导出与 native_worker 同源调用 onnx_exporter）。

跑法（适配器 venv，GPU 独占）：
  adapters/mjlab/.venv/Scripts/python.exe tools/quality_exp_resampling.py --label A_short
  adapters/mjlab/.venv/Scripts/python.exe tools/quality_exp_resampling.py --label CTRL --resampling 3.0,8.0
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "assets/robots/unitree_go2/training/source"))
sys.path.insert(0, str(ROOT / "adapters/mjlab"))
sys.path.insert(0, str(ROOT))

import torch  # noqa: E402

from local_tasks.robots.unitree.go2.tasks.go2_skills.upstream.velocity import (  # noqa: E402
    PROFILES,
    make_flat_env_cfg,
)
from config_introspect import set_by_path  # noqa: E402

PROFILE_ID = "go2-velocity-flat"
REPORT_DIR = ROOT / "workspace" / "validation"


def build_env(resampling: tuple[float, float]):
    from mjlab.envs import ManagerBasedRlEnv

    profile = next(p for p in PROFILES if p.task_name == "Go2")
    cfg = make_flat_env_cfg(profile)
    set_by_path(cfg, "commands.twist.resampling_time_range", resampling)
    cfg.scene.num_envs = 1024
    return ManagerBasedRlEnv(cfg, device="cuda" if torch.cuda.is_available() else "cpu")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--resampling", default="1.0,1.0")
    parser.add_argument("--iters", type=int, default=250)
    args = parser.parse_args()
    resampling = tuple(float(x) for x in args.resampling.split(","))

    import time

    from mjlab.rl import RslRlVecEnvWrapper
    from dataclasses import asdict

    # 产品同口径 runner（profile entrypoints.runner_class）：
    # VelocityOnPolicyRunner 继承 MjlabOnPolicyRunner，算法配置由 make_ppo_runner_cfg 出。
    from local_tasks.robots.unitree.go2.tasks.go2_skills.upstream.rl import (
        make_ppo_runner_cfg,
    )
    from local_tasks.robots.unitree.go2.training.runner import VelocityOnPolicyRunner

    started = datetime.now(timezone.utc)
    t0 = time.time()
    env = build_env(resampling)
    obs, _ = env.reset()

    runner_cfg = make_ppo_runner_cfg(f"resampling-{args.label}")
    runner_cfg.max_iterations = args.iters
    runner_cfg.save_interval = 50
    runner_cfg.logger = "tensorboard"
    output = REPORT_DIR / "quality_exp_runs" / f"resampling-{args.label}"
    output.mkdir(parents=True, exist_ok=True)
    wrapped = RslRlVecEnvWrapper(env, clip_actions=getattr(runner_cfg, "clip_actions", None))
    runner = VelocityOnPolicyRunner(wrapped, asdict(runner_cfg), str(output), device=env.device)
    runner.learn(num_learning_iterations=args.iters)
    wall = time.time() - t0

    # 读 tfevents 曲线（同 iter 位置口径）
    curve = []
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

        acc = EventAccumulator(str(output), size_guidance={"scalars": 0})
        acc.Reload()
        for e in acc.Scalars("Train/mean_reward"):
            curve.append({"iter": e.step, "value": round(float(e.value), 4)})
    except Exception as exc:
        curve_err = str(exc)
    else:
        curve_err = None

    report = {
        "schema": "quality-exp-resampling-1.0",
        "label": args.label,
        "resampling_time_range": list(resampling),
        "tier": {"envs": 1024, "iters": args.iters},
        "started": started.isoformat(),
        "wall_seconds": round(wall, 1),
        "rewards_smoke_gauge": round(float(curve[-1]["value"]), 4) if curve else None,
        "reward_curve_samples": curve[::25] if curve else [],
        "curve_error": curve_err,
        "output_dir": str(output.relative_to(ROOT)),
    }
    out_path = REPORT_DIR / f"quality-resampling-{args.label}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("label", "wall_seconds", "rewards_smoke_gauge")}, ensure_ascii=False))
    print(f"report -> {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
