# Legged Studio

Version `0.3.0` is the first distributable desktop preview.

Legged Studio is a local, contract-driven workbench for validating legged
robot assets, configuring rewards and algorithms, running native MJLab training,
using MuJoCo for interactive simulation, and replaying evaluation/navigation
routes for Go2 and Go2W.

## Quick start

```powershell
npm ci
npm start
```

The Electron launcher does not install or start services when it opens. The
Windows Online package contains no installed Torch/MJLab environment. It does
carry the small bootstrap inputs that would otherwise require GitHub: uv,
CPython base files, and fixed MJLab/Unitree source snapshots. Click **Configure
Runtime** to install the GPU profile into the user data directory, then click
Start and open the Web workbench.

The downloaded Windows profile is:

- Python 3.12.13 and uv 0.11.8.
- Torch 2.11.0+cu128.
- MJLab 1.6.0 and MuJoCo/MuJoCo-Warp 3.11.0.
- MJLab source `b517e0c` and Unitree extension `1425b15`.
- Tsinghua PyPI and Shanghai Jiao Tong PyTorch cu128 mirrors by default.

## Build a release

```powershell
npm ci
npm run release:check
npm run build:portable
```

Build the non-embedded, on-demand Windows 7z distribution:

```powershell
npm run build:online:win
```

The archive and its top-level directory are named
`Legged-Studio-0.3.0-Windows-Online`, not `win-unpacked` or Electron.

To build the Windows package with an embedded CPython 3.12 runtime, CUDA
Torch, MJLab, and the Unitree MJLab extension, run this target on Windows:

```powershell
npm run build:portable:embedded
```

This downloads several gigabytes of GPU wheels and produces an extract-and-run
directory plus a ZIP64-capable 7z archive. A single portable EXE is not used
because the CUDA runtime exceeds the NSIS payload limit. The generated runtime
is staged under `build/embedded-runtime` and is intentionally ignored by Git.

The Windows portable artifact is written to `dist/`. Build the Linux AppImage
on a Linux host or CI runner:

```bash
npm ci
npm run release:check
npm run build:linux
```

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) for runtime requirements,
packaging boundaries, and release limitations. See [docs/PRODUCT_VISION.md](docs/PRODUCT_VISION.md)
for the product workflow and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for
adapter boundaries.

## Verified capabilities

- Versioned Robot Contract and canonical Go2/Go2W MJCF assets.
- MuJoCo interactive simulation for basic teleoperation and map stepping.
- Native MJLab Go2/Go2W PPO training with isolated workers.
- Native evaluation and waypoint navigation.
- CUDA Torch selection for the validated MJLab adapter environment.
- Configurable local backend port and desktop-owned backend lifecycle.

The default lightweight distribution does not bundle an installed Torch/MJLab
runtime. It includes a small bootstrap Python/uv runtime and fixed source
snapshots; GPU dependencies are installed after the user clicks Configure
Runtime. The Windows embedded target bundles Python, CUDA Torch, MJLab, and the
Unitree MJLab extension; UniLab remains a future adapter.
