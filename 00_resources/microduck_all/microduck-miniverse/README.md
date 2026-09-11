# Microduck Miniverse

This repository packages every ONNX policy published by Pollen Robotics in the
[Microduck simulator Space](https://huggingface.co/spaces/pollen-robotics/microduck-simulator)
as a separate Miniverse bundle.

The source checkpoints and two canonical MJCF archives are stored with Git LFS.
The build does not alter the source checkpoint files. It copies each graph,
lowers ONNX Elu nodes to equivalent runtime primitives, adds a Miniverse v0.3 simulation contract to the copy, and writes a
deterministic `.dhsim` archive under `dist/`.

## Included bundles

| Bundle | Published checkpoint | Embodiment |
| --- | --- | --- |
| `microduck-walking-v1` | `BEST_alpha_walking.onnx` | Microduck |
| `microduck-sitstand-v1` | `BEST_alpha_sitstand.onnx` | Microduck |
| `microduck-getup-v1` | `BEST_alpha_stand.onnx` | Microduck |
| `microduck-ground-pick-v1` | `alpha_ground_pick.onnx` | Microduck |
| `microduck-kick-left-v1` | `ball_kick_left.onnx` | Microduck |
| `microduck-kick-right-v1` | `ball_kick_right.onnx` | Microduck |
| `microduck-roulade-v1` | `roulade.onnx` | Microduck |
| `microduck-roller-v1` | `BEST_roller.onnx` | Microduck Rollers |
| `microduck-roller-crouch-v1` | `BEST_roller_crouch.onnx` | Microduck Rollers |

## Build

Install [uv](https://docs.astral.sh/uv/) and Git LFS, then run:

```bash
git lfs pull
uv sync
uv run scripts/build.py
```

The build invokes `miniverse bundle validate ... --json` for every archive.
Build one policy with `--only microduck-walking-v1`. Pass `--skip-validate`
only when developing the builder itself.

## Publish

Authenticate the Miniverse CLI once, then upload and publish every built bundle:

```bash
uv run miniverse auth login
uv run scripts/publish.py
```

Use `--upload-only` to create immutable revisions without changing the
published revision pointer. You can also pass one or more `.dhsim` paths.

See [SPEC.md](SPEC.md) for the controller contract and bundle decisions.
