---
name: robolab-reproduce
description: Reproduce a RoboLab method recipe with explicit robot, task, framework, seed, and evidence checks.
---

# RoboLab reproduce

Use this skill when the user asks to reproduce a paper method or a fixed
Robot + Task + Method + Framework recipe.

## Workflow

1. Resolve the method metadata from `src/robolab/methods/registry.py` and check
   that the selected framework is supported.
2. Keep the robot, task, seed, backend, and method explicit. Do not infer a
   method from a task name.
3. Launch the train Workflow:

```bash
PYTHONPATH=src python -m robolab.cli workflow run reproduce \
  --framework <isaacgym|mjlab> --robot <robot> --task <task> \
  --method <method> --num-envs <N> --device <device> \
  --seed <seed> --max-iterations <N> --run-dir <dir>
```

4. After training, run the evaluate Skill in an independent worker and retain
   the resolved config, checkpoint, metrics, and evaluation JSON together.

## Evidence standard

- A smoke run proves only that the selected chain loads and steps.
- A reproduction run must identify checkpoint and resolved configuration.
- A reproduction claim must include independent evaluation metrics; do not
  describe a runnable checkpoint as paper-level numerical reproduction.
