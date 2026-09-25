"""Go2 侧薄委托：族级 WTW（周期步态先验）技能（入口符号不动）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/wtw/`。本模块只剩三样 go2 事实：

1. **机型绑定** `GO2_WTW`（与 `locomotion/binding.py` 的 `GO2_VELOCITY` 同一份：
   WTW 的实体就是本机型的训练实体 `local_tasks.mjlab_extension.get_go2_robot_cfg`，
   足端几何/足端帧/根 body/关节序全部从它与契约派生）；
2. **任务数值** `WTW`（`WtwProfile`：θ 采样池、行为参数区间、奖励权重与核参数）；
3. **入口函数**（公开名不动，profile 的 `entrypoints` 照旧解析到这里）。

原先本文件的 247 行实现（装配 wtw 任务：`base_link` 帧、`FR/FL/RR/RL` 足端 site、
`<腿>_foot_collision` 模式、`^(?!.*_calf).*` 非足端模式、`<腿>_calf` 足端 body、
奖励权重表、行为 resample 事件；`wtw_mdp.py` 的 316 行 MDP 项）已全部上移为族级实现
＋ profile 数据，机型侧零任务数值字面量。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（与 locomotion/binding.py 同一约定）：worker / 冒烟 / schema-dump
# 三种运行环境都只把 training/source（或包根）放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.wtw import config as kit_wtw  # noqa: E402
from adapters.mjlab.kits.quadruped_kit.skills.wtw import profile as kit_wtw_profile  # noqa: E402

from .binding import GO2_VELOCITY  # noqa: E402

#: WTW 的机型绑定 = velocity 那份（同一个 `get_go2_robot_cfg` 实体；WTW 源实现即
#: `_registered_go2_robot_cfg()`，与 velocity 的实体逐字段相同）。两个技能共用一个
#: 绑定对象，不重复构造「同一台机型的同一份事实」。
GO2_WTW = GO2_VELOCITY

#: go2 的 WTW 任务数值。**θ 池 / 行为区间 / 奖励权重与核参数 / 命令重采样 / sim 上限
#: 全部与源实现逐值相同**，故这里只填机型身份（`task_id` / `experiment_name`）——
#: 其余字段用 `WtwProfile` 的源配方默认值。
WTW = kit_wtw_profile.WtwProfile(
    task_id="Unitree-Go2-WTW",
    experiment_name="go2_wtw",
)


def go2_wtw_rough_env_cfg(play: bool = False):
    return kit_wtw.make_env_cfg(GO2_WTW, WTW, terrain_profile="rough", play=play)


def go2_wtw_flat_env_cfg(play: bool = False):
    return kit_wtw.make_env_cfg(GO2_WTW, WTW, terrain_profile="flat", play=play)


def go2_wtw_runner_cfg():
    return kit_wtw.make_runner_cfg(WTW)
