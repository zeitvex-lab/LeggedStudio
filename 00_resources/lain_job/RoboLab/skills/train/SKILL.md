---
name: robolab-train
description: Run a RoboLab training job through the repository Workflow layer with backend, method, resource, and artifact checks.
---

# RoboLab train

Use this skill when the user asks to train or resume a RoboLab policy.

## Workflow

1. Identify `framework`, `task`, `method`, `num_envs`, `device`, `seed`, and
   `max_iterations`. Preserve the user's values; use a small smoke configuration
   only when they ask for a smoke test.
2. Check that the selected backend is available. Isaac Gym requires its external
   SDK and dedicated Python environment; MJLab requires its dedicated environment.
3. Run the existing Workflow/CLI; do not implement training inside this Skill:

```bash
PYTHONPATH=src python -m robolab.cli workflow run train \
  --framework <isaacgym|mjlab> --task <task> --method <method> \
  --num-envs <N> --device <device> --seed <seed> \
  --max-iterations <N> [--run-dir <dir>] [--resume-from <checkpoint>]
```

4. Report the returned run directory and checkpoint. Confirm that
   `resolved_config.json` and `metrics.json` exist before claiming success.

## Constraints

- Do not mix Isaac Gym and MJLab dependencies in one Python process.
- Do not call a backend-private runner directly from the Agent.
- A completed command is not evidence of convergence; distinguish smoke,
  training completion, and independent evaluation.
