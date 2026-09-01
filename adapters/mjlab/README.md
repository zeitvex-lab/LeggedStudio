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

The local MJLab 1.6.0 source supports Python 3.10-3.13 and defaults to 3.13, but Legged Studio keeps this adapter on 3.12. Canonical Go2 (12 DOF) and Go2W (16 DOF) MJCF assets, Contracts, and forward-walk recipes now live in `legged_studio/assets`, `contracts/fixtures`, and `presets/training`. The current worker records these configurations and runs a deterministic PPO smoke loop; native MJLab task registration remains isolated to this adapter and must be completed before claiming GPU training support.
