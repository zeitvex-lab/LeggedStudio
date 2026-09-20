# ------------------------------------------------------------------------------
# B8 训练去包化（第三批 · 按"框架一致"裁决，2026-09-19）：本文件原先是**自带正文**
# 的 PPO runner 配置（actor / critic / algorithm 三件套逐字段手写）。构造正文已上移为
# ``adapters/mjlab/kits/wheel_leg_kit.ppo_runner_cfg_ex``（唯一真值，与 m20/b2w/go2w
# 同一处）；包内只保留**三个入口函数的签名与各自字面值**（``flat`` / ``rough`` /
# ``crawl`` 仍在 ``robot.config.rl_cfg`` 模块内，静态解析不受影响）。
#
# 语义等价：zex-w 与三包的两处差异已参数化进 Kit —— ``obs_normalization=False`` 与
# ``std_type="log"``（三包是 True / "scalar"）—— 其余字面值与 Kit 的既有默认同源。
# ``run_name=""`` 复现"原实现未显式传 run_name"时的 dataclass 默认（Kit 的默认是透传
# None，那是三包的显式字面值，两者语义不同，故这里必须显式给空串）。
#
# 代价（已裁决接受）：本文件**不再与上游 ``rc_mjlab`` 逐字一致**。35 轮曾把"包内 py 与
# 上游逐字一致"当作 provenance 资产；2026-09-19 用户裁决"按框架一致去移植"，该资产让位
# 于统一框架（同一裁决也覆盖了删除 ``robot/rsl_rl/`` 空壳）。
# ------------------------------------------------------------------------------

"""RL runner configurations for the ZEX-W wheel-legged competition tasks."""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（见 kits/wheel_leg_kit 模块注释）：worker / schema-dump / 冒烟三种运行
# 环境都只把 ``training/source``（或包根）放进 sys.path；沿目录向上找 ``adapters/mjlab``
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from mjlab.rl import RslRlOnPolicyRunnerCfg  # noqa: E402

from adapters.mjlab.kits import wheel_leg_kit as kit  # noqa: E402


def rough_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  """rough 主档（原字面值：lr 8e-4 / entropy 0.003 / 无观测归一化 / log 型噪声）。"""
  return kit.ppo_runner_cfg_ex(
    "robot_rough",
    run_name="",
    max_iterations=20_000,
    save_interval=100,
    init_noise_std=1.0,
    obs_normalization=False,
    std_type="log",
    learning_rate=8.0e-4,
    entropy_coef=0.003,
    max_grad_norm=1.0,
  )


def flat_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  """平坦档：rough 档换 experiment_name 并把 max_iterations 收到 10_000（原实现同）。"""
  cfg = rough_ppo_runner_cfg()
  cfg.experiment_name = "robot_flat"
  cfg.max_iterations = 10_000
  return cfg


def crawl_ppo_runner_cfg() -> RslRlOnPolicyRunnerCfg:
  """匍匐档：rough 档只换 experiment_name（原实现同）。"""
  cfg = rough_ppo_runner_cfg()
  cfg.experiment_name = "robot_crawl"
  return cfg
