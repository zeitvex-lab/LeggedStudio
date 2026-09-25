"""Go2 的算法变体环境入口（薄委托：族级 Skills 的配方分支）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/velocity/variants.py`；本模块只剩三样：

1. **机型绑定** `GO2_VELOCITY`（`locomotion/binding.py`：契约 + `training.xml` 真值 +
   本机型训练实体）—— 关节序 / 足端几何与 site / 腿杆与躯干 body 词干 / 根 body
   全部由 Kit 从它派生；
2. **逐变体数值** `VARIANT_SPECS` / `VARIANT_TERRAIN`（`variants_profile.py`：数据面）；
3. **入口函数**（公开名不动，profile 的 `entrypoints.env` 照旧解析到这里）。

源实现（697 行的 `_go2_custom_algorithm_env_cfg` + 九个 `unitree_go2_*_env_cfg`）
已整段上移为族级机制，机型侧零字面量。
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg

from adapters.mjlab.kits.quadruped_kit.skills.velocity import variants as kit_variants

from .binding import GO2_VELOCITY
from .variants_profile import VARIANT_SPECS, VARIANT_TERRAIN
from .velocity import VELOCITY


def _variant_env_cfg(kind: str, play: bool) -> ManagerBasedRlEnvCfg:
    return kit_variants.make_variant_env_cfg(
        GO2_VELOCITY,
        VELOCITY,
        VARIANT_SPECS[kind],
        terrain=VARIANT_TERRAIN,
        play=play,
    )


def unitree_go2_dreamwaq_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _variant_env_cfg("dreamwaq", play)


def unitree_go2_amp_dreamwaq_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _variant_env_cfg("amp_dreamwaq", play)


def unitree_go2_cts_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _variant_env_cfg("cts", play)


def unitree_go2_amp_cts_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _variant_env_cfg("amp_cts", play)


def unitree_go2_amp_ts_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _variant_env_cfg("amp_ts", play)


def unitree_go2_amp_ts_student_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _variant_env_cfg("amp_ts_student", play)


def unitree_go2_ts_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _variant_env_cfg("ts", play)


def unitree_go2_ts_student_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _variant_env_cfg("ts_student", play)


def unitree_go2_him_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _variant_env_cfg("him", play)
