# Step-Field Terrain — Go2-W Training Guide

This document describes an archived Go2-W experiment family. These tasks are
kept in-repo for reference and require `--experimental`; they are not part of
the default supported task surface.

## What is the Step Field?

The step field is a **deterministic, structured obstacle course** that replaces
random rough terrain.  A regular grid of equal-height square pillars is placed
on a flat base plane:

```
┌──────────────────────────────────┐  8 m × 8 m patch
│  (border — no pillars)           │
│  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐  │  ← pillars (height h, curriculum-scaled)
│  └──┘  └──┘  └──┘  └──┘  └──┘  │
│  ┌──┐  ┌──┐  ┌──┐  ┌──┐  ┌──┐  │
│  └──┘  └──┘  └──┘  └──┘  └──┘  │
│       (flat floor between)       │
└──────────────────────────────────┘
```

| Parameter | Value | Notes |
|---|---|---|
| Pillar footprint | 35 cm × 35 cm | Square, uniform |
| Gap between pillars | 40 cm | Flat walkable floor |
| Max pillar height | 15 cm | At curriculum difficulty = 1 |
| Difficulty range | 0 → 1 | Pillar height: 0 → 15 cm |
| Curriculum rows | 6 | One row per difficulty level |
| Patches per row | 20 | 120 patches total |

**Why this matters for hybrid locomotion:**
- Wheels roll efficiently on the flat floor between pillars.
- Each pillar edge forces a step-up/step-down decision — pure wheeling fails.
- The controlled layout makes failure modes easy to identify and reproduce.

---

## Task Variants

| Task ID | Locomotion | Init | Checkpoint |
|---|---|---|---|
| `go2w-stepfield-hybrid` | Wheels + legs | From scratch | — |
| `go2w-stepfield-hybrid-finetune` | Wheels + legs | Flat wheel policy | `go2w_velocity / model_10000.pt` |
| `go2w-stepfield-legs` | Legs only | From scratch | — |
| `go2w-stepfield-legs-finetune` | Legs only | Flat legs-only policy | `go2w_legs_only_omni / model_30000.pt` |

Legacy long-form `Mjlab-*` step-field names remain accepted temporarily as aliases.

> **Action-space note:** The hybrid tasks have a 16-dim action space (12 leg joints +
> 4 wheel velocities).  The legs-only tasks have a 12-dim action space (leg joints only).
> These two groups are **not interchangeable** — loading a hybrid checkpoint into a
> legs-only task (or vice versa) will fail due to mismatched output layer dimensions.

---

## Training Commands

### From Scratch

```bash
# Hybrid (wheels + legs)
python scripts/train.py --experimental go2w-stepfield-hybrid

# Legs-only
python scripts/train.py --experimental go2w-stepfield-legs
```

Both tasks default to **4096 parallel environments** and **20 000 iterations** for
fast wall-clock training.  Override either at the command line:

```bash
python scripts/train.py --experimental go2w-stepfield-hybrid \
  --env.scene.num-envs=2048 \
  --agent.max-iterations=30001
```

### Finetune from Existing Flat Checkpoint

Finetune picks up from an already-trained flat policy so the robot arrives at
the step field already knowing how to move, cutting the iterations needed to
learn obstacle negotiation.

```bash
# Hybrid — finetune from flat wheel run
# (checkpoint: logs/rsl_rl/go2w_velocity/2026-02-22_01-07-44/model_10000.pt)
python scripts/train.py --experimental go2w-stepfield-hybrid-finetune \
  --agent.load-run=2026-02-22_01-07-44

# Legs-only — finetune from flat legs-only omni run
# (checkpoint: logs/rsl_rl/go2w_legs_only_omni/2026-02-26_22-27-45_flat_walk_omni/model_30000.pt)
python scripts/train.py --experimental go2w-stepfield-legs-finetune \
  --agent.load-run=2026-02-26_22-27-45_flat_walk_omni
```

The `--agent.load-run` argument is the **timestamped directory name** inside
`logs/rsl_rl/<experiment_name>/`.  The experiment name and checkpoint filename
are already baked into each finetune config.

---

## Evaluation / Play

```bash
python scripts/play.py --experimental go2w-stepfield-hybrid \
  --checkpoint-file logs/rsl_rl/go2w_step_field_hybrid/<run_dir>/model_20000.pt

python scripts/play.py --experimental go2w-stepfield-legs \
  --checkpoint-file logs/rsl_rl/go2w_step_field_legs_only/<run_dir>/model_20000.pt
```

---

## Terrain Class Reference

`BoxUniformStepFieldTerrainCfg` lives in
`mjlab/terrains/primitive_terrains.py` and is exported from `mjlab.terrains`.
It can be used in any terrain generator config:

```python
from mjlab.terrains import BoxUniformStepFieldTerrainCfg
from mjlab.terrains.terrain_generator import TerrainGeneratorCfg

my_terrain = TerrainGeneratorCfg(
  size=(8.0, 8.0),
  curriculum=True,
  num_rows=6,
  num_cols=20,
  sub_terrains={
    "step_field": BoxUniformStepFieldTerrainCfg(
      box_size=0.35,        # pillar side length (m)
      box_spacing=0.40,     # gap between pillars (m)
      step_height_range=(0.0, 0.15),  # height at difficulty 0 / 1
    ),
  },
)
```
