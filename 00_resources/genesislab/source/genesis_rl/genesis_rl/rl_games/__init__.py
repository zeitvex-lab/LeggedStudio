"""Wrappers to configure GenesisLab environments for :mod:`rl_games`."""

from .rl_games import RlGamesVecEnvWrapper, RlGamesGpuEnv

__all__ = [
    "RlGamesVecEnvWrapper",
    "RlGamesGpuEnv",
]

