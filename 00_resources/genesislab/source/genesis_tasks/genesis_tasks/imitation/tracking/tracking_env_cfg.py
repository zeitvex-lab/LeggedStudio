"""Whole-body tracking environment configuration for GenesisLab.

Subclass this and set scene.robots["robot"], commands.motion.motion_file,
commands.motion.anchor_body_name, and commands.motion.body_names for a concrete robot
(e.g. G1 BeyondMimic).
"""

from __future__ import annotations

from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnvCfg
from genesislab.utils.configclass import configclass

from .components import (
    ActionsCfg,
    CommandsCfg,
    CurriculumCfg,
    EventsCfg,
    ObservationsCfg,
    RewardsCfg,
    TerminationsCfg,
    TrackingSceneCfg,
)


@configclass
class TrackingEnvCfg(ManagerBasedRlEnvCfg):
    """Configuration for the whole-body tracking environment."""

    scene: TrackingSceneCfg = TrackingSceneCfg()
    observations: ObservationsCfg = ObservationsCfg()
    actions: ActionsCfg = ActionsCfg()
    commands: CommandsCfg = CommandsCfg()
    rewards: RewardsCfg = RewardsCfg()
    terminations: TerminationsCfg = TerminationsCfg()
    events: EventsCfg = EventsCfg()
    curriculum: CurriculumCfg = CurriculumCfg()

    def __post_init__(self):
        """Post initialization."""
        self.decimation = 4
        self.episode_length_s = 10.0
