"""族级 velocity 技能（轮足族）：一份实现，四变体，机型差异全在绑定 + profile。"""

from .config import VARIANTS, WHEEL_GROUND_SENSOR, make_env_cfg
from .profile import CommandRanges, LegsOnlyRecipe, VelocityProfile

__all__ = [
    "VARIANTS",
    "WHEEL_GROUND_SENSOR",
    "CommandRanges",
    "LegsOnlyRecipe",
    "VelocityProfile",
    "make_env_cfg",
]
