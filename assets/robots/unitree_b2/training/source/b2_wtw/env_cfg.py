"""Unitree B2 WTW（周期步态先验）环境配置（薄委托：族级 WTW 技能）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/wtw/`。本模块只给两样 b2 事实：

1. **机型绑定** `BINDING`（复用 `b2_velocity.binding.B2_VELOCITY`：WTW 的实体就是
   本机型的训练实体 `get_b2_robot_cfg`，与 velocity 同一份——足端几何/足端链接 body/
   足端 site/关节序/非足端 body 模式全部由绑定从契约 + `model/robot.xml` 派生）；
2. **任务数值** `PROFILE`（`WtwProfile`：本档案只填机型身份 —— θ 池 / 行为参数区间 /
   奖励权重与核参数 / 命令重采样 / 仿真心上限全部沿用源配方默认值，b2 无自有 WTW 配方）。

**零 Kit 改动**：本档案不新增也不修改 Kit 的任何一行 —— b2 与 go2 的差异（腿序
FR/FL/RR/RL、`XmlActuatorCfg` 包装的 MJCF 执行器、只有足端几何具名、足端链接是
`<腿>_calf`）全部由绑定派生吸收。

口径登记：WTW 的动作缩放是**标量 0.25**（源配方 `cfg.actions["joint_pos"].scale`），
与 b2 契约 `actuator_profile.by_role` 的逐角色缩放（hip 0.125）不是同一口径 ——
WTW 源配方即标量，本档案照源配方取值（与 `b2-velocity` 的 0.25 口径一致）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg

# 仓库根自举（与 b2_velocity/binding.py 同一约定）：worker / schema-dump / 冒烟三种
# 运行环境都只把 training/source 或包根放进 sys.path；沿目录向上找 adapters/mjlab
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.wtw import config as kit_wtw  # noqa: E402
from adapters.mjlab.kits.quadruped_kit.skills.wtw.profile import (  # noqa: E402
    WtwProfile,
)

from b2_velocity.binding import B2_VELOCITY as BINDING  # noqa: E402

#: b2 的 WTW 任务数值：机型身份 + 源配方默认值（b2 无 WTW 自有配方）。
PROFILE = WtwProfile(task_id="Unitree-B2-WTW", experiment_name="b2_wtw")


def make_b2_wtw_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return kit_wtw.make_env_cfg(BINDING, PROFILE, terrain_profile="flat", play=play)


def b2_wtw_env_cfg(*, play: bool = False):
    return make_b2_wtw_env_cfg(play=play)


def b2_wtw_runner_cfg():
    return kit_wtw.make_runner_cfg(PROFILE)
