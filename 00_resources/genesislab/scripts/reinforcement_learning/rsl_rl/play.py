"""Thin wrapper that forwards to ``genesis_rl.rsl_rl.cli.play``.

Kept for backwards compatibility with:

    python scripts/reinforcement_learning/rsl_rl/play.py
"""

import genesis as gs
import torch
import genesis_tasks.locomotion  # noqa: F401  (ensure tasks are registered)
import genesis_tasks.imitation.tracking
from genesis_rl.rsl_rl.cli.play import main

if __name__ == "__main__":
    gs.init(logging_level="WARNING")

    # Ensure TF32 is enabled for better performance when using CUDA.
    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = False
    main()

