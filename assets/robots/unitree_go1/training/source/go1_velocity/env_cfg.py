"""Unitree Go1 velocity environment configuration（薄委托：族级 velocity 技能）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/velocity/`。本模块只剩三样 go1 事实：

1. **机型绑定** `GO1_VELOCITY`（`binding.py`：契约 + `model/robot.xml` 真值 + 本机型训练实体）；
2. **任务数值与机型配方** `GO1_VELOCITY`（`profile.py`：`VelocityProfile` + recipe ——
   HIMLoco / walk-these-ways 的任务数值、观测布局、奖励权重、事件与终止）；
3. **入口函数**（公开名不动：`go1_flat_env_cfg` / `go1_rough_env_cfg` / `make_go1_*` /
   `go1_runner_cfg`，profiles 与训练链照旧解析到这里）。

原先本文件里的 255 行接线（sim 上限 / 高度扫描重指 / 两组接触传感器 /
观测重排 / 奖励权重 / 事件与终止 / 命令档 / play 收尾）已全部上移：
族级机制在 Kit，机型专属那几样在 `profile.py` 的 recipe（同包数据面）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg

# 仓库根自举（见 kits/quadruped_kit 模块注释）：worker / schema-dump / 冒烟三种
# 运行环境都只把 training/source 或包根放进 sys.path；沿目录向上找 adapters/mjlab
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits import quadruped_kit as kit  # noqa: E402
from adapters.mjlab.kits.quadruped_kit.skills.velocity import config as kit_velocity  # noqa: E402

from .binding import GO1_VELOCITY as BINDING  # noqa: E402
from .profile import GO1_VELOCITY as PROFILE  # noqa: E402


def make_go1_env_cfg(play: bool = False, *, rough: bool = False) -> ManagerBasedRlEnvCfg:
    """Go1 velocity configuration (flat or rough).

    ``rough`` keeps mjlab's rough terrain generator, the root-body terrain scan
    sensor and the height-scan termination (source HIMLoco ``Go1RoughCfg``,
    ``terrain.measure_heights = True``); ``flat`` drops them (source
    walk-these-ways / flat evaluation).
    """
    return kit_velocity.make_env_cfg(
        BINDING,
        PROFILE,
        terrain_profile="rough" if rough else "flat",
        play=play,
    )


def make_go1_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Flat-ground Go1 velocity configuration."""
    return make_go1_env_cfg(play, rough=False)


def make_go1_rough_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Rough-terrain Go1 velocity configuration (source HIMLoco Go1RoughCfg)."""
    return make_go1_env_cfg(play, rough=True)


def go1_flat_env_cfg(*, play: bool = False):
    return make_go1_flat_env_cfg(play=play)


def go1_rough_env_cfg(*, play: bool = False):
    return make_go1_rough_env_cfg(play=play)


def go1_runner_cfg():
    """PPO runner —— **委托** `kits/quadruped_kit.ppo_runner_cfg`（唯一真值）。

    原先本函数内联了一份与 lite3/b2 逐字段相同的 runner 配置（隐藏层 512/256/128、
    elu、obs_normalization、Gaussian std 1.0 scalar、clip 0.2、entropy 0.01、
    epochs 5、minibatches 4、lr 1e-3 adaptive、gamma 0.99、lam 0.95、desired_kl 0.01、
    max_grad_norm 1.0、save_interval 100、num_steps 24、max_iterations 10_000）
    —— 三份副本一旦 Kit 调超参就会各自漂移。唯一差异是实验名，故由参数携带。
    """

    return kit.ppo_runner_cfg("go1_velocity")


def make_go1_stairs_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Go1 台阶速度档（2026-10-01 stairs 全族化）：族级 velocity + stairs 地形档。"""
  return kit_velocity.make_env_cfg(BINDING, PROFILE, terrain_profile="stairs", play=play)
