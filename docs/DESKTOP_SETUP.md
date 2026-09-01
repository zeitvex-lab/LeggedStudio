# Desktop setup

This document describes the Windows desktop launcher path for Legged Studio. The launcher owns the local control-plane process; training adapters remain isolated under `adapters/`.

## Start the workspace

From the project directory:

```powershell
npm install
npm start
```

The launcher automatically checks the control-plane Python executable, prepares writable `logs/`, `workspace/`, and `output/` directories in the Electron user-data directory, and waits for `/health` before enabling the Web console buttons.

After the control plane is running, the desktop pages link to the Web workbenches for asset inspection (`/web/assets.html`), policy artifacts/ONNX (`/web/artifacts.html`), and local evaluation (`/web/evaluation.html`).

## Configure the runtime

Open **系统设置** in the desktop launcher.

| Setting | Behavior |
|---|---|
| Python runtime | Detects executable, version, implementation, Python 3.12 policy match, and control-plane dependencies |
| Python path override | Uses the supplied `python.exe` for subsequent backend starts |
| Service port | Uses a configurable local port (`8765` by default, valid range `1024-65535`) and rejects conflicts before launch |
| Auto-start control plane | Starts the local API after the launcher is ready |
| Initialize workspace | Creates missing `logs/`, `workspace/`, and `output/` directories |

Settings are stored in the Electron user-data directory as `settings.json`; project source files are not modified by the settings form.
Changing the service port while the backend is running takes effect after the
backend is stopped and started again. The current session URL remains stable
until that restart.

## Runtime policy

The control plane targets Python 3.12 (`>=3.12,<3.13`). Training environments are adapter-specific and are reported independently. A missing adapter virtual environment is a warning for training, not a reason to prevent the desktop launcher from opening.

The launcher selects a runtime in this order:

1. Python path override saved in settings.
2. Packaged `runtime/python/python.exe`.
3. Existing `adapters/mjlab/.venv` or `adapters/mjlab_new/.venv` runtime.
4. Development `runtime/python/python.exe`.
5. System `python` on `PATH`.

Opening the launcher remains read-only. After **Start control plane** is
clicked, missing FastAPI/Uvicorn dependencies are installed into the selected
runtime; existing MuJoCo, Torch, ONNX, and MJLab packages are reused.

## Build a Windows package

Use a directory build for local verification:

```powershell
npx electron-builder --dir
```

The package includes the launcher, backend, contracts, pipeline, Web assets, adapter source, and the quadruped inventory. Adapter virtual environments and Python bytecode are excluded from the package; install them separately per adapter.

## Troubleshooting

If the launcher reports an unhealthy backend, open **控制台** and inspect the Python output. The most common causes are an unavailable Python executable, missing control-plane dependencies (`fastapi`, `uvicorn`, or `pydantic`), or port `8765` already being used. Stop a conflicting process or select a different configured runtime before restarting the backend.
