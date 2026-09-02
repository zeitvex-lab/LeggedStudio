# Desktop setup

Legged Studio uses a thin Electron launcher and a local FastAPI control plane.
Opening the launcher is read-only: it does not create directories, install
packages, or start a service.

## Start on Windows

Extract the project-branded Online archive and run `Legged Studio.exe`:

```powershell
Legged-Studio-0.3.0-Windows-Online\Legged Studio.exe
```

Click **Configure Runtime** to install the pinned Windows GPU profile into the
Electron user-data directory. The Online archive already contains uv, the
CPython 3.12.13 bootstrap, and fixed MJLab/Unitree source snapshots, so the
configuration step does not need GitHub.

The runtime profile uses:

- Python 3.12.13 and uv 0.11.8
- Torch 2.11.0+cu128
- MJLab 1.6.0
- MuJoCo and MuJoCo-Warp 3.11.0
- Tsinghua PyPI and Shanghai Jiao Tong cu128 PyTorch mirrors

After provisioning completes, click **Start control plane**. The launcher
creates writable user-data directories, verifies Python and dependencies, starts
Uvicorn, validates `/health` identity (`app_id=legged-studio` and
`api_schema=legged-studio-api-1`), and only then enables Web actions.

## Port and Python settings

The service port defaults to `8765` and accepts integers from `1024` through
`65535`. Change it in Settings before starting the backend. A port occupied by
another service is rejected; an unrelated service can never be mistaken for
Legged Studio.

The Python path override is optional. Unsupported Python versions are rejected
before pip runs. The launcher never installs control-plane packages into an
unintended Python 3.9/3.10/3.11 interpreter.

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
