# MJLab adapter

This is the single MJLab adapter directory. It contains the locked runtime
project, training and simulation implementation, native worker, algorithms,
preflight checks, and tests. The FastAPI control plane does not import MJLab,
Torch, Warp, or MuJoCo-Warp directly.

## Development environment

Run the dependency-light preflight from the repository root:

```powershell
python adapters/mjlab/preflight.py
```

Create the development CUDA environment with uv:

```powershell
uv sync --project adapters/mjlab --extra cu128
```

The adapter targets Python 3.12 and pins MJLab 1.6.0. Native Go2 and ZEX-W
workers use manager-based MJLab training, evaluation, and waypoint navigation.
The Web control plane communicates with these workers through JSON task state
and artifact manifests.

## Online desktop runtime

The Windows Online archive uses the same pinned versions. It carries uv,
CPython bootstrap files, and fixed source snapshots; clicking Configure Runtime
installs Torch and the remaining wheels into Electron user data using domestic
mirrors. No GitHub request is needed on the target machine.
