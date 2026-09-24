"""Standalone Unitree Go2 PIE stair-locomotion environment（薄委托）。

族级实现在 `adapters.mjlab.kits.quadruped_kit/skills/parkour/`。profile 的入口
（`go2-parkour.json` 的 `entrypoints.env`）指向本模块的 `unitree_go2_pie_env_cfg` ——
**迁移没有动入口路径**，包侧只剩"机型绑定 + profile + 配方就绪的实体配置"三样机型事实。

两处必须留在这里的机型事实：

1. **配方就绪的实体配置** `_get_pie_go2_robot_cfg` —— 本任务的机器人 = 本机型自己的
   实体配置（`local_tasks.mjlab_extension`：BuiltinPosition 执行器 + `training.xml` 碰撞）
   + PIE 的关节限位调整。技能层不重造物理，只接收它；
2. **PIE 大腿限位** `_get_pie_go2_spec` —— 限位**上界**由族角色（`hip_pitch`）与配方值决定，
   下界保留 MJCF 真值（见族级 `skills/parkour/binding.py::with_thigh_upper_limit`）。
   函数名与模块路径保持迁移前一致（等价性取证按"模块 + 限定名"比对 spec_fn）。
"""

from __future__ import annotations

from dataclasses import replace

from adapters.mjlab.kits.quadruped_kit.skills.parkour import binding as kit_parkour_binding
from adapters.mjlab.kits.quadruped_kit.skills.parkour import config as kit_parkour

from local_tasks.mjlab_extension import get_go2_robot_cfg

from ...binding import GO2_PARKOUR_BINDING
from ...profile import GO2_PARKOUR


def _get_pie_go2_spec():
    return kit_parkour_binding.with_thigh_upper_limit(
        get_go2_robot_cfg().spec_fn, GO2_PARKOUR
    )


def _get_pie_go2_robot_cfg():
    return replace(get_go2_robot_cfg(), spec_fn=_get_pie_go2_spec)


def unitree_go2_pie_env_cfg(play: bool = False):
    """Create the self-contained, stair-focused Go2 PIE environment."""
    return kit_parkour.make_env_cfg(
        GO2_PARKOUR_BINDING, GO2_PARKOUR, _get_pie_go2_robot_cfg, play=play
    )
