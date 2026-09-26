"""族级技能的接触传感器装配。

来源：`go2_skills/shared/sensors.py`（逐字上移）。三处机型常量改为绑定参数：
足端几何名（`binding.foot_geoms`，按契约腿序，走 geom 匹配）、腿杆惩罚的匹配
（`binding.penalized_contact_match()`：几何具名走 geom、未具名走 body，**由资产事实选**）、
根 body 名（`binding.root_body`，MJCF 真值，走 body 匹配）。除腿杆那一项外，匹配面
与源配方同一口径、同族各机型同写法。传感器名（`FEET_SENSOR` / `PENALIZED_SENSOR` /
`BASE_SENSOR`）是**技能级**常量，同族所有机型一致 —— 奖励/终止项按名引用它们。
"""

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg

from ..binding import QuadrupedSkillBinding

FEET_SENSOR = "feet_ground_contact"
PENALIZED_SENSOR = "thigh_calf_ground_contact"
BASE_SENSOR = "base_ground_contact"

#: 速度跟踪族（`skills/velocity/`）的传感器名 —— 一族一套固定名，四足族各机型同值：
#: 奖励/终止/观测按名引用它们（`velocity/config.py` 从这里再导出）。
TERRAIN_SCAN = "terrain_scan"
FOOT_HEIGHT_SCAN = "foot_height_scan"
SELF_COLLISION_SENSOR = "self_collision"
THIGH_SENSOR = "thigh_ground_touch"
SHANK_SENSOR = "shank_ground_touch"
TRUNK_SENSOR = "trunk_ground_touch"


def replace_sensors(cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding) -> None:
    terrain = ContactMatch(mode="body", pattern="terrain")
    feet = ContactSensorCfg(
        name=FEET_SENSOR,
        primary=ContactMatch(
            mode="geom",
            pattern=binding.foot_geoms,
            entity="robot",
        ),
        secondary=terrain,
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
    )
    penalized_mode, penalized_pattern = binding.penalized_contact_match()
    penalized = ContactSensorCfg(
        name=PENALIZED_SENSOR,
        primary=ContactMatch(
            mode=penalized_mode, pattern=penalized_pattern, entity="robot"
        ),
        secondary=terrain,
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
    )
    base = ContactSensorCfg(
        name=BASE_SENSOR,
        primary=ContactMatch(mode="body", pattern=binding.root_body, entity="robot"),
        secondary=terrain,
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
    )
    cfg.scene.sensors = (feet, penalized, base)
