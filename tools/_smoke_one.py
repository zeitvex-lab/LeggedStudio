"""Validate a single training profile (runs in an isolated subprocess).

Usage:
  python tools/_smoke_one.py <package_root> <source_root> <env_factory> \
      <runner_factory_or_-> <num_envs> <rollout_steps> [--train --iters N]

Prints a JSON result object to stdout.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import torch

package_root, source_root, env_factory, runner_factory, num_envs, rollout_steps = sys.argv[1:7]
train_mode = "--train" in sys.argv
iters = int(sys.argv[sys.argv.index("--iters") + 1]) if "--iters" in sys.argv else 50

sys.path.insert(0, str(Path(source_root).resolve()))
sys.path.insert(0, str(Path(package_root).resolve()))

result = {"status": "unknown", "error": None, "rewards": None}

try:
    device = "cuda:0" if torch.cuda.is_available() else "cpu"

    mod_name, _, attr = env_factory.partition(":")
    if not mod_name or not attr:
        raise ValueError(f"bad env factory: {env_factory!r}")
    module = __import__(mod_name, fromlist=[attr])
    env_cfg_factory = getattr(module, attr)
    cfg = env_cfg_factory(play=False)
    cfg.scene.num_envs = int(num_envs)

    from mjlab.envs import ManagerBasedRlEnv

    env = ManagerBasedRlEnv(cfg, device=device)

    total = 0.0
    finite = True
    for _ in range(int(rollout_steps)):
        action = env.action_manager.action
        env.step(action)
        buf = getattr(env.reward_manager, "_reward_buf", None)
        if buf is not None:
            t = float(torch.sum(buf).item())
            total += t
            if not torch.isfinite(torch.as_tensor(t)):
                finite = False
    result["status"] = "ok" if finite else "non_finite_reward"
    if not finite:
        result["error"] = "non-finite reward terms during rollout"
    result["rewards"] = round(total / max(int(rollout_steps), 1), 6)

    if train_mode:
        runner_mod, _, runner_attr = runner_factory.partition(":")
        if not runner_mod or not runner_attr:
            raise ValueError(f"bad runner factory: {runner_factory!r}")
        runner_mod_obj = __import__(runner_mod, fromlist=[runner_attr])
        runner_cfg = getattr(runner_mod_obj, runner_attr)()
        algo_class = str(getattr(runner_cfg.algorithm, "class_name", "PPO"))
        if algo_class != "PPO":
            result["status"] = "skipped_custom_runner"
            result["error"] = f"algorithm {algo_class} requires its custom runner"
        else:
            from mjlab.rl import RslRlVecEnvWrapper
            from rsl_rl.runners import OnPolicyRunner

            runner_cfg.max_iterations = iters
            runner_cfg.save_interval = 10_000
            wrapped = RslRlVecEnvWrapper(env)
            # timeout bootstrap 不变量（报告 1 §8，Ch07）：wrapper 必须透传
            # time_outs，否则 GAE 把 episode 超时当终止清零 value → critic
            # 系统性低估长 episode（最高频的静默 bug）。冒烟阶段即拦截。
            time_outs = getattr(wrapped, "time_outs", None)
            if time_outs is None:
                raise ValueError(
                    "RslRlVecEnvWrapper 未暴露 time_outs —— timeout bootstrap 失效，"
                    "critic 会系统性低估长 episode"
                )
            result["time_outs_wired"] = True
            runner = OnPolicyRunner(wrapped, runner_cfg.to_dict() if hasattr(runner_cfg, "to_dict") else vars(runner_cfg))
            runner.learn(num_learning_iterations=iters)
            result["status"] = "ok"
            result["iters"] = iters
except Exception as exc:
    result["status"] = result.get("status") or "failed"
    result["error"] = f"{type(exc).__name__}: {exc}"
    result["traceback"] = traceback.format_exc()[-2000:]

print(json.dumps(result, default=str))
