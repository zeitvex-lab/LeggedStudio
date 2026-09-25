"""Unitree B2 的 CTS 档案入口（薄委托：族级算法变体 + 平台算法插件）。

**这是"算法轴复用"的证明档案**：族级环境装配（`skills/velocity/variants.py`）与
族级 runner 工厂（`skills/velocity/runner.py`）都不认识 b2，本模块只给两样 b2 事实 ——
绑定（复用 `b2_velocity.binding.B2_VELOCITY`）与数据（`profile.py`），**Kit 一行未改**。

三个入口都按名解析（档案 `entrypoints`）：

* `b2_cts_env_cfg` —— 族级变体工厂 + b2 的 cts 数据；
* `b2_cts_runner_cfg` —— 族级 runner 工厂（源配方 PPO 档 + 变体超参/符号）；
* 算法侧的落地由档案里的 `algorithm_plugin: "cts"` 声明 —— 训练服务经
  `adapters/mjlab/algorithms/registry.json` 把 CtsPPO / CtsActorModel / CtsCriticModel
  绑到 runner 上，**不经任何机型包**。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

# 仓库根自举（与 b2_velocity / b2_wtw 同一约定）：worker / schema-dump / 冒烟三种运行
# 环境都只把 training/source 或包根放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits import quadruped_kit as kit  # noqa: E402
from adapters.mjlab.kits.quadruped_kit.skills.velocity import runner as kit_runner  # noqa: E402
from adapters.mjlab.kits.quadruped_kit.skills.velocity import variants as kit_variants  # noqa: E402
from adapters.mjlab.kits.quadruped_kit.skills.velocity.variants import (  # noqa: E402
    SOURCE_VARIANT_TERRAIN,
)

from b2_velocity.binding import B2_VELOCITY  # noqa: E402
from b2_velocity.profile import B2_VELOCITY as VELOCITY  # noqa: E402

from .profile import CTS_RUNNER, CTS_SPEC  # noqa: E402


def b2_cts_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """CTS 变体的环境（族级装配 + b2 数据）。"""
    return kit_variants.make_variant_env_cfg(
        B2_VELOCITY,
        VELOCITY,
        CTS_SPEC,
        terrain=SOURCE_VARIANT_TERRAIN,
        play=play,
    )


def b2_cts_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    """CTS 变体的 runner（族级源配方 PPO 档 + 本档超参）。"""
    return kit_runner.make_variant_runner_cfg(
        CTS_RUNNER,
        base_runner_cfg=lambda: kit_runner.make_source_ppo_runner_cfg(
            kit.ppo_runner_cfg("b2_cts"),
            learning_rate=CTS_RUNNER.learning_rate,
            max_iterations=CTS_RUNNER.max_iterations,
            save_interval=CTS_RUNNER.save_interval,
            seed=CTS_RUNNER.seed,
        ),
    )
