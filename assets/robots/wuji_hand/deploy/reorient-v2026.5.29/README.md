# wuji-mjlab v0.1.0 — Release assets

This bundle contains the assets needed to reproduce the
`WujiHand_Reorient` task end-to-end with the published policy.

Source code: <https://github.com/wuji-technology/wuji-mjlab>

## Contents

- `checkpoints/`
  - `policy.onnx` — ONNX export consumed by `deploy/reorient/scripts/play_real.py`.
  - `model.pt` — original PPO checkpoint (rsl-rl) for fine-tuning or sim eval.
  - `config.json` — sidecar metadata (`action_scale`, `ema_alpha`,
    `ctrl_dt`, `history_len`, `warmup_time_s`, `control_mode`).
- `hardware/cube/`
  - `cube.3mf` — Bambu Lab dual-material print project (24 ArUco tags
    baked into the geometry — no stickers required).
  - `cube.step` — STEP for editing in any CAD tool.
  - `cube.obj` + `cube.mtl` + `cube.png` — reference mesh, material
    and UV-unwrapped texture (24 ArUco tags laid out per face). Load
    with `trimesh.load("cube.obj")` to verify tag positions, or print
    `cube.png` as sticker decals if you don't have a dual-material
    printer (see `docs/sim2real/setup.md` §3.1 for the fallback flow).
- `hardware/hand-jig/`
  - `base.3mf` — printable PLA base for the hand-mounting jig.
  - `assembly.step` — full assembly model (base + breadboard) for
    reference.
  - `assembly.pdf` — dimensioned assembly drawing (overall height,
    10° tilt, breadboard hole grid, base mounting/counterbore pattern,
    general tolerances). Detailed BOM and assembly steps are in
    [`docs/sim2real/setup.md`](https://github.com/wuji-technology/wuji-mjlab/blob/main/docs/sim2real/setup.md) §5.1.

## Quick start

1. Place `checkpoints/` at the wuji-mjlab repo root: `mv checkpoints /path/to/wuji-mjlab/checkpoints`.
2. Print `hardware/cube/cube.3mf` and `hardware/hand-jig/base.3mf` (Bambu Lab profile bundled).
3. Follow [`docs/sim2real/setup.md`](https://github.com/wuji-technology/wuji-mjlab/blob/main/docs/sim2real/setup.md) for assembly, calibration, and rollout.

## License

Apache-2.0 — see `LICENSE` in this bundle and `NOTICE` in the source
repo for third-party attributions.
