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
# profile 声明的 runner 类（``entrypoints.runner_class``）。产品路径 native_worker.py 也是
# 按这个字段导入的；这里以前写死 MjlabOnPolicyRunner，导致自定义算法一律被跳过。
runner_class = sys.argv[sys.argv.index("--runner-class") + 1] if "--runner-class" in sys.argv else ""
# profile 的算法插件声明（与产品路径同一绑定函数；冒烟必须验**声明后的接线**，
# 否则"冒烟绿"只证明默认 PPO 能跑，声明了的算法从未被训练层验证过）。
plugin_name = sys.argv[sys.argv.index("--algorithm-plugin") + 1] if "--algorithm-plugin" in sys.argv else ""
plugin_variant = sys.argv[sys.argv.index("--algorithm-variant") + 1] if "--algorithm-variant" in sys.argv else ""


def _import_entrypoint(value: str):
    """``module:attr`` → 对象（与 native_worker._import_entrypoint 同形）。"""
    module_name, _, attr = value.partition(":")
    module = __import__(module_name, fromlist=[attr])
    return getattr(module, attr)

sys.path.insert(0, str(Path(source_root).resolve()))
sys.path.insert(0, str(Path(package_root).resolve()))
# 仓库根也要在路径上（放**末尾**，避免压过包内同名模块）：产品路径是
# ``python -m adapters.mjlab.native_worker``（cwd=仓库根），天然能 import ``adapters.*``；
# 而包内 runner（``local_tasks.robots.unitree.go2.training.runner``）确实会
# ``from adapters.mjlab.algorithms.amp.algorithms import ...``。不补这一条，这些 runner 一律
# ModuleNotFoundError（2026-09-20 实测：18 档里 16 档卡在这里）。
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.append(str(_REPO_ROOT))

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
        # runner 类以 profile 的 ``runner_class`` 为准（与产品路径同口径）。以前这里按
        # ``class_name != "PPO"`` 直接 skipped_custom_runner —— 于是 go2 18 档里 11 档
        # （cts / amp-cts / ts / amp-ts / ts-student / him / parkour / dreamwaq ×2 /
        # spring-jump / legstand）**从未被训练层验证过**，而它们的自定义算法本来就能训
        # （产品路径一直在用，见 native_worker._apply_profile_algorithm_plugin 与
        # profile 的 algorithm_plugin / 包内 runner）。缺的是本工具的接线，不是能力。
        from dataclasses import asdict

        from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper

        runner_cls = _import_entrypoint(runner_class) if runner_class else MjlabOnPolicyRunner
        result["runner_class"] = runner_class or "mjlab.rl:MjlabOnPolicyRunner"
        result["algorithm_class_name"] = algo_class

        if plugin_name:
            from adapters.mjlab.algorithms.plugin_registry import apply_algorithm_plugin

            result["algorithm_plugin"] = apply_algorithm_plugin(
                runner_cfg, algorithm_plugin=plugin_name,
                variant=plugin_variant or None,
            )
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
        # 与生产训练路径（native_worker）保持一致：profile 声明的 runner +
        # asdict 展开配置 + 显式 output 目录。
        output = tempfile.mkdtemp(prefix="legged_smoke_")
        runner = runner_cls(wrapped, asdict(runner_cfg), output, device)
        runner.learn(num_learning_iterations=iters)
        # 训练跑通也**不能**把 rollout 的 ``non_finite_reward`` 盖成 ok（另一个方向的假绿）。
        result["status"] = "ok" if finite else "non_finite_reward"
        result["iters"] = iters
except Exception as exc:
    # **无条件**置 failed，不能写 ``result.get("status") or "failed"``。
    # 旧的写法是"假绿"漏洞：rollout 阶段在训练之前就把 status 写成 ``"ok"``，之后任何
    # 异常（runner 导入失败、runner 构造失败……）都改不动 status —— 报告照样打出
    # ``18 ok / 0 failed``，实际 16 档连 runner 都没导进来（2026-09-20 实测踩中，
    # 且正好把"改动导致 7 档退步"这件事盖住了）。失败就是失败，细节进 error/traceback。
    result["status"] = "failed"
    result["error"] = f"{type(exc).__name__}: {exc}"
    result["traceback"] = traceback.format_exc()[-2000:]

print(json.dumps(result, default=str))
