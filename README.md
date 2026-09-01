# Legged Studio

Version `0.3.0` is the first distributable desktop preview.

Legged Studio is a local, contract-driven workbench for validating legged
robot assets, configuring rewards and algorithms, running MuJoCo or native
MJLab training, and replaying evaluation/navigation routes for Go2 and Go2W.

## Quick start

```powershell
npm ci
npm start
```

The Electron launcher does not install or start services when it opens. Click
Start in the launcher, configure the Python runtime and service port if needed,
then open the Web workbench. Native MJLab training uses the isolated adapter
environment and can be installed with:

```powershell
uv sync --project adapters/mjlab --extra cu128
```

## Build a release

```powershell
npm ci
npm run release:check
npm run build:portable
```

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
- Local MuJoCo simulation and PPO/SAC/TD3 adapter smoke paths.
- Native MJLab Go2/Go2W PPO training with isolated workers.
- Native evaluation and waypoint navigation.
- CUDA Torch selection for the validated MJLab adapter environment.
- Configurable local backend port and desktop-owned backend lifecycle.

The default lightweight distribution does not bundle Python, CUDA, MJLab, or
the external source trees. The Windows embedded target bundles Python, CUDA
Torch, MJLab, and the Unitree MJLab extension; UniLab remains a future adapter.
