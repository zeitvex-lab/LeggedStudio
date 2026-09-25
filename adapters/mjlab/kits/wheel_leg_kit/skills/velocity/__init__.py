"""族级 velocity 技能（轮足族）：同一族底座上三条配方，机型差异全在绑定 + profile。"""

from .competition import VARIANTS as COMPETITION_VARIANTS
from .config import VARIANTS, WHEEL_GROUND_SENSOR, make_env_cfg
from .profile import (
    CommandRanges,
    CompetitionActionSpec,
    CompetitionCommandLevel,
    CompetitionCommandSpec,
    CompetitionEventSpec,
    CompetitionMetric,
    CompetitionObservationSpec,
    CompetitionRewardSpec,
    CompetitionSimSpec,
    CompetitionVelocityProfile,
    LegsOnlyRecipe,
    VelocityProfile,
)

__all__ = [
    "COMPETITION_VARIANTS",
    "VARIANTS",
    "WHEEL_GROUND_SENSOR",
    "CommandRanges",
    "CompetitionActionSpec",
    "CompetitionCommandLevel",
    "CompetitionCommandSpec",
    "CompetitionEventSpec",
    "CompetitionMetric",
    "CompetitionObservationSpec",
    "CompetitionRewardSpec",
    "CompetitionSimSpec",
    "CompetitionVelocityProfile",
    "LegsOnlyRecipe",
    "VelocityProfile",
    "make_env_cfg",
]
