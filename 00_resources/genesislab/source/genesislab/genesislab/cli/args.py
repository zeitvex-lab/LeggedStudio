"""Common CLI argument helpers for GenesisLab.

This module provides small utilities to add standard viewer / rendering
options to example and test scripts (e.g. ``--window``, ``--render``,
``--video``).
"""

from __future__ import annotations

import argparse


def add_viewer_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add standard viewer / rendering flags to an ``ArgumentParser``.

    Flags added:

    - ``--window``: turn *on* the Genesis viewer window (default is headless /
      no window).
    - ``--render``: slow down the step loop so that on-screen animation is
      human-viewable (useful together with ``--window``).
    - ``--video PATH``: optional path for saving a video. This is currently a
      placeholder; scripts may choose to interpret it as they see fit.
    """
    group = parser.add_argument_group("Viewer / Rendering")

    # Viewer on/off (single switch, default is no window / headless)
    group.add_argument(
        "--window",
        dest="window",
        action="store_true",
        help="Enable Genesis viewer window.",
    )
    group.set_defaults(window=False)

    # Slow, human-viewable stepping
    group.add_argument(
        "--render",
        action="store_true",
        help="Slow down stepping for human-viewable rendering.",
    )

    # Optional video output path (semantics left to the caller).
    group.add_argument(
        "--video",
        type=str,
        default=None,
        help="Optional path to save a rendered video (script-specific handling).",
    )

    return parser


__all__ = ["add_viewer_args"]

