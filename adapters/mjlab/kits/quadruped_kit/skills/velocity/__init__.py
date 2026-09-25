"""族级 Velocity 技能（四足）。

* `config.py`：`make_env_cfg(binding, profile, terrain_profile=..., play=...)` —— 环境装配；
* `profile.py`：`VelocityProfile` —— 任务级数值（命令/地形/DR/奖励权重/终止阈值）；
* `variants.py`：`make_variant_env_cfg(binding, profile, spec, terrain=..., play=...)` ——
  **算法变体档**（CTS / AMP-CTS / TS / AMP-TS / TS-学生 / HIM / DreamWaQ / AMP-DreamWaQ）：
  同一技能的配方分支，逐项数值走 `VariantSpec`；
* `runner.py`：族级 runner 类与 `make_variant_runner_cfg(spec, base_runner_cfg=...)`
  （算法侧符号串与超参走 `VariantRunnerProfile`）。

与 `trot` / `jump` / `parkour` 同一分层：机型包只提交**绑定**（契约 + MJCF + 基座实体）
与**profile 覆盖**，实现全在本层，零机型字面量。
"""

from .config import TerrainProfile, make_env_cfg
from .profile import (
    VelocityProfile,
    VariantRunnerProfile,
    VariantSpec,
    VariantTerrain,
)
from .runner import (
    PolicyMetadataFn,
    VelocityDistillationRunner,
    VelocityOnPolicyRunner,
    make_variant_runner_cfg,
)
from .variants import make_variant_env_cfg

__all__ = [
    "PolicyMetadataFn",
    "TerrainProfile",
    "VelocityDistillationRunner",
    "VelocityOnPolicyRunner",
    "VelocityProfile",
    "VariantRunnerProfile",
    "VariantSpec",
    "VariantTerrain",
    "make_env_cfg",
    "make_variant_env_cfg",
    "make_variant_runner_cfg",
]
