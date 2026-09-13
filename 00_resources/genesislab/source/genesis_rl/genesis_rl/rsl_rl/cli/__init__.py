"""Command-line entrypoints for GenesisLab + RSL-RL.

These modules expose Python-side CLIs such as:

- ``genesis_rl.rsl_rl.cli.train``
- ``genesis_rl.rsl_rl.cli.play``

that mirror the behavior of the standalone scripts under
``scripts/reinforcement_learning/rsl_rl``.
"""

from . import train, play

__all__ = ["train", "play"]

