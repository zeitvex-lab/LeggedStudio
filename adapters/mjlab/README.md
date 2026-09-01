# MJLab adapter

This directory owns the isolated Python 3.12 MJLab runtime. The FastAPI control plane must not import this environment.

Run the dependency-light host preflight from the workspace root:

```powershell
python -m legged_studio.adapters.mjlab.preflight
```

Create the CUDA environment only after reviewing the report:

```powershell
uv sync --project legged_studio/adapters/mjlab --extra cu128
```

The local MJLab 1.6.0 source supports Python 3.10-3.13 and defaults to 3.13, but Legged Studio keeps this adapter on 3.12. Canonical Go2 (12 DOF) and Go2W (16 DOF) MJCF assets, Contracts, and forward-walk recipes now live in `legged_studio/assets`, `contracts/fixtures`, and `presets/training`. The isolated worker registers the native Go2 and Go2W tasks, runs manager-based PPO smoke/training/evaluation/navigation, and selects the CUDA extra when available.
