"""Validate a single training profile (runs in an isolated subprocess).

Usage:
  python tools/_smoke_one.py <package_root> <source_root> <env_factory> \
      <runner_factory_or_-> <num_envs> <rollout_steps> [--train --iters N]

Prints a JSON result object to stdout.
"""

from __future__ import annotations

import json
import sys
import tempfile
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
            from dataclasses import asdict

            from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper

            runner_cfg.max_iterations = iters
            runner_cfg.save_interval = 10_000
            # 离线冒烟默认走 TensorBoard，避免 wandb 在无网/未登录时中断
            # （与 native_worker 的默认 logger 一致）。
            runner_cfg.logger = "tensorboard"
            wrapped = RslRlVecEnvWrapper(env, clip_actions=getattr(runner_cfg, "clip_actions", None))
            # timeout bootstrap 不变量（报告 1 §8，Ch07）：rsl_rl 从 step 的
            # extras["time_outs"] 读取超时 bootstrap；wrapper 不透传会让 GAE 把
            # episode 超时当终止清零 value → critic 系统性低估长 episode（最高频
            # 的静默 bug）。mjlab 的 wrapper 在 !is_finite_horizon 时注入该键，
            # 因此用一次真实 step 验证而非查属性（属性名随版本漂移）。
            probe_action = torch.zeros((wrapped.num_envs, wrapped.num_actions), device=device)
            _, _, _, probe_extras = wrapped.step(probe_action)
            if not wrapped.cfg.is_finite_horizon and "time_outs" not in probe_extras:
                raise ValueError(
                    "RslRlVecEnvWrapper 未在 step 的 extras 中暴露 time_outs —— timeout "
                    "bootstrap 失效，critic 会系统性低估长 episode"
                )
            result["time_outs_wired"] = True
            # 与生产训练路径（native_worker）保持一致：MjlabOnPolicyRunner +
            # asdict 展开配置 + 显式 output 目录。
            output = tempfile.mkdtemp(prefix="legged_smoke_")
            runner = MjlabOnPolicyRunner(wrapped, asdict(runner_cfg), output, device)
            runner.learn(num_learning_iterations=iters)
            result["status"] = "ok"
            result["iters"] = iters
except Exception as exc:
    result["status"] = result.get("status") or "failed"
    result["error"] = f"{type(exc).__name__}: {exc}"
    result["traceback"] = traceback.format_exc()[-2000:]

print(json.dumps(result, default=str))
