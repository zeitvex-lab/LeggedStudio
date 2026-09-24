"""族级技能的接触传感器装配。

来源：`go2_skills/shared/sensors.py`（逐字上移）。三处机型常量改为绑定参数：
足端几何名（`binding.foot_geoms`，按契约腿序）、腿杆惩罚正则
（`binding.penalized_geom_pattern`，族角色派生）、根 body 名（`binding.root_body`，MJCF 真值）。
传感器名（`FEET_SENSOR` / `PENALIZED_SENSOR` / `BASE_SENSOR`）是**技能级**常量，
同族所有机型一致 —— 奖励/终止项按名引用它们。
"""

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg

from ..binding import QuadrupedSkillBinding

FEET_SENSOR = "feet_ground_contact"
PENALIZED_SENSOR = "thigh_calf_ground_contact"
BASE_SENSOR = "base_ground_contact"


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
    penalized = ContactSensorCfg(
        name=PENALIZED_SENSOR,
        primary=ContactMatch(
            mode="geom", pattern=binding.penalized_geom_pattern, entity="robot"
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
