# Desktop setup

Legged Studio uses a thin Electron launcher and a local FastAPI control plane.
Opening the launcher is read-only: it does not create directories, install
packages, or start a service.

## Start on Windows

Extract the project-branded Online archive and run `Legged Studio.exe`:

```powershell
Legged-Studio-0.3.0-Windows-Online\Legged Studio.exe
```

The default runtime never uses the system Python interpreter. The launcher
uses the bundled/on-demand portable Python 3.12.13 only; the Python path is
used from Settings only when you explicitly override it there.

Click **Configure Runtime** to install the pinned Windows runtime profile into
the Electron user-data directory. In Settings you can choose the compute
device (**GPU** by default, or **CPU**); when GPU is selected the launcher
lists the detected NVIDIA graphics cards. The Online archive already contains
uv, the CPython 3.12.13 bootstrap, and fixed MJLab/Unitree source snapshots, so
the configuration step does not need GitHub.

The runtime profile uses:

- Python 3.12.13 and uv 0.11.8
- Torch 2.11.0 (`+cu128` when GPU, `+cpu` when CPU)
- MJLab 1.6.0
- MuJoCo and MuJoCo-Warp 3.11.0
- Tsinghua PyPI and Shanghai Jiao Tong cu128 PyTorch mirrors (GPU) or the
  PyTorch CPU index

After provisioning completes, click **Start control plane**. The launcher
creates writable user-data directories, verifies Python and dependencies, starts
Uvicorn, validates `/health` identity (`app_id=legged-studio` and
`api_schema=legged-studio-api-1`), and only then enables Web actions.

## Port and Python settings

The service port defaults to `8765` and accepts integers from `1024` through
`65535`. Change it in Settings before starting the backend. A port occupied by
another service is rejected; an unrelated service can never be mistaken for
Legged Studio.

The Python path override is optional and opens a file picker. Leave it empty to
always use the project-bundled portable Python; the launcher never falls back to
the system Python. Unsupported Python versions are rejected before pip runs.

## Development commands

```powershell
npm ci
npm start
```

For a non-embedded Windows archive:

```powershell
npm run build:online:win
npm run verify:online:win
```

For a large embedded CUDA/MJLab directory package, use
`npm run build:portable:embedded`. It is separate from the Online build and is
not required for normal development.

## Troubleshooting

Use the Console page for the exact provisioning or backend error. Common
causes are blocked mirror access, missing NVIDIA display drivers, an occupied
service port, or a runtime that has not been configured yet. The launcher keeps
backend-dependent buttons disabled until the corresponding API request has
returned a verified result.
