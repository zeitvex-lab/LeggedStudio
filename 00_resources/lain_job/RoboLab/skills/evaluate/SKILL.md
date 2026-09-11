---
name: robolab-evaluate
description: Evaluate a RoboLab checkpoint independently and explain tracking, estimator, and artifact evidence.
---

# RoboLab evaluate

Use this skill when a checkpoint needs independent playback or quantitative
evaluation.

## Workflow

```bash
PYTHONPATH=src python -m robolab.cli workflow run evaluate \
  --framework <isaacgym|mjlab> --task <task> --method <method> \
  --checkpoint <checkpoint> --num-envs <N> --steps <N> \
  --device <device> --seed <seed>
```

Check that the checkpoint exists and that its `resolved_config.json` agrees
with the requested framework, task, and method. Report the complete JSON result,
including `mean_abs_forward_tracking_error` and PPO-EE estimator metrics when
present.

Do not overwrite a training run's metrics with evaluation output. Save the
independent evaluation result beside the run or in a clearly named report.
