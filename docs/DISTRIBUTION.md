# Legged Studio 0.3.0 distribution

This is the first distributable desktop preview. It packages the Electron
launcher, FastAPI control plane source, Web workbenches, Contracts, canonical
Go2/Go2W assets, adapters, and documentation.

The default package does not embed an installed Python/Torch/MJLab environment,
NVIDIA drivers, or CUDA runtime. The launcher remains
read-only until the user clicks Configure Runtime or Start. Configure Runtime
downloads the pinned environment; Start prepares the workspace and launches
the control plane. Training adapters are selected separately by the backend.

The recommended non-embedded Windows artifact is the Online 7z package. The
desktop application stays read-only on open; clicking Configure Runtime
downloads the pinned runtime into Electron's user data directory. The program
directory remains small and can be replaced without deleting the downloaded
environment.

To avoid unreliable GitHub access for users in China, the Online archive
already carries uv, the unconfigured CPython base distribution, and the fixed
MJLab/Unitree source snapshots. Runtime wheel installation defaults to
Tsinghua PyPI and (for the GPU profile) the Shanghai Jiao Tong cu128 PyTorch
mirror. No GitHub request is made during the packaged one-click setup.

The compute device is chosen in the launcher Settings (GPU by default, CPU as
an alternative). The launcher lists the detected GPU names when GPU is selected
and installs `torch==2.11.0+cu128` (GPU) or `torch==2.11.0+cpu` (CPU).

| Component | Downloaded version |
| --- | --- |
| uv | 0.11.8 |
| Python | 3.12.13 |
| Torch | 2.11.0 (`+cu128` GPU / `+cpu` CPU) |
| MJLab | 1.6.0 |
| MuJoCo / MuJoCo-Warp | 3.11.0 |
| MJLab source | b517e0c489139e7fcee95702cfb2b01931264985 |
| Unitree extension | 1425b15f73bd4095f0df53709d7c389c3eb9e790 |

For a Windows package that does embed the Python/MJLab GPU runtime, use
`npm run build:portable:embedded`. That target stages a standalone CPython
3.12 distribution, CUDA Torch (cu128), MJLab 1.6.0, and the Unitree extension
under `build/embedded-runtime` before Electron Builder packages it. The staged
directory is generated output and is not committed to Git.

The embedded target produces `dist/embedded-win/win-unpacked` and
`dist/Legged-Studio-0.3.0-Windows-CUDA.7z`. It intentionally does not create a
single EXE: the CUDA/MJLab payload is larger than the NSIS memory-mapped input
limit. Extracting the 7z archive preserves the same portable directory layout.

## Build on Windows

Install Node.js 18 or newer and npm dependencies:

```powershell
npm ci
npm run release:check
npm run build:portable
```

Embedded Windows runtime (large package, requires `uv` and network access):

```powershell
npm run build:portable:embedded
npm run verify:embedded:win
```

The portable output is written to `dist/`.

Non-embedded Online 7z package with project-branded directory names:

```powershell
npm run build:online:win
```

Output: `dist/Legged-Studio-0.3.0-Windows-Online.7z`.

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

- The default package remains lightweight. The Windows embedded target adds
  CPython, CUDA Torch, MJLab, and the Unitree extension, but NVIDIA display
  drivers must still be installed by the user.
- Native MJLab currently exposes PPO. Native SAC/TD3, complex map planning,
  rich native 3D playback, hardware deployment, and TensorRT remain future
  adapter work.
- AppImage must be built and tested on Linux; a Windows build host cannot
  validate Linux graphics and driver behavior.
