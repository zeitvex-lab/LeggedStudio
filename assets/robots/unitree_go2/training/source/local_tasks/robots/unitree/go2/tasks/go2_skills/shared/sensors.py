"""Go2 侧薄委托：族级接触传感器装配 + 本机型绑定。

族级实现在 `.../quadruped_kit/skills/mdp/sensors.py`。传感器名是技能级常量
（族内一致），几何/体名来自 go2 的绑定（契约足端几何 + 族角色派生的腿杆惩罚正则 + MJCF 根 body）。
包内未上移的技能继续按老签名 `replace_sensors(cfg)` 调用。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.mdp import sensors as _kit_sensors

from ..binding import GO2

FEET_SENSOR = _kit_sensors.FEET_SENSOR
PENALIZED_SENSOR = _kit_sensors.PENALIZED_SENSOR
BASE_SENSOR = _kit_sensors.BASE_SENSOR


def replace_sensors(cfg) -> None:
    _kit_sensors.replace_sensors(cfg, GO2)


def replace_rear_stand_sensors(cfg) -> None:
    # Source asset.penalize_contacts_on contains only thigh and calf. Base contact
    # is handled separately as a termination and hip contact is not penalized.
    replace_sensors(cfg)
