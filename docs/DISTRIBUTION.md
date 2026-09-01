# Legged Studio 0.3.0 distribution

This is the first distributable desktop preview. It packages the Electron
launcher, FastAPI control plane source, Web workbenches, Contracts, canonical
Go2/Go2W assets, adapters, and documentation.

The package does not embed a Python distribution, NVIDIA drivers, CUDA, MJLab
source, or the external UniLab/Unitree extension trees. The launcher remains
read-only until the user clicks Start. After that action, choose a Python
runtime, configure the service port if needed, and prepare the control-plane
environment. Training adapters are selected separately by the backend.

## Build on Windows

Install Node.js 18 or newer and npm dependencies:

```powershell
npm ci
npm run release:check
npm run build:portable
```

The portable output is written to `dist/`.

For a directory package used during QA:

```powershell
npm run build:dir
```

If a previous Electron process holds a file under `dist/`, use a different
output directory:

```powershell
npx electron-builder --dir --config.directories.output=dist/qa
```

## Build on Linux

Build Linux artifacts on a Linux host or CI runner:

```bash
npm ci
npm run release:check
npm run build:linux
```

This produces an AppImage and a directory package. The Linux launcher uses
`bin/python` for virtual environments and sends SIGTERM to the backend.

## Runtime choices

The control plane needs FastAPI, Uvicorn, and Pydantic. The native MJLab path
needs the adapter environment with MJLab, Torch, Warp/MuJoCo-Warp, RSL-RL, and
Tyro. On CUDA hosts, install the adapter with:

```powershell
uv sync --project adapters/mjlab --extra cu128
```

The same command is available on Linux with the platform-appropriate lock
resolution. CPU-only control-plane or MuJoCo use does not require CUDA, but
native MJLab CUDA training does require a compatible NVIDIA driver.

## What this release verifies

- Electron launcher and configurable local backend port.
- Contract validation and canonical Go2/Go2W asset loading.
- Local MuJoCo simulation and PPO/SAC/TD3 adapter smoke paths.
- Native MJLab Go2/Go2W PPO training, evaluation, and waypoint navigation.
- CUDA native MJLab selection on the validated RTX 4060 environment.

## Release limitations

- A fully self-contained Python/MJLab runtime is not included in the first
  package; this keeps the desktop artifact portable and avoids shipping a
  multi-gigabyte GPU stack for every platform.
- Native MJLab currently exposes PPO. Native SAC/TD3, complex map planning,
  rich native 3D playback, hardware deployment, and TensorRT remain future
  adapter work.
- AppImage must be built and tested on Linux; a Windows build host cannot
  validate Linux graphics and driver behavior.
